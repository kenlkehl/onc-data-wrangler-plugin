---
name: pull-papers
description: >
  Search PubMed Central for oncology papers with analyzable data, classify
  by research category (basic science, computational biology, translational,
  clinical), validate data quality by inspecting files, and organize into
  category folders. Use when the user wants to find and download oncology
  research papers with data for analysis.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write, Agent
model: inherit
effort: high
---

# Pull Papers — Oncology Paper Discovery & Download

You are orchestrating a pipeline to discover, classify, download, and validate oncology research papers with analyzable data from PubMed Central. Papers are organized into four research categories: **basic_science**, **clinical**, **computational_biology**, and **translational**.

The Python CLI for PMC searches and downloads is at: `${CLAUDE_PLUGIN_ROOT}/scripts/pmc_search.py`

Run it via: `uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pmc_search.py <subcommand> [args]`

All subcommands output JSON to stdout. Logs go to stderr.

---

## PHASE 0: CONFIGURATION

### 0.1 Ask the user

Present these options and ask the user to confirm or customize:

1. **Categories to search** (default: all four):
   - `basic_science` — cell lines, animal models, molecular mechanisms
   - `clinical` — clinical trials, survival analysis, cohort studies
   - `computational_biology` — bioinformatics, ML, algorithms
   - `translational` — biomarkers, drug targets, precision medicine

2. **Papers per category** (default: 5)

3. **Additional topic constraints** (optional): e.g., "breast cancer only", "immunotherapy", "single-cell"

4. **Search pool size** (default: 100 candidates per category)

### 0.2 Verify directory structure

Check that the working directory has (or create) the category subdirectories:

```
./basic_science/
./clinical/
./computational_biology/
./translational/
```

Create any that are missing with `mkdir -p`.

### 0.3 Record configuration

Store the user's choices for reference throughout the pipeline. If the user provided additional topic constraints, you will append them to the search queries in Phase 1.

---

## PHASE 1: SEARCH PMC

For each selected category, search PMC for candidate papers:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pmc_search.py search --category <CATEGORY> --pool <POOL_SIZE>
```

This outputs JSON mapping category → list of PMC article IDs.

If the user specified additional topic constraints, modify the search by running `search --category all` and then filtering in Phase 3 based on the constraint terms in the abstract.

Collect all candidate PMC IDs across categories. Deduplicate IDs that appear in multiple categories.

Report to the user: "Found N candidate papers across K categories."

---

## PHASE 2: FETCH METADATA

Fetch metadata (title, abstract, journal, data signals) for all candidates:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pmc_search.py metadata --ids <COMMA_SEPARATED_IDS>
```

The output includes `abstract` for each paper — this is critical for classification.

Save the metadata JSON to a temporary file (e.g., `_metadata_candidates.json`) in the working directory.

---

## PHASE 3: LLM CLASSIFICATION

This is where you add value beyond keyword search. For each paper, read its **title**, **abstract**, **journal**, and **data_availability** statement, then classify it into exactly one of the four categories.

### Classification criteria

- **basic_science**: Studies focused on understanding biological mechanisms using cell lines, animal models, or molecular experiments. In vitro/in vivo studies. Gene function, signaling pathways, protein interactions. Data typically includes gene expression arrays, Western blot quantification, cell viability assays, flow cytometry. The primary goal is mechanistic understanding, NOT patient outcomes.

- **clinical**: Studies involving human patients or patient cohorts. Clinical trials (phase I-III), retrospective cohort studies, survival analyses, treatment comparisons, epidemiological studies. Data includes patient demographics, treatment records, survival times, clinical outcomes. The primary endpoint is a clinical outcome.

- **computational_biology**: Development or benchmarking of computational methods, algorithms, or software tools applied to cancer data. Machine learning, deep learning, network analysis, multi-omics integration, single-cell pipelines. Data includes benchmark datasets, processed genomics data, algorithm outputs. The primary contribution is methodological.

- **translational**: Bridging basic and clinical science. Biomarker discovery and validation, therapeutic target identification, patient-derived xenografts/organoids, drug sensitivity profiling, companion diagnostics, liquid biopsy. Data includes mixed molecular + clinical data. The primary goal is clinical applicability of biological findings.

### Classification process

1. For each paper, assign a category and a confidence (high/medium/low)
2. If a paper doesn't fit any category or isn't oncology-related, mark it as "rejected"
3. If the user specified topic constraints, also reject papers that don't match
4. Respect the per-category paper target — if one category is oversubscribed, keep the highest-scored candidates

### Present to user for confirmation

Show a table of classified papers:

```
Category: basic_science (N papers)
  PMC12345 — "Title..." [confidence: high]
  PMC67890 — "Title..." [confidence: medium]

Category: clinical (N papers)
  ...
```

Ask the user to confirm or adjust any classifications before proceeding.

---

## PHASE 4: DATA AVAILABILITY FILTER

Filter for papers that actually have downloadable data. Save the classified papers (per category) to a temporary JSON file, then run:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pmc_search.py filter --metadata-file <FILE> --target <N>
```

This checks OA status and scores data availability signals (GEO, Zenodo, Figshare, Dryad, supplementary files). Papers without confirmed OA access or data signals are dropped.

Report to the user how many papers passed filtering per category. If any category has zero candidates, inform the user and offer to re-search with broader queries.

---

## PHASE 5: DOWNLOAD

For each paper that passed filtering, download the PDF, supplementary files, and external data:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pmc_search.py download \
    --pmc-id <PMC_ID> \
    --dest ./<CATEGORY>/<PMC_ID> \
    --metadata-file <FILTERED_METADATA_FILE>
```

This creates the directory structure:
```
./<category>/<PMC_ID>/
├── paper.pdf
├── paper_metadata.json
├── data/
│   ├── clinical_data.csv
│   ├── GSE12345_series_matrix.txt.gz
│   └── ...
└── supplementary/
    ├── supplement.pdf
    └── ...
```

Report download progress to the user as papers complete.

---

## PHASE 6: DATA VALIDATION

For each downloaded paper, verify that the data files are actually analyzable. Spawn `data-validator-worker` agents in batches of up to 5 in parallel.

### Spawning pattern

For each paper to validate, spawn:

```
Agent(
    subagent_type="onc-data-wrangler:data-validator-worker",
    description="Validate data for PMC_ID",
    prompt="""
    Validate the data files for this paper.

    PAPER_DIR: ./<category>/<PMC_ID>
    OUTPUT_PATH: ./<category>/<PMC_ID>/validation_result.json
    PLUGIN_ROOT: ${CLAUDE_PLUGIN_ROOT}

    Inspect every file in the data/ subdirectory. For each file, use Python
    (via uv run --directory PLUGIN_ROOT) to load it with pandas and assess
    whether it contains analyzable tabular data. Write your validation result
    JSON to OUTPUT_PATH.
    """,
    run_in_background=True,
    model="sonnet"
)
```

Wait for all workers to complete. Then read each `validation_result.json`.

### Handle validation failures

For papers where `overall_analyzable` is false:
1. Log the reason
2. Remove the paper directory (it has no usable data)
3. Record the rejection

Report validation results to the user:
```
Validation results:
  basic_science: 4/5 papers have analyzable data
    ✓ PMC12345 — 245 rows, clinical data with survival endpoints
    ✗ PMC67890 — No analyzable files (only image descriptions)
  clinical: 5/5 papers have analyzable data
    ...
```

---

## PHASE 7: SUMMARY & MANIFEST

### 7.1 Write manifest

Create `manifest.json` in the working directory summarizing all papers:

```json
{
  "created": "2025-01-01T00:00:00Z",
  "categories": {
    "basic_science": {
      "papers": [
        {
          "pmc_id": "PMC12345",
          "title": "...",
          "doi": "...",
          "data_summary": "245 rows, 12 columns — patient-level clinical data",
          "status": "complete"
        }
      ]
    },
    "clinical": { ... },
    "computational_biology": { ... },
    "translational": { ... }
  },
  "rejected": [
    {
      "pmc_id": "PMC67890",
      "reason": "No analyzable data files",
      "category": "basic_science"
    }
  ],
  "summary": {
    "total_papers": 18,
    "by_category": {"basic_science": 4, "clinical": 5, ...},
    "total_data_files": 42,
    "data_sources": {"geo": 8, "zenodo": 2, ...}
  }
}
```

### 7.2 Clean up temporary files

Remove the temporary metadata and filter JSON files created during the pipeline:
- `_metadata_candidates.json`
- Any `_filtered_*.json` files

### 7.3 Print summary

Present a final summary to the user:

```
Pipeline complete!

Papers by category:
  basic_science:          4 papers
  clinical:               5 papers
  computational_biology:  3 papers
  translational:          4 papers

Total: 16 papers with analyzable data
Data sources: 8 GEO, 2 Zenodo, 1 Figshare, 12 PMC supplementary
Rejected: 4 papers (no analyzable data)

All papers are organized in category subdirectories.
```
