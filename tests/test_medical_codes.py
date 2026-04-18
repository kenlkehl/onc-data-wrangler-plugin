"""Tests for the medical code registry + synthetic retrieval/registry modules."""

from __future__ import annotations

from onc_wrangler.ontologies.medical_codes import MedicalCodeRegistry
from onc_wrangler.synthetic.code_retrieval import (
    build_reference_block,
    extract_keywords_from_scenario,
)
from onc_wrangler.synthetic.naaccr_registry import (
    _extraction_to_naaccr_dict,
    resolve_cancer_type_from_events,
)


# ---------------------------------------------------------------------------
# MedicalCodeRegistry
# ---------------------------------------------------------------------------

def test_registry_loads_bundled_subsets() -> None:
    r = MedicalCodeRegistry()
    r.load()
    assert r.count("icd10cm") > 100
    assert r.count("loinc") > 50
    assert r.count("snomed") > 50


def test_registry_search_breast_cancer_returns_c50() -> None:
    r = MedicalCodeRegistry()
    r.load()
    hits = r.search("breast cancer", "icd10cm", limit=5)
    assert hits
    assert any(c.code.startswith("C50") for c in hits), (
        f"expected a C50 code in top 5, got {[c.code for c in hits]}"
    )


def test_registry_search_hemoglobin_returns_loinc_7187() -> None:
    r = MedicalCodeRegistry()
    r.load()
    hits = r.search("hemoglobin", "loinc", limit=5)
    assert hits
    assert any(c.code == "718-7" for c in hits), (
        f"expected LOINC 718-7 in top 5, got {[c.code for c in hits]}"
    )


def test_registry_search_lung_cancer_returns_snomed() -> None:
    r = MedicalCodeRegistry()
    r.load()
    hits = r.search("lung cancer", "snomed", limit=5)
    assert hits
    # Must surface some lung-cancer concept in the top results.
    assert any("lung" in c.description.lower() for c in hits)


def test_retrieve_for_context_deduplicates_and_limits() -> None:
    r = MedicalCodeRegistry()
    r.load()
    keywords = ["breast cancer", "metastatic", "hemoglobin", "EGFR"]
    retrieved = r.retrieve_for_context(keywords, per_vocab_limit=10)
    assert set(retrieved).issuperset({"icd10cm", "loinc", "snomed"})
    for vocab, codes in retrieved.items():
        assert len(codes) <= 10
        # No dupes within a vocab.
        code_ids = [c.code for c in codes]
        assert len(code_ids) == len(set(code_ids)), vocab


# ---------------------------------------------------------------------------
# code_retrieval
# ---------------------------------------------------------------------------

def test_extract_keywords_from_breast_cancer_blurb() -> None:
    blurb = (
        "A 55-year-old woman diagnosed with stage III HER2-positive invasive "
        "ductal carcinoma of the left breast; received trastuzumab and paclitaxel."
    )
    keywords = extract_keywords_from_scenario(blurb, events=None)
    lower = {k.lower() for k in keywords}
    assert "breast" in lower
    assert "trastuzumab" in lower
    assert "paclitaxel" in lower
    assert any("HER2" in k or "her2" in k for k in keywords)


def test_extract_keywords_honors_events() -> None:
    blurb = "Stage IV EGFR-mutant NSCLC."
    events = [
        {"type": "diagnosis", "text": "Adenocarcinoma of the right lower lobe."},
        {"type": "ngs_report", "text": "EGFR L858R mutation detected."},
    ]
    keywords = extract_keywords_from_scenario(blurb, events)
    lower = {k.lower() for k in keywords}
    assert "lung" in lower or "nsclc" in lower
    assert "egfr" in lower
    assert "adenocarcinoma" in lower


def test_build_reference_block_is_nonempty_for_oncology_context() -> None:
    r = MedicalCodeRegistry()
    r.load()
    keywords = extract_keywords_from_scenario(
        "Metastatic breast cancer with bone mets on pembrolizumab.",
        events=None,
    )
    block = build_reference_block(r, keywords)
    assert "Reference Vocabularies" in block
    assert "ICD-10-CM" in block
    assert "C50" in block or "C79.51" in block


def test_build_reference_block_empty_when_no_matches() -> None:
    r = MedicalCodeRegistry()
    r.load()
    block = build_reference_block(r, keywords=[])
    assert block == ""


# ---------------------------------------------------------------------------
# naaccr_registry (post-processing only; no LLM call)
# ---------------------------------------------------------------------------

def test_resolve_cancer_type_breast() -> None:
    events = [
        {"type": "demographics", "text": "55yo female."},
        {"type": "diagnosis", "text": "invasive ductal carcinoma of the right breast"},
    ]
    assert resolve_cancer_type_from_events(events) == "breast"


def test_resolve_cancer_type_lung_nsclc() -> None:
    events = [
        {"type": "diagnosis", "text": "Stage IV NSCLC of right lower lobe"},
    ]
    assert resolve_cancer_type_from_events(events) == "lung"


def test_resolve_cancer_type_generic_fallback() -> None:
    events = [
        {"type": "clinical_note", "text": "Patient doing well."},
    ]
    assert resolve_cancer_type_from_events(events) == "generic"


def test_extraction_to_naaccr_dict_reads_extraction_results_metadata() -> None:
    # Simulate the shape produced by Extractor.extract_iterative().
    fake_result_list = [
        {"naaccr": {"PRIMARY_SITE": "C50.9"}},
        {"_diagnoses": [{"tumor_index": 0, "naaccr": {"PRIMARY_SITE": "C50.9"}}]},
        {"_extraction_results": {
            "patient": {
                "230": {
                    "field_id": "230",
                    "field_name": "Sex",
                    "extracted_value": "female",
                    "resolved_code": "2",
                    "confidence": 0.95,
                    "evidence_text": "",
                    "source_chunk_id": "",
                    "source_chunk_type": "",
                    "pass_number": 0,
                    "ontology_id": "naaccr",
                },
            },
            "diagnosis_0": {
                "400": {
                    "field_id": "400",
                    "field_name": "Primary Site",
                    "extracted_value": "breast",
                    "resolved_code": "C50.9",
                    "confidence": 0.9,
                    "evidence_text": "breast mass",
                    "source_chunk_id": "",
                    "source_chunk_type": "",
                    "pass_number": 0,
                    "ontology_id": "naaccr",
                    "tumor_index": 0,
                },
            },
        }},
    ]
    result = _extraction_to_naaccr_dict(fake_result_list)
    assert result == {"230": "2", "400": "C50.9"}


def test_extraction_to_naaccr_dict_empty_when_no_metadata() -> None:
    # No "_extraction_results" entry present.
    assert _extraction_to_naaccr_dict([{"naaccr": {"PRIMARY_SITE": "C50.9"}}]) == {}
