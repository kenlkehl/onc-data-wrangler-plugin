# Medical Code Knowledge Bases

This directory contains curated oncology-focused subsets of standard medical terminologies used by the synthetic data generation pipeline for grounding LLM output in real codes. Each vocabulary is kept as a simple three-column CSV (`code,description,category`) that the `MedicalCodeRegistry` (`src/onc_wrangler/ontologies/medical_codes.py`) loads at runtime.

## Bundled subsets

| Vocabulary | File | Rows | Source / provenance |
|---|---|---|---|
| ICD-10-CM | `icd10cm/icd10cm_codes_oncology.csv` | ~220 | US public-domain clinical modification of ICD-10, curated from the CMS FY-current tabular list (https://www.cms.gov/medicare/coding-billing/icd-10-codes). Focused on Chapter II neoplasms (C00–D49), common comorbidities, cancer-related adverse events, and encounter codes. |
| LOINC (subset) | `loinc/loinc_oncology_subset.csv` | ~100 | Hand-curated from LOINC's public documentation (https://loinc.org) covering common oncology labs (CBC, CMP, LFTs, coag, tumor markers, pathology markers, NGS assays, vitals). This is a small reference subset, not a redistribution of the LOINC release. |
| SNOMED CT (subset) | `snomed/snomed_oncology_subset.csv` | ~150 | Hand-curated set of oncology concepts derived from publicly documented references (disorders, procedures, stages, gene variants, adverse events). **Not** a redistribution of the SNOMED CT release. |

## Licensing notes

- **ICD-10-CM** is in the public domain in the US and may be freely redistributed.
- **LOINC** is freely usable (LOINC License 2.0) but redistribution of the full release typically requires attribution and a downloaded copy from https://loinc.org (free account). The bundled subset here is a small curated reference list intended for prompt grounding, not a substitute for the full release.
- **SNOMED CT** requires an IHTSDO Affiliate license. In the US, free access is provided via the UMLS Metathesaurus (NLM UMLS account required). **Do not redistribute the full SNOMED release without a license.** The bundled subset here is a short hand-curated reference list.

## Upgrading to full releases

To use the full ICD-10-CM / LOINC / SNOMED CT vocabularies instead of the bundled subsets, run the downloader / loader:

```bash
# ICD-10-CM (public, no auth needed)
python -m onc_wrangler.scripts.download_medical_codes --icd10

# LOINC (point at your Loinc.csv from a loinc.org account download)
python -m onc_wrangler.scripts.download_medical_codes \
    --loinc /path/to/LoincTable/Loinc.csv

# SNOMED CT (point at your UMLS/IHTSDO RF2 Snapshot release)
python -m onc_wrangler.scripts.download_medical_codes \
    --snomed /path/to/SnomedCT_.../Snapshot/Terminology
```

After running, files land in `data/ontologies/medical_codes/<vocab>/full/` and `MedicalCodeRegistry` will prefer the full release over the bundled subset automatically.

## CSV schema

Every vocabulary CSV has exactly three columns:

| column | type | notes |
|---|---|---|
| `code` | string | The identifier (ICD-10-CM code, LOINC code, SNOMED CT concept ID) |
| `description` | string | Short human-readable description used for fuzzy matching |
| `category` | string (optional) | A coarse grouping for easier filtering (e.g., `breast`, `cmp`, `adverse_event`) |

Keep new rows in lexicographic order by code within a category block.
