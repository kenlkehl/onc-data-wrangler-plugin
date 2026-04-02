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

cohort_df, id_mapping = builder.build_from_dataframes(patient_df, diag_df, demo_dfs)

# Save outputs
out = Path(config.output_dir)
out.mkdir(parents=True, exist_ok=True)
cohort_df.to_parquet(out / "cohort.parquet", index=False)
with open(out / "cohort_ids.json", "w") as f:
    json.dump(id_mapping, f)

print(f"Cohort built: {len(cohort_df)} patients")
print(f"Columns: {list(cohort_df.columns)}")
PYEOF
```

Report: number of patients, demographic columns available, any filtering applied.

---

## STAGE 2: PREPARE NOTES

Validate that notes files exist and have the expected columns.

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
from onc_wrangler.config import load_config
import pandas as pd

config = load_config('CONFIG_PATH')
for path in config.resolve_notes_files():
    df = pd.read_csv(str(path), nrows=5)
    print(f'{path.name}: {len(pd.read_csv(str(path)))} rows, columns: {list(df.columns)}')
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

Spawn `extraction-worker` agents in batches of 5 with `run_in_background: true`.

For each patient:
1. Read their notes from the notes file
2. Spawn an extraction-worker agent with:
   - The patient's notes text
   - Ontology YAML path: `${CLAUDE_PLUGIN_ROOT}/data/ontologies/<ontology>/ontology.yaml`
   - Output path: `<output_dir>/extractions/<patient_id>.json`
   - The user's chosen model (from `config.extraction.claude_code_model`)

Pass `model: "<claude_code_model>"` to the Agent tool (e.g., `model: "sonnet"`).

After all agents complete, collect results and run validation.

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
from onc_wrangler.database.builder import build_database

config = load_config('CONFIG_PATH')
build_database(config)
print(f"Database built at: {config.db_path}")
PYEOF
```

---

## STAGE 6: METADATA

Generate schema and summary statistics:
```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
from onc_wrangler.config import load_config
from onc_wrangler.database.metadata import generate_schema, generate_summary_stats

config = load_config('CONFIG_PATH')
generate_schema(config)
generate_summary_stats(config)
print(f"Schema: {config.schema_path}")
print(f"Summary: {config.summary_path}")
PYEOF
```

---

## COMPLETION

After all stages complete:
1. Report summary: patients, fields extracted, database tables, any validation issues
2. Update `${CLAUDE_PLUGIN_DATA}/active_config.yaml` with the config
3. Suggest: `/onc-data-wrangler:query-database` to start querying
