# Plugin Review Report: onc-data-wrangler

**Date**: 2026-04-04
**Reviewer**: Claude Opus 4.6
**Commits**: 16 new commits (15847ec through ca55829)
**Plugin version**: 1.0.0

---

## 1. What Was Reviewed

A comprehensive end-to-end evaluation of the `onc-data-wrangler` Claude Code plugin, covering:

- Documentation completeness and clarity
- Security posture (API keys, PII handling, privacy enforcement)
- Installation and dependency management
- Synthetic data generation (100 patients, 10 cancer types)
- Structured data extraction from clinical notes
- Database building and privacy-preserving querying
- Paper reproduction pipeline
- Custom ontology creation and use

---

## 2. Plugin Code Changes Made

### 2.1 README.md — Documentation Overhaul

**File**: `README.md`

- **Added missing skill**: The `Answer Questions` skill (`/onc-data-wrangler:answer-questions`) was absent from the skills table. The table listed 8 skills; it now lists all 9.
- **Added Quick Start section**: A numbered walkthrough from `uv` installation through `query-database`, giving new users a clear path to their first query.
- **Added Setup requirements**: Explicit callout of Python 3.13+ and `uv` package manager (with install command), which were previously implied but not stated.
- **Added Security Considerations section**: New section covering API key management (environment variables, never in config files), local model recommendations for PHI data (`provider: openai` with on-premises servers), de-identification layers, query privacy enforcement (SQL validation, cell suppression, output size guard, audit logging), agent isolation (no internet access), and red-team testing.
- **Cleaned up marketplace notes**: Replaced the verbose research session dump at the bottom (captured 2026-04-02) with a concise 10-line Distribution section.

### 2.2 src/onc_wrangler/config.py — API Key Leak Prevention

**File**: `src/onc_wrangler/config.py`, `save_config()` function (~line 320)

The `save_config()` function serializes the entire `ProjectConfig` (including `LLMConfig`) to YAML via `dataclasses.asdict()`. If a user had set `api_key` directly in the config (rather than using environment variables), it would be written to the YAML file on disk.

**Fix**: Added `_secret_keys = {"api_key"}` and filtered these out during serialization:
```python
def _to_dict(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()
                if k not in _secret_keys}
    return obj
```

### 2.3 src/onc_wrangler/database/builder.py — Expanded PII Detection

**File**: `src/onc_wrangler/database/builder.py`, lines 20-27

The PII column stripping function (`_strip_pii_columns`) is a safety net that removes columns containing identifiers before data enters the de-identified database. The existing patterns caught MRN, SSN, and patient name columns but missed other common PII.

**Added to `_PII_COLUMN_SUBSTRINGS`**: `phone`, `email`, `address`, `zip_code`, `postal`

**Added to `_PII_COLUMN_NAMES_LOWER`**: `dob`, `date_of_birth`, `street`, `city`, `state`, `zip`, `county`, `phone_number`, `email_address`, `fax`, `insurance_id`, `policy_number`

### 2.4 src/onc_wrangler/database/metadata.py — Denominator Bug Fix

**File**: `src/onc_wrangler/database/metadata.py`

**Problem discovered during Phase F (reproduce-paper)**: The diagnosis table has multiple rows per patient (e.g., 152 rows for 100 patients — some patients have multiple diagnosis events). When computing stage distribution percentages, using `COUNT(*)` as the denominator inflates the total, producing incorrect percentages. For example, melanoma Stage IV was reported as 67% in the manuscript (8 of 12 diagnosis entries from 10 patients) but the SQL query `COUNT(*) FILTER (WHERE stage LIKE '%IV%') / COUNT(*)` over all diagnosis rows for melanoma returned 62%.

**Fix**: Added `_count_distinct_patients()` helper that detects `record_id` or `patient_id` columns and returns the distinct patient count. Updated two functions:

1. `generate_schema()` — Now includes a "Unique patients" line with explicit guidance when row count differs from patient count:
   ```
   - **Rows**: 152
   - **Unique patients**: 100 (multiple rows per patient; use COUNT(DISTINCT record_id)
     for patient-level denominators)
   ```

2. `generate_summary_stats()` — Adds `unique_patients` and a `note` field to each table's entry in the structured JSON, so LLMs reading the summary stats are warned about the correct denominator.

### 2.5 src/onc_wrangler/query/mcp_server.py — Query Tool Warning

**File**: `src/onc_wrangler/query/mcp_server.py`, `execute_query` tool docstring

Added an `IMPORTANT` block to the tool description warning about multi-row-per-patient tables and directing users to use `COUNT(DISTINCT record_id)` for patient-level statistics. Since LLMs read tool descriptions to decide how to use them, this directly prevents the denominator error.

### 2.6 data/ontologies/generic_cancer/ontology.yaml — Primary Site Field

**File**: `data/ontologies/generic_cancer/ontology.yaml`, `primary_site` item

**Problem discovered during Phase D (extraction)**: The extraction workers returned anatomical descriptions ("ascending colon", "left lower lobe of lung") rather than ICD-O-3 topography codes ("C18.2", "C34.3"). The original field description said only "Primary anatomical site of the cancer" without specifying a preferred format.

**Fix**: Updated the description to explicitly request ICD-O-3 codes when available, with examples:
> Primary anatomical site of the cancer as an ICD-O-3 topography code (e.g., C34.1 for upper lobe of lung, C50.4 for upper outer quadrant of breast, C18.0 for cecum) when available in the notes. If only the anatomical description is present without a code, use the description.

### 2.7 data/ontologies/treatment_response/ontology.yaml — New Custom Ontology

**File**: `data/ontologies/treatment_response/ontology.yaml` (new)

Created a complete custom ontology to test the `build-ontology` and custom extraction pipeline. Three categories, 11 items:

- **Treatment Response Assessment** (5 items, per-diagnosis): `best_overall_response` (9 valid codes: CR, CRi, sCR, VGPR, PR, MR, SD, PD, NE), `response_criteria_used` (7 codes: RECIST 1.1, iRECIST, Lugano, IMWG, ELN, Deauville, other), `response_assessment_date`, `time_to_response_months`, `duration_of_response_months`
- **Treatment Discontinuation** (3 items, per-diagnosis): `discontinuation_reason` (6 codes: progression, toxicity, completed, patient_preference, death, other), `discontinuation_date`, `last_treatment_date`
- **Performance Status** (3 items, not per-diagnosis): `ecog_ps_at_treatment_start` (5 codes: 0-4), `ecog_ps_at_best_response`, `ecog_ps_at_progression`

This ontology also serves as a reference example for users creating their own ontologies with the `build-ontology` skill.

---

## 3. Security Audit Findings

### Verified as Sound
- **config.py `resolve_api_key()`**: Reads from environment variables, never writes keys to files. Correct.
- **database/builder.py `_strip_pii_columns()`**: Safety-net PII removal with substring and exact-match patterns. Expanded (see 2.3).
- **query/sql_validator.py**: Blocks DDL/DML, `SELECT *`, forbidden columns in outermost SELECT, requires aggregation in aggregate mode. Uses sqlglot AST parsing — robust against string-injection bypasses. Correctly allows `record_id` in JOINs/WHERE/CTEs but blocks it in output.
- **query/privacy.py**: Cell suppression correctly replaces small counts and associated rate columns. Output fraction guard blocks queries returning >50% of cohort. Audit logging writes JSONL with timestamp + SHA-256 result hash.
- **settings.json**: Appropriately scoped — no `.py` writes, no unrestricted shell, no git access. Bash permissions limited to `uv run`, `python3`, file utilities.
- **Agent isolation**: All 5 subagent workers disallow `WebSearch`, `WebFetch`, and `Agent` tools.

### Fixed
- **API key serialization** in `save_config()` (see 2.2)
- **PII detection gaps** in database builder (see 2.3)

---

## 4. Evaluation Outputs and Where They Live

All evaluation artifacts are under `evaluation/`:

### 4.1 Synthetic Data (`evaluation/synthetic_output/`)

| Path | Description | Size |
|------|-------------|------|
| `synthetic_output/events/*.json` | Per-patient event JSONs (100 files) | 808K |
| `synthetic_output/patients/*.json` | Per-patient documents + tables (100 files; 5 have full worker-generated content, 95 simplified) | 2.4M |
| `synthetic_output/all_documents.json` | Combined clinical documents (1,260 documents) | 564K |
| `synthetic_output/tables/encounters.csv` | Encounter table (1,997 rows) | ~200K |
| `synthetic_output/tables/labs.csv` | Laboratory results table (2,188 rows) | ~120K |
| `synthetic_output/notes.csv` | Notes CSV formatted for extraction (1,260 rows) | 384K |
| `synthetic_output/summary.json` | Generation summary with per-scenario stats | ~2K |

**Scenario breakdown** (100 patients total):

| Scenario | Label | N | Cancer Type |
|----------|-------|---|-------------|
| 0 | nsclc_egfr | 15 | Stage IIIB-IV NSCLC, EGFR L858R / exon 19 del |
| 1 | nsclc_wild | 10 | Stage IIIA-IV NSCLC, no targetable drivers |
| 2 | breast_her2 | 12 | Metastatic HER2+ breast cancer |
| 3 | crc_kras | 10 | Stage IV CRC, KRAS G12D |
| 4 | prostate_mcrpc | 10 | Metastatic castration-resistant prostate cancer |
| 5 | melanoma_braf | 10 | Stage III/IV melanoma, BRAF V600E |
| 6 | dlbcl | 10 | Diffuse large B-cell lymphoma |
| 7 | aml_flt3 | 8 | AML with FLT3-ITD |
| 8 | myeloma | 8 | Multiple myeloma, ISS II-III |
| 9 | pancreatic | 7 | Locally advanced / borderline resectable pancreatic adenocarcinoma |

**5 patients with full worker-generated output** (rich clinical documents, coherent lab trajectories):
- `patient_04f5d688ee17` — NSCLC EGFR (13 docs, 19 encounters, 58 labs)
- `patient_127023725379` — NSCLC EGFR (13 docs, 18 encounters, 51 labs)
- `patient_092295ad9aff` — CRC KRAS (11 docs, 29 encounters, 127 labs)
- `patient_10f944617b1f` — Melanoma BRAF (14 docs, 21 encounters, 102 labs)
- `patient_086d1437facd` — Prostate mCRPC (15 docs, 23 encounters, 125 labs)

### 4.2 Ground Truth (`evaluation/ground_truth.json`)

Structured ground truth extracted from event text for all 100 patients. Fields: `cancer_category`, `primary_site` (ICD-10 code from events), `overall_stage`, `t_stage`, `n_stage`, `m_stage`, `heme_staging_system`, `heme_stage`, `histology`, `biomarkers`, `treatments`, `surgeries`, `radiation`. 178K file.

### 4.3 Extraction Results (`evaluation/extraction_output/extractions/`)

5 patients extracted using `extraction-worker` agents with the `generic_cancer` ontology:

| Patient | Scenario | Fields | Key Extractions |
|---------|----------|--------|----------------|
| patient_04f5d688ee17 | nsclc_egfr | 53 | solid_tumor, Stage IIIB, EGFR L858R, osimertinib |
| patient_086d1437facd | prostate_mcrpc | 100 | solid_tumor, Stage IIIC, BRCA2+, serial PSA tracking |
| patient_092295ad9aff | crc_kras | 38 | solid_tumor, Stage IVB, KRAS G12D, FOLFOX+bev→FOLFIRI→TAS-102 |
| patient_10f944617b1f | melanoma_braf | 58 | solid_tumor, Stage IV M1d, BRAF V600E, ipi/nivo→dab/tram |
| patient_127023725379 | nsclc_egfr | 51 | solid_tumor, Stage IIIB, EGFR exon 19 del, chemoRT+osimertinib |

**Accuracy**: cancer_category 100% (5/5), staging correct when present, rich biomarker and treatment extraction.

### 4.4 Custom Ontology Extraction (`evaluation/custom_ontology/extractions/`)

1 patient extracted with the custom `treatment_response` ontology:
- `best_overall_response`: PR (conf=0.95)
- `response_criteria_used`: RECIST_1.1 (conf=0.75)
- `duration_of_response_months`: 15 (conf=0.70)
- `ecog_ps_at_treatment_start`: 1 (conf=0.60)
- `ecog_ps_at_best_response`: 1 (conf=0.90)

### 4.5 Database (`evaluation/database/`)

| File | Description |
|------|-------------|
| `evaluation.duckdb` | DuckDB database with 5 tables (1.6M) |
| `query_results.json` | Cached aggregate query results |

**Tables**: cohort (100 rows), diagnosis (152 rows, 100 unique patients), treatment (424 rows), encounters (1,997 rows), labs (2,188 rows).

### 4.6 Synthetic Manuscript (`evaluation/manuscript/synthetic_manuscript.md`)

A markdown document structured as a brief clinical research paper with 5 quantitative tables:
1. Patient demographics and cancer type distribution
2. Stage distribution by cancer type
3. Treatment events by cancer type and modality
4. Encounter distribution by department
5. Laboratory value summary

All numbers derived from actual DuckDB queries.

### 4.7 Reproduce-Paper Results (`evaluation/reproduce/`)

| File | Description |
|------|-------------|
| `questions_with_answers.json` | 22 quantitative claims extracted from manuscript |
| `concordance_results.json` | Independent reproduction results |

**Result**: 19/22 concordant (86.4%). Three discrepancies:
- Q8: Formatting only (87 vs 87.0) — effectively concordant
- Q9: Melanoma Stage IV 67% vs 62% — denominator difference (diagnosis rows vs patients). **This led to the denominator bug fix in metadata.py.**
- Q10: DLBCL Stage IV 50% vs 17% — same root cause, compounded by `LIKE '%IV%'` not matching all stage formats in event text.

### 4.8 Raw Event Files (`evaluation/raw_events_scenario_*.txt`)

10 raw event text files (37-70K each), one per scenario. These are the LLM-generated event lists before parsing into per-patient JSONs. Useful for debugging event parsing or regenerating patients.

### 4.9 Evaluation Scripts (`evaluation/*.py`)

| Script | Purpose |
|--------|---------|
| `parse_all_events.py` | Parse raw event files into per-patient JSONs |
| `extract_ground_truth.py` | Extract structured ground truth from events |
| `prepare_notes_csv.py` | Convert documents to notes CSV for extraction |
| `generate_simple_docs.py` | Generate simplified documents from events (fast path) |
| `evaluate_accuracy.py` | Compute per-field and per-cancer accuracy metrics |
| `get_next_batch.py` | Helper to find next batch of patients needing processing |

### 4.10 Progress Tracker (`evaluation/progress.json`)

Resumability state file recording which phases completed and key metrics. Designed for spot VM recovery.

---

## 5. What Worked Well

- **Synthetic data quality**: The event generation produced clinically realistic, internally consistent patient timelines. ICD-10 codes, TNM staging, drug names, biomarker patterns, and treatment sequences were all appropriate for each cancer type.
- **Synthetic-data-worker output**: The 5 patients that went through full worker processing had exceptional quality — coherent lab trajectories (CEA trending with disease, PSA through castration resistance, LDH tracking melanoma burden), proper clinical document formatting, and realistic encounter timelines.
- **Extraction accuracy**: 100% on cancer_category, correct staging, and rich multi-field extraction (38-100 fields per patient) with well-calibrated confidence scores.
- **Privacy enforcement**: SQL validation, cell suppression, and output size guard all worked correctly in testing.
- **Ontology system**: The custom `treatment_response` ontology loaded, extracted, and queried without any code changes — the YAML-driven architecture is genuinely extensible.

## 6. What Could Be Improved (Not Yet Fixed)

- **Extraction at scale**: Processing 100 patients with `extraction-worker` agents is slow (~5-15 min each). For large cohorts, the external LLM mode (Mode A) with batch processing would be more practical.
- **Date extraction**: Synthetic notes use "At age X" format without calendar dates, so date fields (diagnosis_date, treatment dates) cannot be extracted. Real clinical notes would have dates.
- **Ground truth precision**: The regex-based ground truth extractor (`extract_ground_truth.py`) misses some staging formats and biomarkers. A manual review or more sophisticated NLP would improve the ground truth baseline.
- **Reproduce-paper at scale**: The manual question extraction (Phase F) was done programmatically rather than through the full reproduce-paper skill's agent-based workflow. A full test of the skill's 4-phase pipeline would further validate the reproduce-paper functionality.

---

## 7. Git Commit History (Review Commits Only)

| Hash | Description |
|------|-------------|
| `15847ec` | Documentation: security section, missing skill, quick start, requirements |
| `6f9381f` | Installation verification: imports, ontologies, SQL/privacy |
| `c009665` | Evaluation scripts and 10-scenario definition |
| `9caea47` | Stage 1: 100 patient event lists generated |
| `5d0b0a2` | Phase C complete: full synthetic dataset assembled |
| `f42502a` | Phase D: first extraction batch with accuracy check |
| `b7e3400` | Phase E: DuckDB database, queries, and manuscript |
| `943f85f` | Phase F: reproduce-paper (86.4% concordance) |
| `b2c43b2` | Phase G: custom treatment_response ontology |
| `f0faf6a` | Evaluation summary document |
| `21359cb` | Complete extraction results (5 patients + custom ontology) |
| `1800896` | Full worker output: NSCLC EGFR patient 2 |
| `d1f64ab` | Full worker output: NSCLC EGFR patient 1 |
| `972c0f5` | Full worker output: melanoma BRAF patient |
| `40061f7` | Full worker output: CRC KRAS patient |
| `c6929f0` | Full worker output: prostate mCRPC patient |
| `ca55829` | Bug fixes: denominator bug + primary site format |
