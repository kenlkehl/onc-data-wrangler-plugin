"""Diagnosis discovery phase for multi-diagnosis extraction.

Before extracting domain-group items, this module asks the LLM to identify
all distinct primary cancer diagnoses in a patient's notes.  Each discovered
diagnosis drives a separate per-diagnosis extraction loop with its own schema
resolution and site-specific staging items.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

from ..llm.base import LLMClient

logger = logging.getLogger(__name__)


def _parse_json_list(text: str) -> list[dict] | None:
    """Best-effort parse of a JSON array from LLM output."""
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


def _unknown_diagnosis() -> list[DiagnosisInfo]:
    """Fallback: a single diagnosis with no identity information."""
    return [DiagnosisInfo(tumor_index=0)]


DISCOVERY_SYSTEM_PROMPT = """\
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

DISCOVERY_USER_TEMPLATE = """\
Clinical text for one patient:
---
{patient_text}
---

Identify ALL distinct primary cancer diagnoses in this text. Return a JSON \
array as described in the instructions."""


def discover_diagnoses(
    llm_client: LLMClient,
    patient_text: str,
    max_tokens: int = 4096,
    max_retries: int = 3,
) -> list[DiagnosisInfo]:
    """Identify all distinct cancer diagnoses from patient text.

    Returns at least one :class:`DiagnosisInfo`.  Falls back to a single
    unknown diagnosis on parse failure.
    """
    if not patient_text or len(patient_text.strip()) < 20:
        return _unknown_diagnosis()

    prompt = DISCOVERY_SYSTEM_PROMPT + "\n\n" + DISCOVERY_USER_TEMPLATE.format(
        patient_text=patient_text,
    )

    for attempt in range(max_retries):
        try:
            response = llm_client.generate_structured(prompt, max_tokens=max_tokens)
            parsed = _parse_json_list(response.text)
            if parsed is not None and len(parsed) > 0:
                diagnoses = _parse_diagnosis_list(parsed)
                if diagnoses:
                    logger.info(
                        "Discovered %d diagnosis(es) from patient text",
                        len(diagnoses),
                    )
                    return diagnoses
            logger.warning(
                "Diagnosis discovery parse failed (attempt %d/%d)",
                attempt + 1, max_retries,
            )
        except Exception:
            logger.exception(
                "Diagnosis discovery LLM call failed (attempt %d/%d)",
                attempt + 1, max_retries,
            )

    logger.warning("Diagnosis discovery failed after %d retries; using single unknown diagnosis", max_retries)
    return _unknown_diagnosis()


def _parse_diagnosis_list(raw_list: list[dict[str, Any]]) -> list[DiagnosisInfo]:
    """Convert raw JSON list to DiagnosisInfo objects, fixing tumor_index ordering."""
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
