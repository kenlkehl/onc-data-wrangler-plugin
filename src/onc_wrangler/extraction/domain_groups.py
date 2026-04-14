"""Domain group definitions for consolidated extraction.

NAACCR domain groups are hand-curated with expert prompts ported from the
onc-registry-extraction pipeline.  Non-NAACCR ontologies get auto-generated
domain groups from their ``DataCategory`` objects.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..ontologies.protocols import DomainGroup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NAACCR item number lists (from the registry extraction pipeline)
# ---------------------------------------------------------------------------

DEMOGRAPHICS_ITEMS = [
    380, 390, 400, 410, 440, 441, 442, 449, 450, 470, 490, 500, 522, 523,
    150, 160, 161, 190, 220, 230, 240, 252, 254,
]

# Patient-level items: extracted once, shared across all diagnoses
PATIENT_LEVEL_ITEMS = [
    150, 160, 161, 190,   # Race 1-3, Spanish/Hispanic Origin
    220,                   # Sex
    240,                   # Date of Birth
    252, 254,             # Birthplace Country, State
]

# Diagnosis-level items from demographics: extracted per diagnosis
DIAGNOSIS_IDENTITY_ITEMS = [
    380,                   # Sequence Number--Central
    390,                   # Date of Diagnosis
    400,                   # Primary Site
    410,                   # Laterality
    440, 441, 442, 449, 450,  # Grade fields
    470, 490,             # Diagnostic Confirmation
    500,                   # Date of Diagnosis Flag
    522, 523,             # Histologic Type, Behavior Code
    230,                   # Age at Diagnosis (may differ per diagnosis)
]

SURGERY_ITEMS = [
    1200, 1290, 1291, 1292, 1294, 1296, 1310, 1320, 1330, 1340, 1350,
    1640, 3170, 3180, 3190,
]

RADIATION_ITEMS = [
    1210, 1360, 1370, 1380, 1430,
    1501, 1502, 1503, 1504, 1505, 1506, 1507,
    1511, 1512, 1513, 1514, 1515, 1516, 1517,
    1521, 1522, 1523, 1524, 1525, 1526, 1527,
    1531, 1532, 1533, 1550, 1570, 3220,
]

SYSTEMIC_ITEMS = [
    1220, 1230, 1240, 1250, 1285, 1390, 1400, 1410, 1420,
    1632, 1633, 1634, 1639, 3230, 3250, 3270,
]

FOLLOWUP_ITEMS = [1750, 1760, 1770, 1772, 1790, 1910]

TEXT_ITEMS = [
    2520, 2530, 2540, 2550, 2560, 2570, 2580, 2590,
    2600, 2610, 2620, 2630, 2640, 2650, 2660, 2670, 2680,
]


# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

CHUNK_USER_TEMPLATE = """\
Clinical text (dates: {first_date} to {last_date}):
---
{chunk_text}
---

{tumor_context}

{prior_state_block}

EXTRACTION GUARD RULES:
- If multiple cancers are present, extract ONLY for the diagnosis specified \
above. Ignore data belonging to other cancers.
- For staging fields: use ONLY information from the time of initial diagnosis. \
Do NOT incorporate later recurrence, progression, or metastatic events into \
the original staging.

Extract the following data items. For coded items, use ONLY the valid codes listed.
If an item was previously extracted with high confidence and this text provides no better
evidence, you may output the same value. Only update if this text provides STRONGER
evidence or a MORE SPECIFIC value.

{json_field_descriptions}"""


# ---------------------------------------------------------------------------
# Helper: build prior state block from generalized ExtractionResult
# ---------------------------------------------------------------------------

def build_prior_state_block(
    prior: dict[str, Any],
    field_ids: list[str] | None = None,
) -> str:
    """Format prior extraction state for prompts.

    Works with both NAACCR (int-keyed) and generic (string-keyed) results.
    """
    if not prior:
        return "No prior extraction state -- this is the first chunk."

    lines = ["PRIOR EXTRACTION STATE (update only with higher-confidence evidence):"]
    items_to_show = field_ids if field_ids else sorted(prior.keys())

    for fid in items_to_show:
        result = prior.get(fid) if isinstance(fid, str) else prior.get(str(fid))
        if result is None:
            continue
        confidence = getattr(result, "confidence", 0.0)
        if confidence <= 0.0:
            continue
        value = getattr(result, "resolved_code", "") or getattr(result, "extracted_value", "")
        if not value:
            continue
        name = getattr(result, "field_name", fid)
        lines.append(f"- {name}: {value} (confidence: {confidence:.2f})")

    if len(lines) == 1:
        return "No prior extraction state -- this is the first chunk."

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Consolidated extraction (single-call-per-diagnosis)
# ---------------------------------------------------------------------------

# Set of NAACCR text/narrative item numbers for per-item narrative detection
NARRATIVE_ITEM_IDS: set[str] = {str(n) for n in TEXT_ITEMS}
PATIENT_LEVEL_ITEM_IDS: set[str] = {str(n) for n in PATIENT_LEVEL_ITEMS}

CONSOLIDATED_SYSTEM_PROMPT = """\
You are an expert cancer registrar certified by the NCRA extracting comprehensive \
cancer registry data for a {primary_site_desc} cancer case \
(Primary Site: {primary_site}, Histology: {histology}).

{site_context}

=== DEMOGRAPHICS & CANCER IDENTIFICATION ===
1. Primary Site: ICD-O-3 topography code (C##.#). Do NOT confuse metastatic sites \
with primary.
2. Histologic Type: ICD-O-3 morphology code (4 digits, 8000-9989).
3. Behavior Code: 0=benign, 1=uncertain, 2=in situ, 3=malignant primary.
4. Date of Diagnosis: EARLIEST date cancer was first suspected/confirmed (YYYYMMDD).

=== STAGING & PROGNOSTIC FACTORS ===
STAGING TEMPORAL RULE (MANDATORY):
Cancer stage is defined ONCE at the time of initial diagnosis and MUST NOT \
change based on later events. When extracting staging data:
- Use ONLY staging information documented at or near the time of initial \
diagnosis (the date_of_diagnosis for this cancer).
- Do NOT incorporate later restaging, recurrence, progression, or new \
metastases into the initial stage.
- If the text mentions "restaging" or "upstaging" months/years after \
diagnosis, that is NOT the initial stage -- ignore it for staging fields.
- If a patient was initially Stage II and later developed metastases, the \
stage remains Stage II. The metastases are a disease EVENT, not a change \
to the original stage.
- Mets at DX fields: Record ONLY metastases documented at the time of \
diagnosis. Metastases discovered months or years later are NOT "mets at DX."
- If you see a stage mentioned in a later note (e.g., "Stage IV disease" \
in a note 2 years post-diagnosis), verify whether this refers to the \
ORIGINAL staging at diagnosis or a later assessment. Only use it if it \
clearly refers to the initial diagnosis.

EXAMPLES OF CORRECT vs INCORRECT STAGING:
- Patient diagnosed Stage IIA breast cancer 2019, develops bone mets 2021:
  CORRECT: Stage IIA, Mets at DX = none
  INCORRECT: Stage IV (incorporating the 2021 bone mets)
- Patient with "restaging CT shows progression" 6 months after diagnosis:
  CORRECT: Use the original staging from diagnosis workup
  INCORRECT: Update staging based on the restaging scan

STAGING RULES:
1. TNM: Distinguish clinical (c) from pathological (p) staging. Do not mix components.
2. Tumor Size: Record in millimeters. Pathological preferred over clinical.
3. Summary Stage 2018: 0=in situ, 1=localized, 2=regional direct extension, \
3=regional LN only, 4=regional both, 7=distant, 9=unknown.
4. EOD: Record primary tumor extent, regional nodes, and mets using valid codes.
5. Biomarkers: Extract exact values (e.g., ER 95%, PSA 4.2, Gleason 3+4=7).
6. Regional Nodes: 00=none examined, 01-89=exact count, 90=90+, 99=unknown.
7. Mets at DX: For each site (bone, brain, distant LN, liver, lung, other): \
0=none, 1=yes, 8=N/A, 9=unknown. Record ONLY mets present AT DIAGNOSIS.
8. TEMPORAL GUARD: If your evidence for a staging field comes from a date \
significantly after the date of diagnosis, lower your confidence to 0.3 or \
below and note "evidence may reflect post-diagnosis status" in the evidence field.

=== SURGICAL TREATMENT (First Course Only) ===
1. Surgery Date: YYYYMMDD of most definitive procedure.
2. Distinguish diagnostic procedures (biopsies) from definitive surgery.
3. LN Surgery Scope: 0=none, 1=biopsy, 2=sentinel, 3=unknown count, \
5=1-3 removed, 6=4+ removed, 7=sentinel+complete, 9=unknown.
4. Surgical Margins: 0=R0, 1=residual NOS, 2=R1, 3=R2, 8=no surgery, 9=unknown.

=== RADIATION TREATMENT (First Course Only) ===
1. Radiation Date: YYYYMMDD when radiation started.
2. RX Summ--Radiation: 0=none, 1=beam, 2=implants, 3=radioisotopes, 4=combo, 5=NOS, 9=unknown.
3. Up to 3 phases, each with: dose per fraction, fractions, total dose, modality, technique, volume.
4. Dose in cGy. Total = dose/fraction x fractions.

=== SYSTEMIC THERAPY (First Course Only) ===
1. Chemo Date: YYYYMMDD when started.
2. Chemo: 00=none, 01=NOS, 02=single, 03=multi-agent, 85=not recommended, 87=refused, 99=unknown.
3. Hormone: 00=none, 01=hormone therapy, 85=not recommended, 87=refused, 99=unknown.
4. BRM/Immunotherapy: 00=none, 01=BRM, 85=not recommended, 87=refused, 99=unknown.
5. Treatment Status: 0=none given, 1=completed, 2=incomplete, 9=unknown.
6. Neoadjuvant: 0=no, 1=yes, 9=unknown.

=== FOLLOW-UP & OUTCOMES ===
1. Date of Last Contact: Most recent date patient known alive or date of death (YYYYMMDD).
2. Vital Status: 0=Dead, 1=Alive.
3. Cancer Status: 1=no evidence of disease, 2=evidence of disease, 9=unknown.

=== NARRATIVE TEXT FIELDS ===
For items marked as narrative/text fields, compose concise factual summaries:
- Only include information found in the text.
- Each summary under 4000 characters.
- Use standard medical terminology.
- Include dates, measurements, specific findings.
- Do not include patient identifiers.

=== GENERAL RULES ===
1. For each item, rate confidence 0.0-1.0 and quote supporting evidence (max 200 chars).
2. Extract ONLY what is explicitly stated. Do not infer.

{json_format_instructions}"""


GENERIC_CONSOLIDATED_SYSTEM_PROMPT = """\
You are a clinical data extraction system specializing in structured data extraction \
from clinical notes. Extract all requested information for this patient.

{domain_context}

RULES:
1. Extract ONLY what is explicitly stated in the text. Do not infer.
2. For each item, rate your confidence 0.0-1.0.
3. Provide a short evidence quote (max 200 chars) from the text.
4. Use valid codes when provided. If not found, use "unknown" and confidence 0.0.
5. STAGING SCOPE: Fields with "at_diagnosis" or "at diagnosis" in their name \
or description refer to the cancer's status at the time of INITIAL DIAGNOSIS \
ONLY. Do NOT populate these with later restaging, recurrence, or progression data.
6. MULTI-DIAGNOSIS: When a tumor_context is provided, extract ONLY data \
pertaining to that specific diagnosis.
7. MULTI-INSTANCE DATA: For categories that can have multiple instances \
(e.g., treatment regimens, biomarker tests), return ALL instances as JSON \
arrays under the designated key. Return an empty array if none found.

{json_format_instructions}"""


def build_naaccr_consolidated_group() -> DomainGroup:
    """Return a single consolidated DomainGroup for NAACCR extraction.

    All single-instance items (patient demographics, diagnosis identity,
    surgery, radiation, systemic, follow-up, narratives) are in ``field_ids``.
    Staging items are appended dynamically after schema resolution.
    NAACCR has no multi-instance subgroups.
    """
    all_single_items = (
        PATIENT_LEVEL_ITEMS
        + DIAGNOSIS_IDENTITY_ITEMS
        + SURGERY_ITEMS
        + RADIATION_ITEMS
        + SYSTEMIC_ITEMS
        + FOLLOWUP_ITEMS
        + TEXT_ITEMS
    )
    # Deduplicate while preserving order
    seen: set[int] = set()
    deduped: list[int] = []
    for n in all_single_items:
        if n not in seen:
            seen.add(n)
            deduped.append(n)

    return DomainGroup(
        group_id="consolidated_all",
        name="Consolidated Extraction",
        field_ids=[str(n) for n in deduped],
        system_prompt_template=CONSOLIDATED_SYSTEM_PROMPT,
        depends_on=[],
        context_keys=[
            "primary_site", "histology",
            "primary_site_desc", "site_context",
        ],
        dynamic=True,  # staging items appended at runtime
        items_per_call=0,  # no batching — all items in one call
    )


def build_generic_consolidated_group(ontology: Any) -> DomainGroup:
    """Return a single consolidated DomainGroup for a generic ontology.

    All non-multi-instance categories are merged into one group's
    ``field_ids``.  Multi-instance categories become
    ``multi_instance_subgroups``.
    """
    single_field_ids: list[str] = []
    mi_subgroups: list[DomainGroup] = []
    seen_ids: set[str] = set()
    domain_contexts: list[str] = []

    categories = ontology.get_base_items()
    try:
        site_categories = ontology.get_site_specific_items("generic")
        categories = categories + site_categories
    except Exception:
        pass

    for cat in categories:
        if cat.id in seen_ids:
            continue
        seen_ids.add(cat.id)

        field_ids: list[str] = []
        for item in cat.items:
            fid = getattr(item, "json_field", None) or getattr(item, "id", None) or item.name
            field_ids.append(fid)

        is_multi = getattr(cat, "multi_instance", False)

        if is_multi:
            mi_subgroups.append(DomainGroup(
                group_id=cat.id,
                name=cat.name,
                field_ids=field_ids,
                system_prompt_template="",  # not used directly
                multi_instance=True,
            ))
        else:
            single_field_ids.extend(field_ids)

        ctx = getattr(cat, "context", "") or getattr(cat, "description", "") or ""
        if ctx:
            domain_contexts.append(f"{cat.name}: {ctx}")

    return DomainGroup(
        group_id="consolidated_all",
        name="Consolidated Extraction",
        field_ids=single_field_ids,
        system_prompt_template=GENERIC_CONSOLIDATED_SYSTEM_PROMPT,
        depends_on=[],
        context_keys=["domain_context"],
        items_per_call=0,
        multi_instance_subgroups=mi_subgroups,
    )
