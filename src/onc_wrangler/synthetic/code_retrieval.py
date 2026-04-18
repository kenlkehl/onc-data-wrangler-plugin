"""Scenario-driven retrieval of relevant medical codes for prompt grounding.

Extracts keywords from the scenario blurb and Stage-1 events (no LLM
call) and uses :class:`MedicalCodeRegistry` to fetch the most relevant
ICD-10-CM / LOINC / SNOMED codes. Produces a markdown block that is
injected into Stage 2 and Stage 3 prompts to force the LLM to use real
codes.
"""

from __future__ import annotations

import re
from typing import Iterable

from onc_wrangler.ontologies.medical_codes import (
    MedicalCode,
    MedicalCodeRegistry,
    SUPPORTED_VOCABS,
)

from .drug_perturbation import DEFAULT_DRUG_MAP


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------

# Oncology-relevant site / histology / concept anchors. Chosen to match
# the LOINC/ICD/SNOMED bundled descriptions so fuzzy hits are plentiful.
_SITE_KEYWORDS: tuple[str, ...] = (
    "breast", "lung", "prostate", "colon", "rectum", "rectal", "colorectal",
    "pancreas", "pancreatic", "liver", "hepatocellular", "biliary",
    "gallbladder", "gastric", "stomach", "esophageal", "esophagus",
    "melanoma", "skin", "ovarian", "ovary", "endometrial", "uterine",
    "cervical", "cervix", "bladder", "kidney", "renal", "testicular",
    "head and neck", "thyroid", "adrenal", "brain", "glioma",
    "glioblastoma", "meningioma", "sarcoma", "bone", "soft tissue",
    "lymphoma", "Hodgkin", "diffuse large B-cell", "follicular",
    "leukemia", "AML", "ALL", "CLL", "CML", "myeloma", "MDS",
    "mesothelioma", "anal", "nasopharyngeal",
)

_HISTOLOGY_KEYWORDS: tuple[str, ...] = (
    "adenocarcinoma", "squamous cell carcinoma", "small cell",
    "non-small cell", "NSCLC", "SCLC", "ductal carcinoma",
    "lobular carcinoma", "transitional cell", "clear cell",
    "papillary", "medullary", "mucinous", "neuroendocrine",
    "carcinoid", "sarcomatoid", "large cell",
)

_LAB_KEYWORDS: tuple[str, ...] = (
    "hemoglobin", "hematocrit", "platelets", "white blood cell",
    "leukocytes", "neutrophils", "lymphocytes", "creatinine",
    "bilirubin", "alkaline phosphatase", "AST", "ALT",
    "albumin", "glucose", "sodium", "potassium",
    "calcium", "LDH", "PSA", "CEA", "CA-125", "CA 19-9",
    "CA 15-3", "AFP", "beta-hCG", "PT", "INR", "aPTT",
    "ferritin", "thyroglobulin", "TSH", "estrogen receptor",
    "progesterone receptor", "HER2", "PD-L1", "microsatellite",
    "tumor mutation burden", "next generation sequencing",
)

_STAGE_KEYWORDS: tuple[str, ...] = (
    "stage I", "stage II", "stage III", "stage IV",
    "metastatic", "metastasis", "metastases",
    "recurrence", "progression", "partial response",
    "complete response", "stable disease", "remission",
)

_BIOMARKER_KEYWORDS: tuple[str, ...] = (
    "EGFR", "KRAS", "BRAF", "ALK", "ROS1", "HER2",
    "BRCA1", "BRCA2", "TP53", "MET", "RET", "NTRK",
    "PIK3CA", "PD-L1", "microsatellite instability",
    "tumor mutational burden",
)

# Compile once.
_ALL_KEYWORD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE))
    for kw in (
        *_SITE_KEYWORDS,
        *_HISTOLOGY_KEYWORDS,
        *_LAB_KEYWORDS,
        *_STAGE_KEYWORDS,
        *_BIOMARKER_KEYWORDS,
    )
]

_DRUG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (drug, re.compile(r"\b" + re.escape(drug) + r"\b", re.IGNORECASE))
    for drug in DEFAULT_DRUG_MAP
]


def extract_keywords_from_scenario(
    blurb: str,
    events: list[dict] | None = None,
) -> list[str]:
    """Extract clinical keywords from a blurb + Stage-1 events.

    Pure string matching against a curated oncology keyword list;
    deterministic and cheap. De-duplicates while preserving order.
    """
    haystack_parts: list[str] = [blurb or ""]
    if events:
        for e in events:
            haystack_parts.append(e.get("text", ""))
    haystack = "\n".join(haystack_parts)
    seen: set[str] = set()
    keywords: list[str] = []
    for kw, pat in _ALL_KEYWORD_PATTERNS:
        if pat.search(haystack):
            key = kw.lower()
            if key in seen:
                continue
            seen.add(key)
            keywords.append(kw)
    for drug, pat in _DRUG_PATTERNS:
        if pat.search(haystack):
            key = drug.lower()
            if key in seen:
                continue
            seen.add(key)
            keywords.append(drug)
    return keywords


# ---------------------------------------------------------------------------
# Reference-block formatting
# ---------------------------------------------------------------------------

_VOCAB_HEADERS: dict[str, tuple[str, str]] = {
    "icd10cm": ("ICD-10-CM", "diagnoses / encounters / comorbidities"),
    "loinc": ("LOINC", "laboratory tests and observations"),
    "snomed": ("SNOMED CT", "clinical concepts, procedures, findings"),
}


def build_reference_block(
    registry: MedicalCodeRegistry,
    keywords: Iterable[str],
    vocabs: Iterable[str] = SUPPORTED_VOCABS,
    per_vocab_limit: int = 25,
) -> str:
    """Format retrieved codes as a markdown block for prompt injection.

    Returns an empty string if no keywords were found in any vocab so
    that the caller can cleanly skip injection.
    """
    kw_list = list(keywords)
    if not kw_list:
        return ""
    retrieved = registry.retrieve_for_context(
        kw_list,
        vocabs=vocabs,
        per_vocab_limit=per_vocab_limit,
    )
    nonempty = {v: codes for v, codes in retrieved.items() if codes}
    if not nonempty:
        return ""

    lines: list[str] = [
        "## Reference Vocabularies",
        (
            "Use the exact codes below where applicable (don't invent new ones). "
            "Each section lists codes relevant to this patient's clinical context."
        ),
    ]
    for vocab in vocabs:
        codes = nonempty.get(vocab)
        if not codes:
            continue
        header_name, header_desc = _VOCAB_HEADERS.get(
            vocab, (vocab.upper(), vocab)
        )
        lines.append(f"\n### {header_name}  ({header_desc})")
        for c in codes:
            lines.append(_format_code_line(c))
    return "\n".join(lines)


def _format_code_line(code: MedicalCode) -> str:
    return f"- {code.code}  {code.description}"


# ---------------------------------------------------------------------------
# High-level convenience
# ---------------------------------------------------------------------------

def build_reference_block_for_patient(
    registry: MedicalCodeRegistry,
    blurb: str,
    events: list[dict] | None = None,
    per_vocab_limit: int = 25,
) -> str:
    """One-shot: extract keywords from blurb + events and format a block."""
    keywords = extract_keywords_from_scenario(blurb, events)
    return build_reference_block(
        registry, keywords, per_vocab_limit=per_vocab_limit,
    )
