---
name: make-database
description: Interactively build a DuckDB database from raw tabular data files. Discovers files, configures the project, builds cohort, loads structured data, and creates a queryable privacy-preserving database. Use when the user wants to go from raw data files to a DuckDB database.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write
model: inherit
effort: high
---

# Make Database

You are helping the user build a privacy-preserving DuckDB database from raw tabular data files. This is an interactive, end-to-end process: you discover their data, configure the project, build a cohort, load structured tables, and produce a queryable database — all in one session.

**IMPORTANT**: A previous `active_config.yaml` may exist from a prior project. Always start fresh based only on what the user tells you.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## STAGE 0: DISCOVER

Before anything else, remove any previous active config from the working directory so a prior project's settings don't leak into this session:

```bash
rm -f active_config.yaml
```

Ask the user where their data is located (directory path). Then:

1. Use Glob to find all tabular data files: `*.csv`, `*.parquet`, `*.tsv`
2. Use Glob to find documentation: `*.xlsx`, `*.pdf` (data dictionaries)

For each tabular data file found, profile it with a Python one-liner via Bash:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
import pandas as pd
df = pd.read_csv('PATH', nrows=5)
print(f'Rows: {len(pd.read_csv(\"PATH\"))}')
print(f'Columns ({len(df.columns)}): {list(df.columns)}')
print(df.head(3).to_string())
"
```

(Use `pd.read_parquet` for parquet files, `pd.read_csv(..., sep='\t')` for TSV files.)

Present findings to the user organized by file.

### Patient Identifier Detection

After profiling all files, automatically detect likely patient identifier columns:

1. **Collect all column names** from every profiled file.
2. **Pattern matching**: flag columns whose names match common patient ID patterns (case-insensitive):
   - Exact or close matches: `patient_id`, `patientid`, `pat_id`, `mrn`, `medical_record_number`, `record_id`, `subject_id`, `subjectid`, `person_id`, `empi`, `enterprise_id`, `study_id`, `participant_id`, `case_id`
   - Substring patterns: column name contains `_id` or `_mrn` combined with a clinical/patient term
3. **Cross-file analysis**: identify columns that appear in multiple files with the same name — these are likely join keys and strong patient ID candidates.
4. **Value heuristics**: for top candidates, check sample values — patient IDs tend to be unique per row (or nearly so), string/integer type, and not dates or free text.

Present your best guess (or top 2-3 candidates if ambiguous) to the user **for confirmation**, rather than asking them to name the column from scratch. If a single column clearly appears across all files, propose it as the default. If different files use different ID column names, propose the `patient_id_columns` per-file mapping.

---

## STAGE 1: CONFIGURE

Gather the following from the user interactively. Auto-detect and propose defaults wherever possible — don't make the user type what you can infer.

### Required

1. **Project name** (kebab-case identifier, e.g., `lung-cohort-2024`)
2. **Patient ID column** — present the auto-detected candidate(s) from Stage 0 and ask the user to confirm or correct. If different files use different ID columns, populate the `patient_id_columns` mapping.
3. **Cohort definition**:
   - Patient file (CSV/parquet with patient IDs — often the main demographics file)
   - Diagnosis file (optional, for filtering by ICD codes)
   - Demographics file(s) (may be the same as patient file)
   - Diagnosis code filter (e.g., `["C34"]` for lung cancer) — only if a diagnosis file is provided
4. **Output directory** for all results

### Optional (propose sensible defaults)

5. **Cancer type** (default: `generic`). The `generic` setting works for **pan-cancer projects** — the extraction engine auto-detects each patient's specific cancer type(s) from clinical text. Only set a specific type (lung, breast, prostate, colorectal, etc.) if the project is single-disease and the user indicates so. Default to `generic` without asking unless they mention a specific disease.
6. **Ontology** — list available ontologies by scanning `${CLAUDE_PLUGIN_ROOT}/data/ontologies/`:
   ```bash
   ls ${CLAUDE_PLUGIN_ROOT}/data/ontologies/
   ```
   Default: `naaccr` for cancer registry, `generic_cancer` for general oncology, `omop` for claims data. Only ask if the choice is ambiguous.
7. **Column mappings** for demographics: sex, race, ethnicity, birth_date, death_date. Auto-detect from column names where possible and confirm.
8. **Privacy mode** for querying:
   - `aggregate-only` (default): Only aggregate queries, cell suppression enforced
   - `individual-allowed`: Individual-level queries permitted
   - `individual-with-audit`: Same as above but all queries are logged

### Ontology Harmonization (Optional)

Before categorizing files, offer the user ontology-driven column harmonization. This maps source columns in their data files to standardized ontology fields, auto-populating `field_mappings` in the config so the Harmonizer produces standardized, category-based tables.

**Important**: A single input file can populate multiple database tables (e.g., one file has diagnosis, staging, and treatment columns → three tables). And multiple input files can contribute rows to the same table (e.g., two files both have diagnosis columns). Present mappings organized by ontology category to make this clear.

1. **Ask the user**: "Would you like to use an ontology to standardize your data columns? This maps your raw column names to a standard schema (e.g., `SITE_CD` → `primary_site`) and organizes tables by clinical category. If not, files will be loaded as-is with their original column names."

2. **If yes**, list available ontologies:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
from onc_wrangler.ontologies.registry import OntologyRegistry
registry = OntologyRegistry()
registry.discover()
for ont in registry.list_ontologies():
    cats = ont.get_categories()
    total_items = sum(len(c.items) for c in cats)
    print(f'{ont.ontology_id}: {ont.display_name} — {ont.description} ({len(cats)} categories, {total_items} fields)')
"
```

Present the list and let the user pick one. If the user already chose an ontology in step 6 (Optional settings), default to that one. Note: if an ontology has 0 fields (e.g., NAACCR whose items are loaded from CSV dictionaries at runtime), recommend `generic_cancer` or another ontology with inline field definitions for structured data harmonization.

3. **Load the chosen ontology's full structure** (categories, items with descriptions, data types, and valid values):

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
from onc_wrangler.ontologies.registry import OntologyRegistry
registry = OntologyRegistry()
registry.discover()
ont = registry.get('ONTOLOGY_ID')
for cat in ont.get_categories():
    print(f'Category: {cat.id} — {cat.name}')
    print(f'  Description: {cat.description}')
    for item in cat.items:
        vv = ''
        if item.valid_values:
            vv = ' | valid: ' + ', '.join(v.code for v in item.valid_values[:8])
        print(f'  - {item.id} ({item.data_type}): {item.description[:100]}{vv}')
    print()
"
```

4. **For each non-cohort tabular file**, semantically match source columns to ontology fields. Use the column names, sample data (from Stage 0 profiling), ontology field descriptions, and data types to propose mappings. Follow these rules:
   - Match by semantic meaning, not just name similarity (e.g., `DRUG_NAMES` → `regimen_drug_list`, `HIST_DESC` → `histology`)
   - A source column maps to exactly one target field in one category
   - A single file's columns may span multiple categories — this is expected and correct
   - Multiple files may contribute columns to the same category
   - The patient ID column is NOT mapped — it is handled separately by the Harmonizer
   - Only propose mappings you are reasonably confident about — do not force marginal matches
   - Date columns should be matched to date-typed target fields

5. **Present proposed mappings** organized by **ontology category**, showing which file each source column comes from:

```
Proposed ontology mappings (ONTOLOGY_NAME):

→ Table: cancer_diagnosis
    tumor_registry.csv: SITE_CD       → primary_site
    tumor_registry.csv: HIST_DESC     → histology
    tumor_registry.csv: STAGE_GRP     → overall_stage_at_diagnosis
    pathology.csv:      SITE_CODE     → primary_site
    pathology.csv:      GRADE         → grade

→ Table: cancer_systemic_therapy_regimen
    treatment.csv:      DRUG_NAMES    → regimen_drug_list
    treatment.csv:      TX_START      → regimen_start_date
    treatment.csv:      TX_END        → regimen_end_date

→ Table: cancer_biomarker
    lab_results.csv:    TEST_NAME     → biomarker_tested
    lab_results.csv:    TEST_RESULT   → biomarker_result

Unmapped columns per file:
  tumor_registry.csv: [COL_A, COL_B]
  treatment.csv: [COL_X]
  imaging.csv: (no mappings found — will go to File Categorization)
```

Ask the user to confirm, remove individual mappings, or add any missed ones. If the user wants to add a transform (e.g., `lowercase`, `date_to_yyyy_mm_dd`, `to_string`, `to_numeric`) or value_map for any mapping, accommodate that.

6. **Record confirmed mappings** for use when writing the config in Stage 2. The mappings will be written as the `field_mappings` section using this format:

```yaml
field_mappings:
  cancer_diagnosis:
    - source: SITE_CD
      target: primary_site
    - source: HIST_DESC
      target: histology
    - source: STAGE_GRP
      target: overall_stage_at_diagnosis
    - source: SITE_CODE
      target: primary_site
    - source: GRADE
      target: grade
  cancer_systemic_therapy_regimen:
    - source: DRUG_NAMES
      target: regimen_drug_list
    - source: TX_START
      target: regimen_start_date
    - source: TX_END
      target: regimen_end_date
  cancer_biomarker:
    - source: TEST_NAME
      target: biomarker_tested
    - source: TEST_RESULT
      target: biomarker_result
```

7. **Track which files were fully handled**. A file is "fully handled" if at least one of its non-ID columns was mapped to an ontology field. Files with zero accepted mappings are "unhandled" and proceed to File Categorization.

**If the user declines ontology harmonization** (says no in step 1), skip this entire section and proceed directly to File Categorization with `field_mappings: {}`.

### File Categorization

For each tabular file that is NOT the patient/diagnosis/demographics file **and was NOT handled by ontology harmonization above**, ask the user how to handle it:

- **"Load as database table"** — include it as a separate table in the DuckDB. Ask for a short table name (e.g., `encounters`, `labs`, `medications`). Record these files and their table names for Stage 4.
- **"Skip"** — exclude from the database.

If ontology harmonization was used, first summarize: "The following files are mapped via ontology harmonization and will produce standardized tables: [list files and their target categories]. The remaining files need categorization:"

If there are many uncategorized files, present the list and let the user batch-categorize (e.g., "load all of these as tables").

Note: Files handled by ontology harmonization are processed in Stage 4 via the Harmonizer. Files categorized here as "load as database table" are processed in Stage 4 as direct table loads.

---

## STAGE 2: WRITE & ACTIVATE CONFIG

Construct the YAML config and write it. Use this structure:

```yaml
project:
  name: <name>
  input_paths:
    - <path1>
    - <path2>
  output_dir: <output_dir>

cohort:
  patient_file: <path>
  patient_id_column: <col>
  diagnosis_file: <path>           # if applicable
  diagnosis_code_column: <col>     # if applicable
  diagnosis_code_filter:           # if applicable
    - "C34"
  demographics_files:
    - <path>
  column_mappings:
    sex: <col or null>
    race: <col or null>
    ethnicity: <col or null>
    birth_date: <col or null>
    death_date: <col or null>

extraction:
  llm:
    provider: claude-code
    model: ""
    base_url: ""
  claude_code_model: opus
  ontology_ids:
    - <ontology>
  cancer_type: <type>
  notes_paths: []
  notes_text_column: text
  notes_date_column: date
  patient_id_column: <col>

database:
  deidentify_dates: true
  record_id_prefix: patient
  min_non_missing: 10

query:
  privacy_mode: <mode>
  min_cell_size: 10
  max_query_rows: 500

field_mappings: {}
patient_id_columns: {}
```

If ontology harmonization was configured in Stage 1, populate the `field_mappings` section with the user-confirmed mappings instead of `{}`. Use the category-based format shown in the Ontology Harmonization step. The category IDs must match the ontology's category IDs exactly.

**Note:** The `extraction` section is populated with defaults. If the user later wants to extract from clinical notes, they can update these fields and run `/onc-data-wrangler:extract-notes`.

Write the config to `<output_dir>/<project_name>_config.yaml`.

Then activate it by copying to the working directory (the query CLI auto-discovers it here):

```bash
cp <output_dir>/<project_name>_config.yaml active_config.yaml
```

Validate the config:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
from onc_wrangler.config import load_config
config = load_config('CONFIG_PATH')
errors = config.validate()
if errors:
    for e in errors: print(f'ERROR: {e}')
else:
    print(f'Config OK: project={config.name}')
    print(f'Output dir: {config.output_dir}')
"
```

---

## STAGE 3: BUILD COHORT

Build the patient roster with demographics and de-identification.

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
from onc_wrangler.config import load_config
from onc_wrangler.cohort.builder import CohortBuilder
import pandas as pd, json
from pathlib import Path

config = load_config('CONFIG_PATH')
builder = CohortBuilder(config.cohort)

# Load patient file
patient_df = pd.read_csv(config.cohort.patient_file) if config.cohort.patient_file else None

# Load diagnosis file
diag_df = None
if config.cohort.diagnosis_file:
    diag_df = pd.read_csv(config.cohort.diagnosis_file)

# Load demographics
demo_dfs = []
for f in config.cohort.demographics_files:
    demo_dfs.append(pd.read_csv(f))

cohort_df = builder.build_from_dataframes(
    patient_df, diagnosis_df=diag_df, demographics_dfs=demo_dfs if demo_dfs else None
)

# Build ID mapping from builder's stored original_ids
id_mapping = dict(zip(builder.original_ids, cohort_df["record_id"].tolist()))

# Save outputs
out = Path(config.output_dir)
out.mkdir(parents=True, exist_ok=True)
cohort_df.to_parquet(out / "cohort.parquet", index=False)
with open(out / "cohort_ids.json", "w") as f:
    json.dump(id_mapping, f)

print(f"Cohort built: {len(cohort_df)} patients")
print(f"Columns: {list(cohort_df.columns)}")
print(f"ID mapping entries: {len(id_mapping)}")
PYEOF
```

Report: number of patients, demographic columns available, any filtering applied.

---

## STAGE 4: LOAD ADDITIONAL TABLES

This stage loads additional tabular files (categorized in Stage 1) into the `harmonized/` directory so the DatabaseBuilder can pick them up.

### Files with field_mappings configured

If `field_mappings` are present in the config (either from the ontology harmonization step in Stage 1, or configured manually):

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
from onc_wrangler.config import load_config
from onc_wrangler.harmonization.harmonizer import Harmonizer
import pandas as pd
from pathlib import Path

config = load_config('CONFIG_PATH')
if config.field_mappings:
    harmonizer = Harmonizer.from_config(config.field_mappings)
    for f in config.resolve_input_files():
        df = pd.read_csv(str(f))
        result = harmonizer.harmonize(df, patient_id_column=config.cohort.patient_id_column)
        for category, harmonized_df in result.items():
            out_path = Path(config.output_dir) / "harmonized" / f"{f.stem}_{category}.parquet"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            harmonized_df.to_parquet(out_path, index=False)
            print(f"Harmonized {f.name} -> {category}: {len(harmonized_df)} rows")
else:
    print("No field_mappings configured.")
PYEOF
```

### Files categorized as "load as database table"

For each file the user chose to load as a separate table (with no field mappings), convert it to parquet in the `harmonized/` directory using the table name they chose:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import pandas as pd
from pathlib import Path

# Repeat this block for each additional file
source_path = "SOURCE_FILE_PATH"
table_name = "TABLE_NAME"
output_dir = "OUTPUT_DIR"

# Read the file
if source_path.endswith(".parquet"):
    df = pd.read_parquet(source_path)
elif source_path.endswith(".tsv"):
    df = pd.read_csv(source_path, sep="\t")
else:
    df = pd.read_csv(source_path)

# Save to harmonized directory — DatabaseBuilder._load_harmonized will handle:
#   - Renaming the patient ID column to record_id
#   - De-identifying patient IDs via cohort_ids.json
#   - Stripping PII columns
#   - Filtering sparse columns
out_path = Path(output_dir) / "harmonized" / f"{table_name}.parquet"
out_path.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(out_path, index=False)
print(f"Loaded {source_path} -> harmonized/{table_name}.parquet: {len(df)} rows, {len(df.columns)} columns")
PYEOF
```

If no additional files were categorized, skip this stage and report "No additional tables to load."

---

## STAGE 5: BUILD DATABASE

Build the de-identified DuckDB database:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
from onc_wrangler.config import load_config
from onc_wrangler.database.builder import DatabaseBuilder

config = load_config('CONFIG_PATH')
builder = DatabaseBuilder(config)
db_path = builder.build()
print(f"Database built at: {db_path}")
PYEOF
```

---

## STAGE 6: GENERATE METADATA

Generate schema and summary statistics:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import duckdb, json
from pathlib import Path
from onc_wrangler.config import load_config
from onc_wrangler.database.metadata import generate_schema, generate_summary_stats

config = load_config('CONFIG_PATH')
con = duckdb.connect(str(config.db_path), read_only=True)

forbidden = set(config.database.forbidden_output_columns) if config.database.forbidden_output_columns else None

schema_md = generate_schema(con, project_name=config.name, forbidden_columns=forbidden)
schema_path = Path(config.output_dir) / "schema.md"
schema_path.write_text(schema_md)
print(f"Schema written to: {schema_path}")

summary = generate_summary_stats(con, project_name=config.name, forbidden_columns=forbidden, min_cell_size=config.query.min_cell_size)
summary_path = Path(config.output_dir) / "summary_stats.json"
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)
print(f"Summary written to: {summary_path}")

con.close()
PYEOF
```

---

## STAGE 7: COMPLETION

After all stages complete:

1. Report summary: number of patients, tables created, columns per table
2. Confirm `active_config.yaml` exists in the working directory
3. Suggest next steps:
   - `/onc-data-wrangler:aggregate-database-query` to start querying the database
   - `/onc-data-wrangler:derive-dataset` to build a one-row-per-patient analysis dataset
   - `/onc-data-wrangler:extract-notes` to add clinical notes extraction later (update the `extraction` section of the config first)
