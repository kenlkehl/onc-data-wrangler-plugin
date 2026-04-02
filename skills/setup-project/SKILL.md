---
name: setup-project
description: Interactive project setup wizard for oncology data wrangling. Discovers data files, profiles them, asks about configuration, and writes a YAML project config. Use when user wants to set up a new data wrangling project.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write
model: inherit
effort: high
---

# Setup Project

You are helping the user set up a new oncology data wrangling project. Walk through an interactive setup process to create a YAML configuration file.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`
Persistent data: `${CLAUDE_PLUGIN_DATA}`

---

## STEP 1: Discover Data Files

Ask the user where their data is located (directory path). Then:

1. Use Glob to find all data files: `*.csv`, `*.parquet`, `*.tsv`, `*.txt` (tabular data)
2. Use Glob to find documentation: `*.xlsx`, `*.pdf` (data dictionaries)
3. Use Glob to find clinical notes files

For each data file found, profile it with a Python one-liner via Bash:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
import pandas as pd
df = pd.read_csv('PATH', nrows=5)
print(f'Rows: {len(pd.read_csv(\"PATH\"))}')
print(f'Columns ({len(df.columns)}): {list(df.columns)}')
print(df.head(3).to_string())
"
```

Present findings to the user organized by category (structured data, clinical notes, documentation).

## STEP 2: Project Configuration

Ask the user for:

1. **Project name** (kebab-case identifier)
2. **Cancer type** (generic, lung, breast, prostate, colorectal, etc.)
3. **Ontology** -- list available ontologies by scanning `${CLAUDE_PLUGIN_ROOT}/data/ontologies/`:
   ```bash
   ls ${CLAUDE_PLUGIN_ROOT}/data/ontologies/
   ```
   Default: `naaccr` for cancer registry, `generic_cancer` for general oncology, `omop` for claims data
4. **Patient ID column** -- which column in the data identifies patients
5. **Cohort definition**:
   - Patient file (CSV/parquet with patient IDs)
   - Diagnosis file (optional, for filtering by ICD codes)
   - Demographics file(s)
   - Diagnosis code filter (e.g., `["C34"]` for lung cancer)
6. **Column mappings** (sex, race, ethnicity, birth_date, death_date columns)
7. **Notes configuration** (if clinical notes exist):
   - Notes file path(s)
   - Text column, date column, note type column, patient ID column in notes
8. **Extraction LLM backend**:
   - `openai` / `vllm`: Local OpenAI-compatible server (for PHI data)
   - `azure`: Azure OpenAI deployment
   - `anthropic` / `vertex`: Claude API
   - `claude-code`: Use Claude Code itself as the extractor
   - If `claude-code`: ask which model (opus, sonnet, haiku)
   - Otherwise: ask for base_url, model name, API key (or env var)
9. **Privacy mode** for querying:
   - `aggregate-only` (default): Only aggregate queries, cell suppression enforced
   - `individual-allowed`: Individual-level queries permitted, no cell suppression
   - `individual-with-audit`: Same as above but all queries are logged
10. **Output directory** for results

## STEP 3: Write Configuration

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
  # ... other cohort fields

extraction:
  llm:
    provider: <provider>
    model: <model>
    base_url: <url>  # if applicable
  claude_code_model: opus  # if provider is claude-code
  ontology_ids:
    - <ontology>
  cancer_type: <type>
  notes_paths:
    - <path>
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

Write the config to `<output_dir>/<project_name>_config.yaml`.

## STEP 4: Activate Config

Save the config path so the MCP server and other skills can find it:

```bash
mkdir -p ${CLAUDE_PLUGIN_DATA}
echo "<config_path>" > ${CLAUDE_PLUGIN_DATA}/active_config.yaml
```

Actually, copy the full config to `${CLAUDE_PLUGIN_DATA}/active_config.yaml` so the MCP server can load it directly.

Report the setup as complete and suggest next steps:
- `/onc-data-wrangler:run-pipeline` to run the full pipeline
- `/onc-data-wrangler:extract-notes` for standalone extraction
- `/onc-data-wrangler:query-database` if a database already exists
