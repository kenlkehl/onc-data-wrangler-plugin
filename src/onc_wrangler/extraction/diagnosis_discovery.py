"""Diagnosis discovery phase for multi-diagnosis extraction.

Before extracting domain-group items, this module asks the LLM to identify
all distinct primary cancer diagnoses in a patient's notes.  Each discovered
diagnosis drives a separate per-diagnosis extraction loop with its own schema
resolution and site-specific staging items.

Uses a two-step approach for reliability:
  Step 1: Plain-language identification of diagnoses (no ICD-O-3 codes)
  Step 2: ICD-O-3 code resolution with reference data injection
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

from ..llm.base import LLMClient
from .icdo3_lookup import get_icdo3_reference

logger = logging.getLogger(__name__)


def _parse_json_list(text: str) -> list[dict] | None:
    """Best-effort parse of a JSON array from LLM output.

    Handles cases where JSON mode returns a single object instead of an array,
    or wraps the array inside an object (e.g. {"diagnoses": [...]}).
    """
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
        if isinstance(result, list):
            return result
        # Handle single object → wrap in list
        if isinstance(result, dict):
            # Check if it wraps a list (e.g. {"diagnoses": [...]})
            for v in result.values():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    return v
            # Single diagnosis object → wrap in list
            if "tumor_index" in result or "primary_site" in result or "site_description" in result:
                return [result]
    except json.JSONDecodeError:
        pass
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    return None


@dataclass
class DiagnosisInfo:
    """A single cancer diagnosis discovered from patient notes."""

    tumor_index: int
    primary_site: str = ""                # ICD-O-3 topography code, e.g. "C50.9"
    primary_site_description: str = ""    # e.g. "breast"
    histology: str = ""                   # ICD-O-3 morphology code, e.g. "8500"
    histology_description: str = ""       # e.g. "infiltrating duct carcinoma"
    date_of_diagnosis: str = ""           # YYYYMMDD
    laterality: str = ""                  # left/right/bilateral/not applicable
    confidence: float = 0.0
    evidence: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> DiagnosisInfo:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class _PlainLanguageDiagnosis:
    """Internal: step 1 output before code resolution."""

    tumor_index: int
    site_description: str = ""
    histology_description: str = ""
    date_of_diagnosis: str = ""
    laterality: str = ""
    confidence: float = 0.0
    evidence: str = ""


def _unknown_diagnosis() -> list[DiagnosisInfo]:
    """Fallback: a single diagnosis with no identity information."""
    return [DiagnosisInfo(tumor_index=0)]


def _build_corrective_prompt(base_prompt: str, failed_response: str) -> str:
    """Build a corrective re-prompt that includes the failed output.

    Shows the model its previous response and asks it to fix the JSON formatting.
    """
    failed_text = failed_response[:2000] if len(failed_response) > 2000 else failed_response
    return (
        base_prompt
        + "\n\n--- PREVIOUS ATTEMPT FAILED ---\n"
        "Your previous response could not be parsed as valid JSON. "
        "Here is what you returned:\n\n"
        + failed_text
        + "\n\nPlease try again and return ONLY a valid JSON array. "
        "Do not include any text, explanation, or markdown formatting outside the JSON."
    )


# --------------------------------------------------------------------------
# Legacy single-call prompt (kept for reference / A-B comparison)
# --------------------------------------------------------------------------

_LEGACY_DISCOVERY_PROMPT = """\
You are an expert cancer registrar certified by the NCRA. Your task is to \
identify every DISTINCT primary cancer diagnosis mentioned in the clinical \
text for a single patient.

CRITICAL RULES:
1. A PRIMARY cancer is one that originated at its anatomic site. Metastases \
are NOT separate primaries (e.g., liver metastasis from colon cancer is still \
ONE colon cancer diagnosis, not a separate liver cancer).
2. A RECURRENCE of the same cancer (same site and histology) is NOT a new \
diagnosis. It is still the same tumor_index.
3. A truly NEW primary cancer at a different site (e.g., breast cancer AND \
lung cancer) IS a separate diagnosis with its own tumor_index.
4. If a patient has bilateral cancers of a paired organ (e.g., left breast \
and right breast), treat each side as a separate diagnosis ONLY if they are \
documented as independent primaries (not contralateral spread).
5. Order diagnoses by date_of_diagnosis (earliest first), starting at \
tumor_index 0.
6. If only ONE cancer is found, return a single-element array.
7. COMMON TRAPS -- do NOT create a new diagnosis for any of these:
   - "Lung metastasis from breast cancer" → still 1 breast cancer diagnosis
   - "Recurrent ovarian cancer" → still the original ovarian cancer
   - "Brain mets from NSCLC" → still 1 lung cancer diagnosis
   - "Disease progression with liver involvement" → same diagnosis
   - "Second-line treatment for relapsed lymphoma" → same lymphoma
   - "Restaging shows new bone lesions" → same diagnosis, not a new primary
8. A second primary IS a new diagnosis ONLY when the text explicitly states \
or clearly implies a NEW, INDEPENDENT cancer at a different site with its \
own histology. Look for language like "new primary," "second malignancy," \
"synchronous primary," or documentation of a biopsy-proven cancer at a \
site unrelated to the known cancer's pattern of spread.
9. When uncertain whether a mentioned cancer site is a metastasis or a new \
primary, default to treating it as a metastasis of the existing cancer \
UNLESS there is explicit documentation of an independent primary. Set \
confidence lower (0.5-0.7) and note the ambiguity in the evidence field.

For each diagnosis, extract:
- tumor_index: integer starting at 0
- primary_site: ICD-O-3 topography code (C##.#)
- primary_site_description: plain-English site name
- histology: ICD-O-3 morphology code (4 digits, 8000-9989)
- histology_description: plain-English histology name
- date_of_diagnosis: YYYYMMDD (use 99 for unknown day/month parts)
- laterality: "left", "right", "bilateral", "midline", or "not_applicable"
- confidence: 0.0-1.0 indicating how certain you are this is a distinct primary
- evidence: short quote (max 200 chars) from the text supporting this diagnosis

Respond with ONLY a JSON array of objects. Example:
[
  {
    "tumor_index": 0,
    "primary_site": "C50.9",
    "primary_site_description": "breast",
    "histology": "8500",
    "histology_description": "infiltrating duct carcinoma",
    "date_of_diagnosis": "20190315",
    "laterality": "left",
    "confidence": 0.95,
    "evidence": "Left breast IDC diagnosed March 2019"
  }
]"""


# --------------------------------------------------------------------------
# Step 1: Plain-language discovery prompt (no ICD-O-3 codes required)
# --------------------------------------------------------------------------

DISCOVERY_STEP1_SYSTEM_PROMPT = """\
You are an expert cancer registrar certified by the NCRA. Your task is to \
identify every DISTINCT primary cancer diagnosis mentioned in the clinical \
text for a single patient.

CRITICAL RULES:
1. A PRIMARY cancer is one that originated at its anatomic site. Metastases \
are NOT separate primaries (e.g., liver metastasis from colon cancer is still \
ONE colon cancer diagnosis, not a separate liver cancer).
2. A RECURRENCE of the same cancer (same site and histology) is NOT a new \
diagnosis. It is still the same tumor_index.
3. A truly NEW primary cancer at a different site (e.g., breast cancer AND \
lung cancer) IS a separate diagnosis with its own tumor_index.
4. If a patient has bilateral cancers of a paired organ (e.g., left breast \
and right breast), treat each side as a separate diagnosis ONLY if they are \
documented as independent primaries (not contralateral spread).
5. Order diagnoses by date_of_diagnosis (earliest first), starting at \
tumor_index 0.
6. If only ONE cancer is found, return a single-element array.
7. COMMON TRAPS -- do NOT create a new diagnosis for any of these:
   - "Lung metastasis from breast cancer" → still 1 breast cancer diagnosis
   - "Recurrent ovarian cancer" → still the original ovarian cancer
   - "Brain mets from NSCLC" → still 1 lung cancer diagnosis
   - "Disease progression with liver involvement" → same diagnosis
   - "Second-line treatment for relapsed lymphoma" → same lymphoma
   - "Restaging shows new bone lesions" → same diagnosis, not a new primary
8. A second primary IS a new diagnosis ONLY when the text explicitly states \
or clearly implies a NEW, INDEPENDENT cancer at a different site with its \
own histology. Look for language like "new primary," "second malignancy," \
"synchronous primary," or documentation of a biopsy-proven cancer at a \
site unrelated to the known cancer's pattern of spread.
9. When uncertain whether a mentioned cancer site is a metastasis or a new \
primary, default to treating it as a metastasis of the existing cancer \
UNLESS there is explicit documentation of an independent primary. Set \
confidence lower (0.5-0.7) and note the ambiguity in the evidence field.

For each diagnosis, extract using PLAIN ENGLISH (no ICD-O-3 codes):
- tumor_index: integer starting at 0
- site_description: plain-English anatomic site, as specific as possible \
(e.g., "left lower lobe of lung", "sigmoid colon", "right breast upper outer \
quadrant"). Include laterality in the description if applicable.
- histology_description: plain-English histology name with subtype details \
if documented (e.g., "adenocarcinoma", "squamous cell carcinoma", \
"infiltrating duct carcinoma", "diffuse large B-cell lymphoma", \
"epithelioid mesothelioma")
- date_of_diagnosis: YYYYMMDD (use 99 for unknown day/month parts)
- laterality: "left", "right", "bilateral", "midline", or "not_applicable"
- confidence: 0.0-1.0 indicating how certain you are this is a distinct primary
- evidence: short quote (max 200 chars) from the text supporting this diagnosis

Do NOT include ICD-O-3 codes. Use plain English descriptions only.

Respond with ONLY a JSON array of objects. Example:
[
  {
    "tumor_index": 0,
    "site_description": "left breast",
    "histology_description": "infiltrating duct carcinoma",
    "date_of_diagnosis": "20190315",
    "laterality": "left",
    "confidence": 0.95,
    "evidence": "Left breast IDC diagnosed March 2019"
  }
]"""

DISCOVERY_STEP1_USER_TEMPLATE = """\
Clinical text for one patient:
---
{patient_text}
---

Identify ALL distinct primary cancer diagnoses in this text. Return a JSON \
array as described in the instructions. Use plain English only, no codes."""


# --------------------------------------------------------------------------
# Step 2: Code resolution prompt (with ICD-O-3 reference injection)
# --------------------------------------------------------------------------

DISCOVERY_STEP2_SYSTEM_PROMPT = """\
You are an expert cancer registrar certified by the NCRA. Your task is to \
assign ICD-O-3 codes to cancer diagnoses that have already been identified.

For each diagnosis below, assign:
- primary_site: The most specific ICD-O-3 topography code (format C##.#) \
for the anatomic site
- histology: The ICD-O-3 morphology code (4 digits, 8000-9989) for the \
histologic type

RULES:
1. Choose the MOST SPECIFIC code that matches the description.
2. If the exact subsite is unknown, use the .9 (NOS) code for that site \
(e.g., C34.9 for lung NOS).
3. If the histology description does not exactly match any reference code, \
choose the closest match.
4. If you are confident in a code that is NOT in the reference list, you \
may use it -- but prefer reference codes when they match.
5. Return the same number of diagnoses in the same order as provided.

Respond with ONLY a JSON array of objects with these fields:
- tumor_index: (same as input)
- primary_site: ICD-O-3 topography code (C##.#)
- primary_site_description: plain-English site name (echo from input)
- histology: ICD-O-3 morphology code (4 digits)
- histology_description: plain-English histology name (echo from input)

Example:
[
  {
    "tumor_index": 0,
    "primary_site": "C34.3",
    "primary_site_description": "left lower lobe of lung",
    "histology": "8140",
    "histology_description": "adenocarcinoma"
  }
]"""

DISCOVERY_STEP2_USER_TEMPLATE = """\
Diagnoses to assign codes to:
{diagnoses_json}

ICD-O-3 TOPOGRAPHY REFERENCE (choose the best match):
{topography_reference}

ICD-O-3 MORPHOLOGY/HISTOLOGY REFERENCE (choose the best match):
{morphology_reference}

Assign the most appropriate ICD-O-3 codes to each diagnosis. Return a JSON array."""


# --------------------------------------------------------------------------
# Public API (unchanged signature)
# --------------------------------------------------------------------------

def discover_diagnoses(
    llm_client: LLMClient,
    patient_text: str,
    max_tokens: int = 4096,
    max_retries: int = 3,
) -> list[DiagnosisInfo]:
    """Identify all distinct cancer diagnoses from patient text.

    Uses a two-step approach:
      1. Plain-language identification of diagnoses (no codes)
      2. ICD-O-3 code resolution with reference data injection

    Returns at least one :class:`DiagnosisInfo`.  Falls back to a single
    unknown diagnosis on parse failure.
    """
    if not patient_text or len(patient_text.strip()) < 20:
        return _unknown_diagnosis()

    # Discovery steps use more retries than the caller's max_retries since
    # these are cheaper calls and Gemma4 sometimes returns garbage responses
    # (e.g., echoing "thought" instead of JSON).
    discovery_retries = max(max_retries, 5)

    # --- Step 1: Plain-language discovery ---
    plain_diagnoses = _discover_plain_language(
        llm_client, patient_text, max_tokens, discovery_retries,
    )
    if not plain_diagnoses:
        return _unknown_diagnosis()

    # --- Step 2: Code resolution with reference data ---
    coded_diagnoses = _resolve_codes(
        llm_client, plain_diagnoses, max_tokens, discovery_retries,
    )
    if not coded_diagnoses:
        # Graceful degradation: use plain-language results without codes
        logger.warning(
            "Code resolution failed; returning %d diagnosis(es) without ICD-O-3 codes",
            len(plain_diagnoses),
        )
        return _plain_to_diagnosis_info(plain_diagnoses)

    return coded_diagnoses


# --------------------------------------------------------------------------
# Step 1 implementation
# --------------------------------------------------------------------------

def _discover_plain_language(
    llm_client: LLMClient,
    patient_text: str,
    max_tokens: int,
    max_retries: int,
) -> list[_PlainLanguageDiagnosis]:
    """Step 1: Identify diagnoses in plain language (no codes)."""
    base_prompt = (
        DISCOVERY_STEP1_SYSTEM_PROMPT
        + "\n\n"
        + DISCOVERY_STEP1_USER_TEMPLATE.format(patient_text=patient_text)
    )
    prompt = base_prompt

    for attempt in range(max_retries):
        try:
            response = llm_client.generate_structured(prompt, max_tokens=max_tokens)
            parsed = _parse_json_list(response.text)
            if parsed is not None and len(parsed) > 0:
                diagnoses = _parse_plain_language_list(parsed)
                if diagnoses:
                    logger.info(
                        "Step 1: discovered %d diagnosis(es) from patient text",
                        len(diagnoses),
                    )
                    return diagnoses
            logger.warning(
                "Step 1 diagnosis discovery parse failed (attempt %d/%d). Raw response (first 500 chars): %s",
                attempt + 1,
                max_retries,
                response.text[:500] if response.text else "(empty)",
            )
            # Corrective re-prompt: show the model its failed output
            prompt = _build_corrective_prompt(base_prompt, response.text)
        except Exception:
            logger.exception(
                "Step 1 diagnosis discovery LLM call failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
            )
            prompt = base_prompt  # Reset prompt on LLM error

    logger.warning(
        "Step 1 diagnosis discovery failed after %d retries",
        max_retries,
    )
    return []


# --------------------------------------------------------------------------
# Step 2 implementation
# --------------------------------------------------------------------------

def _resolve_codes(
    llm_client: LLMClient,
    plain_diagnoses: list[_PlainLanguageDiagnosis],
    max_tokens: int,
    max_retries: int,
) -> list[DiagnosisInfo]:
    """Step 2: Assign ICD-O-3 codes using reference data injection."""
    reference = get_icdo3_reference()

    # Collect unique site/histology descriptions for reference narrowing
    site_descs = list({d.site_description for d in plain_diagnoses if d.site_description})
    hist_descs = list({d.histology_description for d in plain_diagnoses if d.histology_description})

    topo_codes = reference.get_all_topography_for_descriptions(site_descs)
    morph_codes = reference.get_all_morphology_for_descriptions(hist_descs)

    from .icdo3_lookup import _format_code_list

    topography_ref = _format_code_list(topo_codes)
    morphology_ref = _format_code_list(morph_codes)

    # Format diagnoses as JSON for the prompt
    diag_dicts = [
        {
            "tumor_index": d.tumor_index,
            "site_description": d.site_description,
            "histology_description": d.histology_description,
        }
        for d in plain_diagnoses
    ]

    base_prompt = (
        DISCOVERY_STEP2_SYSTEM_PROMPT
        + "\n\n"
        + DISCOVERY_STEP2_USER_TEMPLATE.format(
            diagnoses_json=json.dumps(diag_dicts, indent=2),
            topography_reference=topography_ref,
            morphology_reference=morphology_ref,
        )
    )
    prompt = base_prompt

    for attempt in range(max_retries):
        try:
            response = llm_client.generate_structured(prompt, max_tokens=max_tokens)
            parsed = _parse_json_list(response.text)
            if parsed is not None and len(parsed) > 0:
                coded = _merge_codes_with_plain(parsed, plain_diagnoses)
                if coded:
                    logger.info(
                        "Step 2: resolved ICD-O-3 codes for %d diagnosis(es)",
                        len(coded),
                    )
                    return coded
            logger.warning(
                "Step 2 code resolution parse failed (attempt %d/%d). Raw response (first 500 chars): %s",
                attempt + 1,
                max_retries,
                response.text[:500] if response.text else "(empty)",
            )
            # Corrective re-prompt: show the model its failed output
            prompt = _build_corrective_prompt(base_prompt, response.text)
        except Exception:
            logger.exception(
                "Step 2 code resolution LLM call failed (attempt %d/%d)",
                attempt + 1,
                max_retries,
            )
            prompt = base_prompt  # Reset prompt on LLM error

    logger.warning(
        "Step 2 code resolution failed after %d retries",
        max_retries,
    )
    return []


# --------------------------------------------------------------------------
# Parsers and converters
# --------------------------------------------------------------------------

def _parse_plain_language_list(
    raw_list: list[dict[str, Any]],
) -> list[_PlainLanguageDiagnosis]:
    """Convert raw JSON list to _PlainLanguageDiagnosis objects."""
    diagnoses: list[_PlainLanguageDiagnosis] = []
    for i, entry in enumerate(raw_list):
        if not isinstance(entry, dict):
            continue
        diag = _PlainLanguageDiagnosis(
            tumor_index=i,
            site_description=str(entry.get("site_description", "")).strip(),
            histology_description=str(entry.get("histology_description", "")).strip(),
            date_of_diagnosis=str(entry.get("date_of_diagnosis", "")).strip(),
            laterality=str(entry.get("laterality", "")).strip(),
            confidence=float(entry.get("confidence", 0.5)),
            evidence=str(entry.get("evidence", "")).strip()[:300],
        )
        diagnoses.append(diag)
    return diagnoses


def _merge_codes_with_plain(
    coded_list: list[dict[str, Any]],
    plain_diagnoses: list[_PlainLanguageDiagnosis],
) -> list[DiagnosisInfo]:
    """Merge step 2 code results with step 1 metadata.

    Step 1 provides: date_of_diagnosis, laterality, confidence, evidence,
    site_description, histology_description.
    Step 2 provides: primary_site (C-code), histology (morphology code),
    and may echo descriptions.
    """
    # Build lookup by tumor_index for step 1 data
    plain_by_idx: dict[int, _PlainLanguageDiagnosis] = {
        d.tumor_index: d for d in plain_diagnoses
    }

    result: list[DiagnosisInfo] = []
    for i, coded in enumerate(coded_list):
        if not isinstance(coded, dict):
            continue

        # Match to step 1 data (prefer tumor_index, fall back to position)
        tidx = int(coded.get("tumor_index", i))
        plain = plain_by_idx.get(tidx)
        if plain is None and i < len(plain_diagnoses):
            plain = plain_diagnoses[i]
        if plain is None:
            plain = _PlainLanguageDiagnosis(tumor_index=tidx)

        diag = DiagnosisInfo(
            tumor_index=i,
            primary_site=str(coded.get("primary_site", "")).strip(),
            primary_site_description=(
                str(coded.get("primary_site_description", "")).strip()
                or plain.site_description
            ),
            histology=str(coded.get("histology", "")).strip(),
            histology_description=(
                str(coded.get("histology_description", "")).strip()
                or plain.histology_description
            ),
            date_of_diagnosis=plain.date_of_diagnosis,
            laterality=plain.laterality,
            confidence=plain.confidence,
            evidence=plain.evidence,
        )
        result.append(diag)

    return result


def _plain_to_diagnosis_info(
    plain_diagnoses: list[_PlainLanguageDiagnosis],
) -> list[DiagnosisInfo]:
    """Fallback: convert plain-language diagnoses to DiagnosisInfo without codes."""
    return [
        DiagnosisInfo(
            tumor_index=d.tumor_index,
            primary_site="",
            primary_site_description=d.site_description,
            histology="",
            histology_description=d.histology_description,
            date_of_diagnosis=d.date_of_diagnosis,
            laterality=d.laterality,
            confidence=d.confidence,
            evidence=d.evidence,
        )
        for d in plain_diagnoses
    ]


def _parse_diagnosis_list(raw_list: list[dict[str, Any]]) -> list[DiagnosisInfo]:
    """Convert raw JSON list to DiagnosisInfo objects, fixing tumor_index ordering.

    Kept for backward compatibility with legacy single-call discovery.
    """
    diagnoses: list[DiagnosisInfo] = []
    for i, entry in enumerate(raw_list):
        if not isinstance(entry, dict):
            continue
        diag = DiagnosisInfo(
            tumor_index=i,
            primary_site=str(entry.get("primary_site", "")).strip(),
            primary_site_description=str(entry.get("primary_site_description", "")).strip(),
            histology=str(entry.get("histology", "")).strip(),
            histology_description=str(entry.get("histology_description", "")).strip(),
            date_of_diagnosis=str(entry.get("date_of_diagnosis", "")).strip(),
            laterality=str(entry.get("laterality", "")).strip(),
            confidence=float(entry.get("confidence", 0.5)),
            evidence=str(entry.get("evidence", "")).strip()[:300],
        )
        diagnoses.append(diag)
    return diagnoses
