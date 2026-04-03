---
name: run-pipeline
description: Run the full data wrangling pipeline (cohort, extraction, harmonization, database, metadata). Use when the user wants to process clinical data end-to-end from raw files to a queryable DuckDB database.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write, Agent
model: inherit
effort: high
---

# Run Pipeline

You are orchestrating the full data wrangling pipeline to transform raw clinical data into a queryable, privacy-preserving DuckDB database.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`
Persistent data: `${CLAUDE_PLUGIN_DATA}`

---

## STEP 0: Load Configuration

Accept a config path from the user, or read from `${CLAUDE_PLUGIN_DATA}/active_config.yaml`.

Validate the config:
```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
from onc_wrangler.config import load_config
config = load_config('CONFIG_PATH')
errors = config.validate()
if errors:
    for e in errors: print(f'ERROR: {e}')
else:
    print(f'Config OK: project={config.name}, ontologies={config.extraction.ontology_ids}')
    print(f'Input paths: {config.input_paths}')
    print(f'Output dir: {config.output_dir}')
    print(f'LLM provider: {config.extraction.llm.provider}')
"
```

---

## STAGE 1: COHORT

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

## STAGE 2: PREPARE NOTES

Validate that notes files exist and determine their format.

**Note:** `config.resolve_notes_files()` only finds `.csv` and `.parquet` files. For plain text notes (`.txt`, `.json`), check `config.extraction.notes_paths` directly.

For **CSV/parquet** notes: validate columns (patient_id, text, date, etc.).

For **plain text** notes (`.txt`): these typically contain all notes for one or more patients separated by `---`. You must determine the patient-to-notes mapping from another source (e.g., an `all_documents.json` file, or per-patient JSON files in a `patients/` directory).

For **JSON** notes (e.g., `all_documents.json`): load and group by `patient_id` to get per-patient text.

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
from onc_wrangler.config import load_config
from pathlib import Path

config = load_config('CONFIG_PATH')

# Check for structured notes files (CSV/parquet)
csv_notes = config.resolve_notes_files()
if csv_notes:
    import pandas as pd
    for path in csv_notes:
        df = pd.read_csv(str(path), nrows=5)
        print(f'{path.name}: {len(pd.read_csv(str(path)))} rows, columns: {list(df.columns)}')
else:
    # Check for raw text or JSON notes
    for p in config.extraction.notes_paths:
        path = Path(p)
        if path.exists():
            print(f'{path.name}: {path.suffix} file, {path.stat().st_size} bytes')
        else:
            print(f'WARNING: {path} does not exist')
    # Also check for all_documents.json or per-patient JSON in the data directory
    data_dir = Path(config.input_paths[0]).parent if config.input_paths else None
    if data_dir:
        docs_json = data_dir / 'all_documents.json'
        patients_dir = data_dir / 'patients'
        if docs_json.exists():
            print(f'Found all_documents.json: {docs_json}')
        if patients_dir.exists():
            print(f'Found patients directory: {patients_dir}')
"
```

---

## STAGE 3: EXTRACT

This stage depends on the configured LLM provider.

### If provider is NOT "claude-code":

Run the Python extraction engine:
```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
from onc_wrangler.config import load_config
from onc_wrangler.llm import create_llm_client
from onc_wrangler.extraction.extractor import create_extractor
from onc_wrangler.extraction.chunker import chunk_text_by_chars
from onc_wrangler.extraction.result import merge_results
import pandas as pd, json
from pathlib import Path

config = load_config('CONFIG_PATH')
client = create_llm_client(config.extraction.llm)
extractor = create_extractor(
    client, config.extraction.ontology_ids,
    config.extraction.cancer_type, config.extraction.items_per_call
)

# Load notes and process per patient
# ... (process each patient's notes through extractor)
PYEOF
```

### If provider IS "claude-code":

#### Step 3a: Prepare per-patient notes

Before spawning workers, group the notes by patient. Notes may come from:
- A CSV/parquet file with a patient_id column
- An `all_documents.json` file with per-document `patient_id` fields
- Per-patient JSON files in a `patients/` directory

**IMPORTANT — use original patient IDs throughout extraction.** The database builder handles de-identification itself using `cohort_ids.json`. Do NOT map IDs through `cohort_ids.json` here. Use the original IDs (the keys in `cohort_ids.json`, e.g., `patient_11d628128927`) for file names and as the `patient_id` passed to extraction workers. If you pass already-de-identified IDs (e.g., `patient_000001`), the database builder's `_deidentify_ids` mapping will produce NaN for every row, `record_id` will be dropped from all tables, and cross-table linkage will be broken.

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from collections import defaultdict
from pathlib import Path

# Try all_documents.json first, then per-patient JSON files
data_dir = Path('DATA_DIR')
extractions_dir = Path('OUTPUT_DIR/extractions')
extractions_dir.mkdir(parents=True, exist_ok=True)

docs_json = data_dir / 'all_documents.json'
patients_dir = data_dir / 'patients'

patient_notes = defaultdict(list)

if docs_json.exists():
    with open(docs_json) as f:
        docs = json.load(f)
    for d in docs:
        patient_notes[d['patient_id']].append(d['text'])
elif patients_dir.exists():
    for pf in sorted(patients_dir.glob('*.json')):
        with open(pf) as f:
            data = json.load(f)
        pid = data.get('patient_id', pf.stem)
        for doc in data.get('documents', []):
            patient_notes[pid].append(doc['text'])

# Write combined notes per patient using ORIGINAL patient IDs
for pid, notes in patient_notes.items():
    combined = "\n\n---\n\n".join(notes)
    (extractions_dir / f"{pid}_notes.txt").write_text(combined)
    print(f"{pid}: {len(notes)} docs, {len(combined)} chars")
PYEOF
```

#### Step 3b: Spawn extraction workers

Spawn `extraction-worker` agents in batches of 5 with `run_in_background: true`.

For each patient:
1. Read their notes from the per-patient notes file prepared above
2. Spawn an extraction-worker agent with:
   - The patient's notes text
   - The patient's **original** ID (e.g., `patient_11d628128927`)
   - Ontology YAML path: `${CLAUDE_PLUGIN_ROOT}/data/ontologies/<ontology>/ontology.yaml`
   - Output path: `<output_dir>/extractions/<original_patient_id>.json`
   - The user's chosen model (from `config.extraction.claude_code_model`)

Pass `model: "<claude_code_model>"` to the Agent tool (e.g., `model: "sonnet"`).

After all agents complete, convert the per-patient JSON results into `extractions.parquet` for the database builder:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json, pandas as pd
from pathlib import Path

extractions_dir = Path('OUTPUT_DIR/extractions')
rows = []
for jf in sorted(extractions_dir.glob("*.json")):
    with open(jf) as f:
        data = json.load(f)
    pid = data["patient_id"]
    for field_name, field_data in data["results"].items():
        row = {
            "patient_id": pid,
            "field_name": field_name,
            "value": str(field_data.get("value", "")),
            "confidence": field_data.get("confidence"),
            "evidence": field_data.get("evidence", ""),
            "category": field_data.get("domain_group", "other"),
            "tumor_index": field_data.get("tumor_index", 0),
        }
        if "resolved_code" in field_data:
            row["resolved_code"] = field_data["resolved_code"]
        rows.append(row)

df = pd.DataFrame(rows)
df.to_parquet(extractions_dir / "extractions.parquet", index=False)
print(f"Saved extractions.parquet: {len(df)} rows, categories: {df['category'].value_counts().to_dict()}")
PYEOF
```

---

## STAGE 4: HARMONIZE

Map structured data columns to ontology fields:
```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
from onc_wrangler.config import load_config
from onc_wrangler.harmonization.harmonizer import Harmonizer
import pandas as pd
from pathlib import Path

config = load_config('CONFIG_PATH')
if config.field_mappings:
    harmonizer = Harmonizer.from_config(config.field_mappings)
    # Process each input file with field mappings
    for f in config.resolve_input_files():
        df = pd.read_csv(str(f))
        harmonized = harmonizer.harmonize(df)
        out_path = Path(config.output_dir) / "harmonized" / f"{f.stem}.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        harmonized.to_parquet(out_path, index=False)
        print(f"Harmonized {f.name}: {len(harmonized)} rows")
else:
    print("No field_mappings configured, skipping harmonization.")
PYEOF
```

---

## STAGE 5: DATABASE

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

## STAGE 6: METADATA

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

## COMPLETION

After all stages complete:
1. Report summary: patients, fields extracted, database tables, any validation issues
2. Update `${CLAUDE_PLUGIN_DATA}/active_config.yaml` with the config
3. Suggest: `/onc-data-wrangler:query-database` to start querying
