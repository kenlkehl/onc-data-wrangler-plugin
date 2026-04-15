"""Synthetic NAACCR cancer registry generation.

Given a synthetic patient's generated events and documents, runs the
existing NAACCR extraction pipeline (``onc_wrangler.extraction``) on the
documents and converts the output into the NAACCRWriter-compatible
``{item_number_str: resolved_code}`` shape used downstream.

This deliberately reuses the registrar-grade extractor rather than
writing a parallel "synthetic registrar" prompt so the synthetic NAACCR
records are generated the same way real data is extracted (useful as
ground-truth for benchmarking the extractor too).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from onc_wrangler.extraction.extractor import create_extractor
from onc_wrangler.extraction.result import ExtractionResult
from onc_wrangler.llm.base import LLMClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cancer-type resolution from Stage-1 events
# ---------------------------------------------------------------------------

# Keyword -> NAACCR schema id. Keys are matched case-insensitively against
# the diagnosis event text. Schema ids must match those in
# ``data/ontologies/naaccr/schemas.yaml``.
_CANCER_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    (r"\bbreast\b", "breast"),
    (r"\bprostate\b", "prostate"),
    (r"\blung\b|\bNSCLC\b|\bSCLC\b|\bbronch", "lung"),
    (r"\bcolon\b|\bcolorectal\b|\brectum\b|\brectal\b", "colon_rectum"),
    (r"\bpancreas\b|\bpancreatic\b", "pancreas"),
    (r"\bliver\b|\bhepatocellular\b|\bHCC\b", "liver"),
    (r"\bmelanoma\b", "melanoma"),
    (r"\bovar(?:y|ian)\b", "ovary"),
    (r"\bendomet", "endometrium"),
    (r"\bcerv(?:ix|ical)\b", "cervix"),
    (r"\bkidney\b|\brenal\b", "kidney"),
    (r"\bbladder\b", "bladder"),
    (r"\bthyroid\b", "thyroid"),
    (r"\bbrain\b|\bglio", "brain"),
    (r"\blymphoma\b|\bHodgkin\b|\bDLBCL\b", "lymphoma"),
    (r"\bleukemia\b|\bAML\b|\bALL\b|\bCLL\b|\bCML\b", "leukemia"),
    (r"\bmyeloma\b", "myeloma"),
    (r"\bstomach\b|\bgastric\b", "stomach"),
    (r"\besophag", "esophagus"),
    (r"\btestic", "testis"),
    (r"\bhead and neck\b|\boropharynx\b|\blarynx\b", "head_and_neck"),
)


def resolve_cancer_type_from_events(events: list[dict]) -> str:
    """Pick a NAACCR schema hint from the Stage-1 events.

    Scans diagnosis (and adjacent) event text for site keywords and
    returns the first match. Falls back to ``"generic"``.
    """
    if not events:
        return "generic"
    haystack_parts = []
    for e in events:
        t = e.get("type", "")
        text = e.get("text", "")
        if t in {"diagnosis", "pathology_report", "ngs_report", "demographics"}:
            haystack_parts.append(text)
    if not haystack_parts:
        haystack_parts = [e.get("text", "") for e in events]
    haystack = "\n".join(haystack_parts)
    for pat, schema in _CANCER_TYPE_KEYWORDS:
        if re.search(pat, haystack, flags=re.IGNORECASE):
            return schema
    return "generic"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _documents_to_chunks(documents: list[dict]) -> list[str]:
    """Render generated documents as plain text chunks for the extractor."""
    chunks: list[str] = []
    for doc in documents:
        etype = doc.get("event_type", "document")
        idx = doc.get("event_index", "?")
        text = doc.get("text", "")
        if not text.strip():
            continue
        chunks.append(
            f"=== DOCUMENT ({etype}, event {idx}) ===\n{text}\n"
        )
    return chunks


def extract_registry_record(
    client: LLMClient,
    patient_id: str,
    events: list[dict],
    documents: list[dict],
    dictionary: Optional[Any] = None,
    cancer_type: Optional[str] = None,
) -> dict[str, str]:
    """Run the NAACCR extractor on a synthetic patient's documents.

    Returns a ``{item_number_str: resolved_code}`` dict — the shape
    consumed by :class:`NAACCRWriter`. Multi-diagnosis patients collapse
    to the primary diagnosis (tumor_index=0); other tumors are dropped.

    Args:
        client: LLM client (same one used for synthetic generation).
        patient_id: Patient identifier (used only for logging).
        events: Stage-1 event list; used to hint cancer_type.
        documents: Generated documents from Stage 2.
        dictionary: Preloaded ``NAACCRDictionary`` (optional; the
            extractor will look one up via ``OntologyRegistry`` if None).
        cancer_type: Override cancer-type hint. If None, resolved from
            events.
    """
    chunks = _documents_to_chunks(documents)
    if not chunks:
        logger.info("No documents available for %s; skipping registry extraction", patient_id)
        return {}

    ct = cancer_type or resolve_cancer_type_from_events(events)
    logger.info(
        "Extracting NAACCR record for %s (cancer_type=%s, %d chunks)",
        patient_id, ct, len(chunks),
    )

    extractor = create_extractor(
        llm_client=client,
        ontology_ids=["naaccr"],
        cancer_type=ct,
    )
    result_list = extractor.extract_iterative(chunks, cancer_type=ct)
    return _extraction_to_naaccr_dict(result_list)


def _extraction_to_naaccr_dict(
    result_list: list[dict],
) -> dict[str, str]:
    """Post-process ``extract_iterative`` output into writer input shape.

    Walks the ``_extraction_results`` metadata entry, pulls the
    ``resolved_code`` off each :class:`ExtractionResult`, and merges
    patient-level fields with diagnosis_0 (primary tumor) fields.
    """
    metadata: dict[str, dict[str, dict]] = {}
    for entry in result_list:
        if isinstance(entry, dict) and "_extraction_results" in entry:
            metadata = entry["_extraction_results"]
            break

    if not metadata:
        return {}

    out: dict[str, str] = {}

    # Patient-level fields.
    for fid, result_dict in metadata.get("patient", {}).items():
        code = _code_from_result_dict(result_dict)
        if code:
            out[str(fid)] = code

    # Primary diagnosis (tumor_index=0). If absent, fall back to the
    # lowest-indexed diagnosis available.
    diag_key = "diagnosis_0"
    if diag_key not in metadata:
        diag_candidates = sorted(
            k for k in metadata if k.startswith("diagnosis_")
        )
        if diag_candidates:
            diag_key = diag_candidates[0]
    for fid, result_dict in metadata.get(diag_key, {}).items():
        code = _code_from_result_dict(result_dict)
        if code:
            out[str(fid)] = code

    return out


def _code_from_result_dict(raw: dict) -> str:
    """Pull the best code-like value off a serialized ExtractionResult."""
    try:
        r = ExtractionResult.from_dict(raw)
    except Exception:
        return ""
    return (r.resolved_code or r.extracted_value or "").strip()
