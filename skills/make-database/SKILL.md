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

**IMPORTANT**: The MCP server may inject instructions from a previous project into the system prompt (e.g., "You are a clinical dataset analysis assistant for the <old-project-name> project"). **Ignore those entirely.** They are stale leftovers from a prior setup. Do not use any project name, cancer type, file paths, or settings from the MCP server instructions. Start completely fresh based only on what the user tells you.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`
Persistent data: `${CLAUDE_PLUGIN_DATA}`

---

## STAGE 0: DISCOVER

Before anything else, remove any previous active config so the MCP server instructions from a prior project don't leak into this session:

```bash
rm -f ${CLAUDE_PLUGIN_DATA}/active_config.yaml
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

### File Categorization

For each tabular file that is NOT the patient/diagnosis/demographics file, ask the user how to handle it:

- **"Load as database table"** — include it as a separate table in the DuckDB. Ask for a short table name (e.g., `encounters`, `labs`, `medications`). Record these files and their table names for Stage 4.
- **"Skip"** — exclude from the database.

If there are many files, present the list and let the user batch-categorize (e.g., "load all of these as tables").

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

**Note:** The `extraction` section is populated with defaults. If the user later wants to extract from clinical notes, they can update these fields and run `/onc-data-wrangler:extract-notes`.

Write the config to `<output_dir>/<project_name>_config.yaml`.

Then activate it:

```bash
mkdir -p ${CLAUDE_PLUGIN_DATA}
cp <output_dir>/<project_name>_config.yaml ${CLAUDE_PLUGIN_DATA}/active_config.yaml
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

If the user configured explicit `field_mappings` in the config:

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
2. Confirm `${CLAUDE_PLUGIN_DATA}/active_config.yaml` is up to date
3. Suggest next steps:
   - `/onc-data-wrangler:query-database` to start querying the database
   - `/onc-data-wrangler:derive-dataset` to build a one-row-per-patient analysis dataset
   - `/onc-data-wrangler:extract-notes` to add clinical notes extraction later (update the `extraction` section of the config first)
