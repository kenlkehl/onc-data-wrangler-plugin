"""Consolidated extraction using ontology-driven fields.

Uses a single LLM call per diagnosis to extract all fields at once,
with per-field {value, confidence, evidence}, code resolution, and
higher-confidence-wins merging across chunks.

When the ``clinical_summary`` ontology is the sole ontology, extraction
switches to free-text summary mode (see ``SummaryExtractor``).
"""

import copy
import json
import logging
from typing import Any, Optional

from ..llm.base import LLMClient
from ..ontologies import OntologyRegistry
from .result import (
    ExtractionResult,
    HIGH_CONFIDENCE_THRESHOLD,
    merge_results,
)
from .schema_builder import SchemaBuilder
from .code_resolver import GenericCodeResolver
from .domain_groups import (
    build_naaccr_consolidated_group,
    build_generic_consolidated_group,
    build_prior_state_block,
    CHUNK_USER_TEMPLATE,
    NARRATIVE_ITEM_IDS,
    PATIENT_LEVEL_ITEM_IDS,
)
from .diagnosis_discovery import DiagnosisInfo, discover_diagnoses
from ..ontologies.protocols import DomainGroup

logger = logging.getLogger(__name__)

# Default items per LLM call
DEFAULT_ITEMS_PER_CALL = 50


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def parse_json_object(text: str) -> dict | None:
    """Best-effort parse of a JSON object from LLM output."""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            part = parts[1]
            if part.lower().startswith("json"):
                part = part[4:]
            text = part.strip()

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        # Unwrap single-element array
        if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
            return result[0]
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Main Extractor
# ---------------------------------------------------------------------------

class Extractor:
    """Consolidated clinical data extractor.

    Uses a single LLM call per diagnosis to extract all fields at once,
    with per-field confidence/evidence tracking and code resolution.
    Maintains the same public interface as the previous Extractor for
    backward compatibility with ChunkedExtractor.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        ontology_ids: list[str],
        cancer_type: Optional[str] = "generic",
        items_per_call: int = DEFAULT_ITEMS_PER_CALL,
    ):
        self.llm_client = llm_client
        self.ontology_ids = ontology_ids if ontology_ids else ["naaccr"]
        self.cancer_type = cancer_type or "generic"
        self.items_per_call = items_per_call
        self._schema_builder = SchemaBuilder()

        # Initialize per-ontology resources
        self._ontologies: dict[str, Any] = {}
        self._code_resolvers: dict[str, Any] = {}
        self._item_registries: dict[str, dict[str, Any]] = {}  # field_id -> item

        # Consolidated extraction: single group per ontology
        self._consolidated_groups: dict[str, DomainGroup] = {}
        # Set of field_ids that are narrative (skip code resolution)
        self._narrative_field_ids: set[str] = set(NARRATIVE_ITEM_IDS)

        registry = OntologyRegistry()
        registry.discover()
        for oid in self.ontology_ids:
            ont = registry.get(oid)
            self._ontologies[oid] = ont
            self._init_ontology(oid, ont)

    def _init_ontology(self, oid: str, ont: Any) -> None:
        """Initialize code resolver, consolidated group, and item registry for one ontology."""
        # Code resolver
        resolver = getattr(ont, "get_code_resolver", lambda: None)()
        if resolver is None:
            # Build generic resolver from ontology's valid_values
            all_items = self._collect_all_items(ont)
            resolver = GenericCodeResolver.from_data_items(all_items)
        self._code_resolvers[oid] = resolver

        # Consolidated group
        if oid == "naaccr":
            from ..ontologies.schema_registry import SchemaRegistry
            self._naaccr_schema_registry = SchemaRegistry()
            self._consolidated_groups[oid] = build_naaccr_consolidated_group()
        else:
            self._consolidated_groups[oid] = build_generic_consolidated_group(ont)

        # Item registry: field_id -> item object
        registry: dict[str, Any] = {}
        all_items = self._collect_all_items(ont)
        for item in all_items:
            fid = self._get_field_id(item)
            registry[fid] = item
        self._item_registries[oid] = registry

    def _collect_all_items(self, ont: Any) -> list:
        """Collect all DataItem objects from an ontology."""
        items = []
        for cat in ont.get_base_items():
            items.extend(cat.items)
        try:
            for cat in ont.get_site_specific_items("generic"):
                items.extend(cat.items)
        except Exception:
            pass
        return items

    @staticmethod
    def _get_field_id(item: Any) -> str:
        """Get the field_id from an item (NAACCR or generic)."""
        if hasattr(item, "field_id"):
            return str(item.field_id)
        if hasattr(item, "item_number"):
            return str(item.item_number)
        return getattr(item, "json_field", None) or getattr(item, "id", str(id(item)))

    # ------------------------------------------------------------------
    # Public interface (same as old Extractor)
    # ------------------------------------------------------------------

    def extract_from_text(
        self,
        text: str,
        cancer_type: Optional[str] = None,
        max_tokens: Optional[int] = 32768,
    ) -> list[dict]:
        """Extract structured data from a single text document."""
        return self.extract_single_chunk(text, [], 0, 1, cancer_type, max_tokens)

    def extract_single_chunk(
        self,
        chunk_text: str,
        running: Optional[list[dict]] = None,
        chunk_index: int = 0,
        total_chunks: int = 1,
        cancer_type: Optional[str] = None,
        max_tokens: Optional[int] = 32768,
        max_retries: int = 3,
    ) -> list[dict]:
        """Extract from a single chunk.

        Delegates to ``extract_single_chunk_consolidated`` which uses
        a single LLM call per diagnosis (1 discovery + 1 consolidated).
        """
        return self.extract_single_chunk_consolidated(
            chunk_text, running, chunk_index, total_chunks,
            cancer_type, max_tokens, max_retries,
        )

    def extract_iterative(
        self,
        texts: list[str],
        cancer_type: Optional[str] = None,
        max_tokens: Optional[int] = 8000,
        max_retries: int = 3,
    ) -> list[dict]:
        """Extract from multiple text chunks iteratively."""
        running: list[dict] = []
        for i, chunk_text in enumerate(texts):
            running = self.extract_single_chunk(
                chunk_text, running, i, len(texts),
                cancer_type, max_tokens, max_retries,
            )
        return running

    # ------------------------------------------------------------------
    # Prompt building & response parsing
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self,
        group: DomainGroup,
        json_instructions: str,
        context: dict[str, str],
    ) -> str:
        """Build the system prompt for a domain group."""
        template = group.system_prompt_template

        # Substitute known context variables
        format_kwargs = {"json_format_instructions": json_instructions}
        for key in ["primary_site", "histology", "primary_site_desc", "site_context",
                     "domain_name", "domain_context", "tumor_context"]:
            if f"{{{key}}}" in template:
                format_kwargs[key] = context.get(key, "unknown")

        try:
            return template.format(**format_kwargs)
        except KeyError:
            # Fallback: just append JSON instructions
            return template + "\n\n" + json_instructions

    def _parse_response(
        self,
        response: dict,
        items: list,
        oid: str,
        resolver: Any,
        chunk_index: int,
        is_narrative: bool,
    ) -> list[ExtractionResult]:
        """Parse LLM JSON response into ExtractionResult objects."""
        results: list[ExtractionResult] = []

        # Build lookup: prompt_field_name -> item
        field_map: dict[str, Any] = {}
        for item in items:
            pfn = self._schema_builder._field_name(item)
            field_map[pfn] = item

        for field_name, payload in response.items():
            if field_name.startswith("_"):
                continue

            item = field_map.get(field_name)
            if item is None:
                logger.debug("LLM returned unknown field '%s'; skipping.", field_name)
                continue

            if not isinstance(payload, dict):
                # Handle flat value (no {value, confidence, evidence} wrapper)
                payload = {"value": str(payload), "confidence": 0.5, "evidence": ""}

            raw_value = str(payload.get("value", "")).strip()
            llm_confidence = float(payload.get("confidence", 0.5))
            evidence = str(payload.get("evidence", "")).strip()

            if not raw_value:
                continue

            field_id = self._get_field_id(item)

            # Per-item narrative detection: group-level flag OR field_id in narrative set
            field_is_narrative = is_narrative or field_id in self._narrative_field_ids

            if field_is_narrative:
                # No code resolution for narrative text
                length = getattr(item, "length", 0) or 0
                if length > 0:
                    raw_value = raw_value[:length]
                results.append(ExtractionResult(
                    field_id=field_id,
                    field_name=field_name,
                    extracted_value=raw_value,
                    resolved_code=raw_value,
                    confidence=round(llm_confidence, 4),
                    evidence_text=evidence[:300],
                    source_chunk_id="aggregated",
                    source_chunk_type="aggregated",
                    pass_number=chunk_index,
                    ontology_id=oid,
                ))
            else:
                # Resolve code
                resolved_code, resolution_confidence = resolver.resolve(field_id, raw_value)

                if resolution_confidence > 0.0:
                    final_confidence = min(llm_confidence, resolution_confidence)
                else:
                    final_confidence = llm_confidence * 0.5

                results.append(ExtractionResult(
                    field_id=field_id,
                    field_name=field_name,
                    extracted_value=raw_value,
                    resolved_code=resolved_code,
                    confidence=round(final_confidence, 4),
                    evidence_text=evidence[:300],
                    source_chunk_id="sequential",
                    source_chunk_type="sequential",
                    pass_number=chunk_index,
                    ontology_id=oid,
                ))

        return results

    # ------------------------------------------------------------------
    # NAACCR-specific helpers
    # ------------------------------------------------------------------

    def _resolve_naaccr_items(self, group: DomainGroup, item_registry: dict[str, Any]) -> list:
        """Resolve NAACCR item numbers to dictionary items."""
        items = []
        for fid in group.field_ids:
            item = item_registry.get(fid)
            if item is None:
                # Try loading from dictionary
                try:
                    ont = self._ontologies["naaccr"]
                    dict_obj = getattr(ont, "dictionary", None)
                    if dict_obj:
                        item = dict_obj.get_item(int(fid))
                        if item:
                            item_registry[fid] = item
                except (ValueError, TypeError):
                    pass
            if item is not None:
                # Skip retired items
                if getattr(item, "year_retired", ""):
                    continue
                items.append(item)
        return items

    def _resolve_generic_items(self, group: DomainGroup, item_registry: dict[str, Any]) -> list:
        """Resolve generic field_ids to item objects."""
        items = []
        for fid in group.field_ids:
            item = item_registry.get(fid)
            if item is not None:
                items.append(item)
        return items

    def _resolve_naaccr_schema(
        self,
        internal_state: dict[str, ExtractionResult],
        context: dict[str, str],
        groups: list[DomainGroup],
    ) -> None:
        """After demographics extraction, resolve schema and populate staging group."""
        primary_site_result = internal_state.get("400")
        histology_result = internal_state.get("522")

        primary_site = ""
        histology = ""
        if primary_site_result:
            primary_site = primary_site_result.resolved_code or primary_site_result.extracted_value
        if histology_result:
            histology = histology_result.resolved_code or histology_result.extracted_value

        schema = self._naaccr_schema_registry.get_schema_for_site_histology(
            primary_site, histology, None,
        )
        staging_items = self._naaccr_schema_registry.get_all_staging_items(schema)
        site_desc = self._naaccr_schema_registry.get_primary_site_description(schema)
        site_context = self._naaccr_schema_registry.get_site_context(schema)

        context["primary_site"] = primary_site or "unknown"
        context["histology"] = histology or "unknown"
        context["schema"] = schema
        context["primary_site_desc"] = site_desc
        context["site_context"] = site_context

        # Populate the dynamic staging group
        for group in groups:
            if group.group_id == "staging" and group.dynamic:
                group.field_ids = [str(n) for n in staging_items]
                break

    # ------------------------------------------------------------------
    # Multi-diagnosis helpers
    # ------------------------------------------------------------------

    def _seed_from_diagnosis(
        self,
        diag: DiagnosisInfo,
        state: dict[str, ExtractionResult],
    ) -> dict[str, ExtractionResult]:
        """Pre-populate extraction state from discovery results.

        Only seeds fields that are not already present with higher
        confidence, so that actual extraction can override discovery.
        """
        seeds: list[tuple[str, str, str, str]] = []  # (field_id, field_name, value, evidence)
        if diag.primary_site:
            seeds.append(("400", "primarySite", diag.primary_site, diag.evidence))
        if diag.histology:
            seeds.append(("522", "histologicTypeIcdO3", diag.histology, diag.evidence))
        if diag.date_of_diagnosis:
            seeds.append(("390", "dateOfDiagnosis", diag.date_of_diagnosis, diag.evidence))
        if diag.laterality:
            seeds.append(("410", "laterality", diag.laterality, diag.evidence))

        for fid, fname, value, evidence in seeds:
            existing = state.get(fid)
            seed_conf = diag.confidence * 0.8  # Slightly lower than direct extraction
            if existing is None or existing.confidence < seed_conf:
                state[fid] = ExtractionResult(
                    field_id=fid,
                    field_name=fname,
                    extracted_value=value,
                    resolved_code=value,
                    confidence=round(seed_conf, 4),
                    evidence_text=evidence[:300],
                    source_chunk_id="discovery",
                    source_chunk_type="discovery",
                    pass_number=0,
                    ontology_id="naaccr",
                    tumor_index=diag.tumor_index,
                )
        return state

    @staticmethod
    def _base_context_from_diagnosis(diag: DiagnosisInfo, cancer_type: str) -> dict[str, str]:
        """Build a context dict from a DiagnosisInfo."""
        return {
            "cancer_type": cancer_type,
            "primary_site": diag.primary_site or "unknown",
            "histology": diag.histology or "unknown",
        }

    @staticmethod
    def _build_tumor_context(diag: DiagnosisInfo, total_diagnoses: int) -> str:
        """Build a tumor_context string telling the LLM which diagnosis to extract for."""
        if total_diagnoses <= 1:
            return ""
        parts = [
            f"EXTRACTING FOR DIAGNOSIS {diag.tumor_index + 1} OF {total_diagnoses}:",
        ]
        if diag.primary_site or diag.primary_site_description:
            site = diag.primary_site_description or diag.primary_site
            parts.append(f"Primary Site: {diag.primary_site} ({site})")
        if diag.histology or diag.histology_description:
            hist = diag.histology_description or diag.histology
            parts.append(f"Histology: {diag.histology} ({hist})")
        if diag.date_of_diagnosis:
            parts.append(f"Date of Diagnosis: {diag.date_of_diagnosis}")
        if diag.laterality and diag.laterality != "not_applicable":
            parts.append(f"Laterality: {diag.laterality}")
        parts.append(
            "Extract ONLY information pertaining to THIS specific cancer diagnosis. "
            "Do NOT include data from the patient's other cancer(s)."
        )
        parts.append(
            "For staging fields: use ONLY staging data from the initial diagnosis "
            "workup for THIS cancer. Do NOT incorporate later recurrence, "
            "progression, or metastatic events into the original stage."
        )
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Consolidated extraction (1 discovery + 1 call per diagnosis)
    # ------------------------------------------------------------------

    def _resolve_schema_from_discovery(
        self,
        diag: DiagnosisInfo,
        context: dict[str, str],
        group: DomainGroup,
    ) -> None:
        """Resolve NAACCR staging schema from discovery results.

        Uses ``DiagnosisInfo.primary_site`` and ``histology`` directly
        (instead of extraction state) and appends staging item IDs to
        the consolidated group's ``field_ids``.
        """
        primary_site = diag.primary_site or ""
        histology = diag.histology or ""

        schema = self._naaccr_schema_registry.get_schema_for_site_histology(
            primary_site, histology, None,
        )
        staging_items = self._naaccr_schema_registry.get_all_staging_items(schema)
        site_desc = self._naaccr_schema_registry.get_primary_site_description(schema)
        site_context = self._naaccr_schema_registry.get_site_context(schema)

        context["primary_site"] = primary_site or "unknown"
        context["histology"] = histology or "unknown"
        context["primary_site_desc"] = site_desc
        context["site_context"] = site_context

        # Append staging items to the consolidated group
        if group.dynamic:
            existing = set(group.field_ids)
            for item_num in staging_items:
                sid = str(item_num)
                if sid not in existing:
                    group.field_ids.append(sid)
                    existing.add(sid)

    def _extract_consolidated(
        self,
        group: DomainGroup,
        chunk_text: str,
        merged_state: dict[str, ExtractionResult],
        oid: str,
        resolver: Any,
        item_registry: dict[str, Any],
        context: dict[str, str],
        chunk_index: int,
        total_chunks: int,
        max_tokens: Optional[int],
        max_retries: int,
        tumor_context: str = "",
    ) -> tuple[list[ExtractionResult], dict[str, list[dict[str, str]]]]:
        """Extract all fields (single + multi-instance) in one LLM call.

        Returns ``(single_instance_results, multi_instance_data)`` where
        ``multi_instance_data`` is ``{group_id: [row_dict, ...]}``.
        """
        # -- Resolve single-instance items --
        if oid == "naaccr":
            single_items = self._resolve_naaccr_items(group, item_registry)
        else:
            single_items = self._resolve_generic_items(group, item_registry)

        # Filter high-confidence items
        single_items = [
            item for item in single_items
            if merged_state.get(self._get_field_id(item)) is None
            or merged_state[self._get_field_id(item)].confidence < HIGH_CONFIDENCE_THRESHOLD
        ]

        # -- Resolve multi-instance items --
        mi_groups_info: list[tuple[str, str, list[Any]]] = []
        for mi_sub in group.multi_instance_subgroups:
            mi_items = self._resolve_generic_items(mi_sub, item_registry)
            if mi_items:
                mi_groups_info.append((mi_sub.group_id, mi_sub.name, mi_items))

        if not single_items and not mi_groups_info:
            return [], {}

        # -- Build format instructions --
        json_instructions = self._schema_builder.build_consolidated_format_instructions(
            single_items, mi_groups_info, resolver,
        )

        # -- Build system prompt --
        system_prompt = self._build_system_prompt(group, json_instructions, context)

        # -- Build user prompt --
        field_ids = [self._get_field_id(item) for item in single_items]
        prior_block = build_prior_state_block(merged_state, field_ids)

        user_prompt = CHUNK_USER_TEMPLATE.format(
            first_date="",
            last_date="",
            chunk_text=chunk_text,
            tumor_context=tumor_context,
            prior_state_block=prior_block,
            json_field_descriptions=json_instructions,
        )

        # -- Call LLM with retry --
        parsed = None
        full_prompt = system_prompt + "\n\n" + user_prompt
        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate_structured(
                    full_prompt, max_tokens=max_tokens or 32768,
                )
                parsed = parse_json_object(response.text)
                if parsed is not None:
                    break
                logger.warning(
                    "Consolidated extraction JSON parse failed (attempt %d/%d)",
                    attempt + 1, max_retries,
                )
                failed_text = response.text[:2000] if len(response.text) > 2000 else response.text
                full_prompt = (
                    system_prompt + "\n\n" + user_prompt
                    + "\n\n--- PREVIOUS ATTEMPT FAILED ---\n"
                    "Your previous response could not be parsed as valid JSON. "
                    "Here is what you returned:\n\n"
                    + failed_text
                    + "\n\nPlease try again and return ONLY a valid JSON object."
                )
            except Exception:
                logger.exception(
                    "Consolidated extraction LLM call failed (attempt %d/%d)",
                    attempt + 1, max_retries,
                )

        if parsed is None:
            return [], {}

        # -- Parse single-instance results --
        # Separate out multi-instance arrays before parsing single-instance
        mi_raw: dict[str, list[dict]] = {}
        single_response: dict[str, Any] = {}
        for key, value in parsed.items():
            if key.startswith("_") and isinstance(value, list):
                # Multi-instance array
                mi_raw[key.lstrip("_")] = value
            else:
                single_response[key] = value

        single_results = self._parse_response(
            single_response, single_items, oid, resolver, chunk_index, False,
        )

        # -- Parse multi-instance results --
        mi_data: dict[str, list[dict[str, str]]] = {}
        for group_id, group_name, mi_items in mi_groups_info:
            raw_instances = mi_raw.get(group_id, [])
            if not raw_instances:
                continue
            # Build field map for this mi group
            mi_field_map: dict[str, Any] = {}
            for item in mi_items:
                pfn = self._schema_builder._field_name(item)
                mi_field_map[pfn] = item
            instances: list[dict[str, str]] = []
            for instance_data in raw_instances:
                if not isinstance(instance_data, dict):
                    continue
                row: dict[str, str] = {}
                for fname, payload in instance_data.items():
                    item = mi_field_map.get(fname)
                    if item is None:
                        continue
                    if not isinstance(payload, dict):
                        payload = {"value": str(payload), "confidence": 0.5, "evidence": ""}
                    raw_val = str(payload.get("value", "")).strip()
                    if not raw_val:
                        continue
                    fid = self._get_field_id(item)
                    resolved, _ = resolver.resolve(fid, raw_val)
                    row[fname] = resolved
                if row:
                    instances.append(row)
            if instances:
                mi_data[group_id] = instances

        return single_results, mi_data

    def extract_single_chunk_consolidated(
        self,
        chunk_text: str,
        running: Optional[list[dict]] = None,
        chunk_index: int = 0,
        total_chunks: int = 1,
        cancer_type: Optional[str] = None,
        max_tokens: Optional[int] = 32768,
        max_retries: int = 3,
    ) -> list[dict]:
        """Consolidated extraction: 1 discovery + 1 call per diagnosis per chunk.

        Replaces the multi-call sequential domain-group approach with a
        single consolidated LLM call that extracts all single-instance
        fields (demographics, staging, treatment, follow-up, narratives)
        and all multi-instance categories (regimens, biomarkers) at once.
        """
        if running is None:
            running = []

        ct = cancer_type or self.cancer_type

        # Reconstruct state from prior chunks
        patient_state, diagnosis_states, discovered, multi_instance_data = \
            self._list_to_internal_multi(running)

        # --- Discovery (chunk 0 only) ---
        if not discovered:
            discovered = discover_diagnoses(
                self.llm_client, chunk_text,
                max_tokens=4096, max_retries=max_retries,
            )
            for diag in discovered:
                if diag.tumor_index not in diagnosis_states:
                    diagnosis_states[diag.tumor_index] = {}

        # --- Per-diagnosis consolidated extraction ---
        for diag in discovered:
            tidx = diag.tumor_index
            diag_state = diagnosis_states.get(tidx, {})

            # Seed from discovery results
            diag_state = self._seed_from_diagnosis(diag, diag_state)

            for oid in self.ontology_ids:
                resolver = self._code_resolvers[oid]
                item_registry = self._item_registries.get(oid, {})
                group = copy.deepcopy(self._consolidated_groups.get(oid))
                if group is None:
                    continue

                context = dict(self._base_context_from_diagnosis(diag, ct))
                tumor_context = self._build_tumor_context(diag, len(discovered))
                context["tumor_context"] = tumor_context

                # Schema resolution from discovery (NAACCR)
                if oid == "naaccr":
                    self._resolve_schema_from_discovery(diag, context, group)
                else:
                    # For generic ontologies, populate domain_context
                    from .domain_groups import build_generic_consolidated_group
                    ont = self._ontologies.get(oid)
                    if ont:
                        contexts = []
                        for cat in ont.get_base_items():
                            ctx = getattr(cat, "context", "") or getattr(cat, "description", "") or ""
                            if ctx:
                                contexts.append(f"{cat.name}: {ctx}")
                        context["domain_context"] = "\n".join(contexts) if contexts else ""

                # Merge patient + diagnosis state for HIGH_CONFIDENCE filtering
                merged_state = {**patient_state, **diag_state}

                single_results, mi_data = self._extract_consolidated(
                    group=group,
                    chunk_text=chunk_text,
                    merged_state=merged_state,
                    oid=oid,
                    resolver=resolver,
                    item_registry=item_registry,
                    context=context,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                    max_tokens=max_tokens,
                    max_retries=max_retries,
                    tumor_context=tumor_context,
                )

                # Split results: patient-level vs diagnosis-level
                for r in single_results:
                    r.ontology_id = oid
                    if r.field_id in PATIENT_LEVEL_ITEM_IDS:
                        # Patient-level: store once, higher confidence wins
                        existing = patient_state.get(r.field_id)
                        if existing is None or r.confidence > existing.confidence:
                            patient_state[r.field_id] = r
                    else:
                        r.tumor_index = tidx

                diag_results = [
                    r for r in single_results
                    if r.field_id not in PATIENT_LEVEL_ITEM_IDS
                ]
                diag_state = merge_results(diag_state, diag_results)

                # Merge multi-instance data
                for mi_group_id, instances in mi_data.items():
                    mi_key = f"{tidx}_{mi_group_id}"
                    existing_mi = multi_instance_data.get(mi_key, [])
                    existing_mi.extend(instances)
                    multi_instance_data[mi_key] = existing_mi

            diagnosis_states[tidx] = diag_state

        return self._internal_to_list_multi(
            patient_state, diagnosis_states, discovered, multi_instance_data,
        )

    # ------------------------------------------------------------------
    # Format conversion (internal <-> list[dict])
    # ------------------------------------------------------------------

    def _list_to_internal(self, running: list[dict]) -> dict[str, ExtractionResult]:
        """Convert list[dict] format to internal ExtractionResult state.

        Handles the ``[{category: {field: value}}]`` format from old
        Extractor output.
        """
        state: dict[str, ExtractionResult] = {}
        if not running:
            return state

        # Check if we already have metadata from a previous round
        for entry in running:
            if not isinstance(entry, dict):
                continue

            # Check for embedded ExtractionResult metadata
            if "_extraction_results" in entry:
                for fid, result_dict in entry["_extraction_results"].items():
                    state[fid] = ExtractionResult.from_dict(result_dict)
                continue

            # Standard format: {category: {field: value}}
            for category, fields in entry.items():
                if category.startswith("_"):
                    continue
                if not isinstance(fields, dict):
                    continue
                for field_name, value in fields.items():
                    if field_name.startswith("_"):
                        continue
                    fid = field_name  # Use field name as ID for generic
                    state[fid] = ExtractionResult(
                        field_id=fid,
                        field_name=field_name,
                        extracted_value=str(value),
                        resolved_code=str(value),
                        confidence=0.5,  # Unknown confidence from old format
                        evidence_text="",
                        source_chunk_id="prior",
                        source_chunk_type="prior",
                        pass_number=0,
                    )

        return state

    def _internal_to_list(self, state: dict[str, ExtractionResult]) -> list[dict]:
        """Convert internal ExtractionResult state to list[dict] format.

        Groups results by ontology_id and category for backward compatibility.
        Also embeds the full ExtractionResult metadata for round-trip fidelity.
        """
        if not state:
            return []

        # Group by ontology
        by_ontology: dict[str, dict[str, str]] = {}
        for fid, result in state.items():
            oid = result.ontology_id or "extraction"
            if oid not in by_ontology:
                by_ontology[oid] = {}
            # Use field_name as key for the output dict
            by_ontology[oid][result.field_name] = result.resolved_code or result.extracted_value

        # Build list[dict] format
        output: list[dict] = []
        for oid, fields in by_ontology.items():
            output.append({oid: fields})

        # Embed metadata for round-trip
        metadata = {fid: result.to_dict() for fid, result in state.items()}
        output.append({"_extraction_results": metadata})

        return output

    # ------------------------------------------------------------------
    # Multi-diagnosis format conversion
    # ------------------------------------------------------------------

    def _list_to_internal_multi(
        self,
        running: list[dict],
    ) -> tuple[
        dict[str, ExtractionResult],        # patient_state
        dict[int, dict[str, ExtractionResult]],  # diagnosis_states
        list[DiagnosisInfo],                # discovered diagnoses
        dict[str, list[dict[str, str]]],    # multi_instance_data
    ]:
        """Reconstruct multi-diagnosis state from the list[dict] output format."""
        patient_state: dict[str, ExtractionResult] = {}
        diagnosis_states: dict[int, dict[str, ExtractionResult]] = {}
        discovered: list[DiagnosisInfo] = []
        multi_instance_data: dict[str, list[dict[str, str]]] = {}

        if not running:
            return patient_state, diagnosis_states, discovered, multi_instance_data

        for entry in running:
            if not isinstance(entry, dict):
                continue

            # Discovered diagnoses
            if "_discovered_diagnoses" in entry:
                for d in entry["_discovered_diagnoses"]:
                    discovered.append(DiagnosisInfo.from_dict(d))
                continue

            # Multi-instance data (regimens, assessments, etc.)
            if "_multi_instance" in entry:
                for mi_key, instances in entry["_multi_instance"].items():
                    if isinstance(instances, list):
                        multi_instance_data[mi_key] = instances
                continue

            # Multi-diagnosis metadata
            if "_extraction_results" in entry:
                er = entry["_extraction_results"]
                if "patient" in er:
                    # Multi-diagnosis format
                    for fid, rd in er.get("patient", {}).items():
                        patient_state[fid] = ExtractionResult.from_dict(rd)
                    for key, results_dict in er.items():
                        if key.startswith("diagnosis_"):
                            tidx = int(key.split("_", 1)[1])
                            if tidx not in diagnosis_states:
                                diagnosis_states[tidx] = {}
                            for fid, rd in results_dict.items():
                                diagnosis_states[tidx][fid] = ExtractionResult.from_dict(rd)
                else:
                    # Legacy single-diagnosis format -- treat all as diagnosis 0
                    for fid, rd in er.items():
                        r = ExtractionResult.from_dict(rd)
                        if fid in _PATIENT_LEVEL_FIELD_IDS:
                            patient_state[fid] = r
                        else:
                            if 0 not in diagnosis_states:
                                diagnosis_states[0] = {}
                            diagnosis_states[0][fid] = r
                continue

            # Per-diagnosis fields
            if "_diagnoses" in entry:
                for diag_entry in entry["_diagnoses"]:
                    tidx = diag_entry.get("tumor_index", 0)
                    if tidx not in diagnosis_states:
                        diagnosis_states[tidx] = {}
                    # Values are already in diagnosis_states via metadata
                continue

            # Patient-level fields (ontology dicts at top level)
            for category, fields in entry.items():
                if category.startswith("_") or not isinstance(fields, dict):
                    continue
                for field_name, value in fields.items():
                    if field_name.startswith("_"):
                        continue
                    patient_state[field_name] = ExtractionResult(
                        field_id=field_name,
                        field_name=field_name,
                        extracted_value=str(value),
                        resolved_code=str(value),
                        confidence=0.5,
                        evidence_text="",
                        source_chunk_id="prior",
                        source_chunk_type="prior",
                        pass_number=0,
                    )

        return patient_state, diagnosis_states, discovered, multi_instance_data

    def _internal_to_list_multi(
        self,
        patient_state: dict[str, ExtractionResult],
        diagnosis_states: dict[int, dict[str, ExtractionResult]],
        discovered: list[DiagnosisInfo],
        multi_instance_data: dict[str, list[dict[str, str]]] | None = None,
    ) -> list[dict]:
        """Convert multi-diagnosis state to list[dict] for checkpointing.

        Output format::

            [
                {oid: {patient_field: value, ...}},
                {"_diagnoses": [
                    {"tumor_index": 0, oid: {field: value}},
                    {"tumor_index": 1, oid: {field: value}},
                ]},
                {"_multi_instance": {
                    "0_regimen": [{field: value}, ...],
                }},
                {"_extraction_results": {
                    "patient": {fid: result_dict, ...},
                    "diagnosis_0": {fid: result_dict, ...},
                }},
                {"_discovered_diagnoses": [diag_dict, ...]},
            ]
        """
        output: list[dict] = []

        # Patient-level fields grouped by ontology
        by_ontology: dict[str, dict[str, str]] = {}
        for fid, result in patient_state.items():
            oid = result.ontology_id or "extraction"
            if oid not in by_ontology:
                by_ontology[oid] = {}
            by_ontology[oid][result.field_name] = result.resolved_code or result.extracted_value
        for oid, fields in by_ontology.items():
            output.append({oid: fields})

        # Per-diagnosis fields
        diagnoses_list: list[dict] = []
        for tidx in sorted(diagnosis_states.keys()):
            diag_entry: dict[str, Any] = {"tumor_index": tidx}
            by_ont: dict[str, dict[str, str]] = {}
            for fid, result in diagnosis_states[tidx].items():
                oid = result.ontology_id or "extraction"
                if oid not in by_ont:
                    by_ont[oid] = {}
                by_ont[oid][result.field_name] = result.resolved_code or result.extracted_value
            diag_entry.update(by_ont)
            diagnoses_list.append(diag_entry)
        output.append({"_diagnoses": diagnoses_list})

        # Multi-instance data (regimens, assessments, etc.)
        if multi_instance_data:
            output.append({"_multi_instance": multi_instance_data})

        # Metadata for round-trip
        metadata: dict[str, dict[str, dict]] = {}
        metadata["patient"] = {fid: r.to_dict() for fid, r in patient_state.items()}
        for tidx, dstate in diagnosis_states.items():
            metadata[f"diagnosis_{tidx}"] = {fid: r.to_dict() for fid, r in dstate.items()}
        output.append({"_extraction_results": metadata})

        # Persist discovered diagnoses for subsequent chunks
        output.append({"_discovered_diagnoses": [d.to_dict() for d in discovered]})

        return output


# Set of NAACCR field IDs that are patient-level (for legacy format detection)
_PATIENT_LEVEL_FIELD_IDS = {
    "150", "160", "161", "190", "220", "240", "252", "254",
}


# ---------------------------------------------------------------------------
# SummaryExtractor (preserved unchanged)
# ---------------------------------------------------------------------------

class SummaryExtractor:
    """Free-text clinical summary extractor.

    Produces a running free-text summary instead of structured JSON.
    Uses the clinical_summary ontology's prompt templates for iterative
    summarization across chunks.

    The running state is a plain string (the summary so far) rather than
    a list of dicts.  To fit into the same ``ChunkedExtractor`` pipeline,
    results are wrapped as ``[{"clinical_summary": {"summary": text}}]``.
    """

    def __init__(self, llm_client: LLMClient, cancer_type: Optional[str] = "generic"):
        self.llm_client = llm_client
        self.cancer_type = cancer_type
        _registry = OntologyRegistry()
        _registry.discover()
        self._ontology = _registry.get("clinical_summary")
        self._first_chunk_template = (
            "{system_prompt}\n\n"
            "Here is the clinical document for this patient:\n\n"
            "<DOCUMENT>\n{chunk_text}\n</DOCUMENT>\n\n"
            "Now, write your clinical summary. Do not add preceding text "
            "before the summary, and do not add commentary afterwards."
        )
        self._update_chunk_template = (
            "{system_prompt}\n\n"
            "You previously wrote the following summary based on earlier "
            "portions of this patient's clinical record:\n\n"
            "<PRIOR_SUMMARY>\n{prior_summary}\n</PRIOR_SUMMARY>\n\n"
            "Here is the next portion of the patient's clinical record:\n\n"
            "<DOCUMENT>\n{chunk_text}\n</DOCUMENT>\n\n"
            "Update the summary to incorporate any new relevant information "
            "from this segment.\n"
            "- If the segment contains no new information, output the prior "
            "summary exactly as-is.\n"
            "- Maintain the same format and structure.\n"
            "- Do not add preceding text before the summary, and do not add "
            "commentary afterwards.\n\n"
            "Write the updated summary:"
        )

    def _system_prompt(self) -> str:
        return self._ontology.format_for_prompt(self.cancer_type)

    def extract_from_text(self, text: str, cancer_type: Optional[str] = None, max_tokens: Optional[int] = 8000) -> list[dict]:
        prompt = self._first_chunk_template.format(
            system_prompt=self._system_prompt(),
            chunk_text=text,
        )
        response = self.llm_client.generate(prompt, max_tokens=max_tokens)
        return _wrap_summary(response.text)

    def extract_single_chunk(self, chunk_text: str, running: Optional[list[dict]] = None, chunk_index: int = 0, total_chunks: int = 1, cancer_type: Optional[str] = None, max_tokens: Optional[int] = 8000, max_retries: int = 3) -> list[dict]:
        prior_summary = _unwrap_summary(running)

        if chunk_index == 0 and not prior_summary:
            prompt = self._first_chunk_template.format(
                system_prompt=self._system_prompt(),
                chunk_text=chunk_text,
            )
        else:
            prompt = self._update_chunk_template.format(
                system_prompt=self._system_prompt(),
                prior_summary=prior_summary,
                chunk_text=chunk_text,
            )

        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate(prompt, max_tokens=max_tokens)
                summary_text = response.text.strip()
                if summary_text:
                    return _wrap_summary(summary_text)
            except Exception:
                logger.exception(
                    "Summary chunk %d/%d: LLM call failed (attempt %d/%d)",
                    chunk_index + 1, total_chunks, attempt + 1, max_retries,
                )

        logger.warning(
            "Summary chunk %d/%d: all retries failed, keeping previous summary",
            chunk_index + 1, total_chunks,
        )
        return running if running else _wrap_summary("")

    def extract_iterative(self, texts: list[str], cancer_type: Optional[str] = None, max_tokens: Optional[int] = 8000, max_retries: int = 3) -> list[dict]:
        running: list[dict] = []
        for i, chunk_text in enumerate(texts):
            running = self.extract_single_chunk(
                chunk_text, running, i, len(texts),
                cancer_type, max_tokens, max_retries,
            )
        return running


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wrap_summary(text: str) -> list[dict]:
    return [{"clinical_summary": {"summary": text.strip()}}]


def _unwrap_summary(running: Optional[list[dict]]) -> str:
    if not running:
        return ""
    for entry in running:
        if isinstance(entry, dict) and "clinical_summary" in entry:
            return entry["clinical_summary"].get("summary", "")
    return ""


def is_summary_only(ontology_ids: list[str]) -> bool:
    """Check if the ontology list consists solely of free-text ontologies."""
    if not ontology_ids:
        return False
    registry = OntologyRegistry()
    registry.discover()
    for oid in ontology_ids:
        ont = registry.get(oid)
        if ont is None or not ont.is_free_text:
            return False
    return True


def create_extractor(
    llm_client: LLMClient,
    ontology_ids: list[str],
    cancer_type: Optional[str] = "generic",
    items_per_call: int = DEFAULT_ITEMS_PER_CALL,
    questions: Optional[list[dict]] = None,
    **kwargs,
):
    """Factory that returns the appropriate extractor based on ontology types."""
    if questions is not None:
        from .qa_extractor import QAExtractor
        return QAExtractor(llm_client, questions)
    if is_summary_only(ontology_ids):
        return SummaryExtractor(llm_client, cancer_type)
    return Extractor(llm_client, ontology_ids, cancer_type, items_per_call)
