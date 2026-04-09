# onc-data-wrangler

A Claude Code plugin for oncology data wrangling and analysis: extracting structured data from clinical notes, building privacy-preserving DuckDB databases, querying cohorts, and reproducing published paper results.

> **Do not send real Protected Health Information (PHI) to any LLM endpoint that is not covered by an institutional Business Associate Agreement (BAA)!** Cloud LLM APIs — including the Anthropic API, OpenAI API, Google Vertex/AI Studio, and Azure OpenAI — are **not** BAA-covered by default. If you are working with real patient data, use a locally hosted model (see [Running with a Local Model](#running-with-a-local-model)) or confirm that your institution has a signed BAA with the provider **and** that the specific endpoint you are using is within scope. When in doubt, treat the data as PHI and keep it on-premises. You take all responsibility for where you are sending data; if in doubt about your configuration, do not use!

## Example Synthetic Data

The repository includes a set of pre-generated synthetic clinical data in `example_synthetic_data/`. This dataset was produced by the `generate-synthetic-data` skill and covers 50 patients across multiple cancer scenarios (NSCLC, breast, renal cell carcinoma, head & neck, and others). It contains:

- **`documents/`** — 946 individual clinical document JSON files (progress notes, imaging reports, pathology reports, NGS reports)
- **`notes.csv`** — The same documents collected into a single CSV (one row per note, columns: `patient_id`, `text`, `date`, `note_type`) ready for use with the `extract-notes` skill
- **`structured/`** — Per-patient structured data (encounters, labs, medications, hospitalizations, patient-reported outcomes)
- **`tables/`** — Combined CSVs (encounters, labs, medications, hospitalizations, PROs) with `scenario_index` and `scenario_label` columns

This data is entirely synthetic and contains no real patient information. It can be used to test extraction pipelines, build example databases, or explore the plugin's capabilities without any PHI concerns.

## Installation & Quick Start

### 1. Install Claude Code

Follow the [Claude Code setup instructions](https://docs.anthropic.com/en/docs/claude-code/setup) to install Claude Code:

```bash
# macOS / Linux
curl -fsSL https://claude.ai/install.sh | sh

# Windows (PowerShell)
irm https://claude.ai/install.ps1 | iex
```

### 2. Install the plugin dependencies

```bash
# Install uv (Python package manager) if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh  # or: pip install uv

# Install plugin dependencies (requires Python 3.13+)
cd /path/to/onc-data-wrangler-plugin
uv sync
```

### 3. (Optional) Set up a local model

If your data cannot leave your network, you can run Claude Code entirely against a local model using **vLLM** or **Ollama**.

#### Option A: vLLM

Install and start vLLM. For example, Gemma 4 31B works reasonably well; you can follow the [Gemma 4 usage guide](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html). See also the [vLLM Claude Code integration docs](https://docs.vllm.ai/en/stable/serving/integrations/claude_code/).

```bash
# Start the vLLM server (example with Gemma 4 31B)
vllm serve nvidia/Gemma-4-31b-IT-NVFP4 \
  --quantization modelopt \
  --enable-auto-tool-choice \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --served-model-name gemma4-31b
```

Then launch Claude Code pointed at the local server:

```bash
CLAUDE_CODE_USE_VERTEX=0 \
ANTHROPIC_BASE_URL=http://localhost:8000 \
ANTHROPIC_API_KEY=dummy \
ANTHROPIC_AUTH_TOKEN=dummy \
ANTHROPIC_DEFAULT_OPUS_MODEL=gemma4-31b \
ANTHROPIC_DEFAULT_SONNET_MODEL=gemma4-31b \
ANTHROPIC_DEFAULT_HAIKU_MODEL=gemma4-31b \
claude --model opus --plugin-dir .
```

#### Option B: Ollama

Install [Ollama](https://ollama.com/download) and pull a model. See the [Ollama Claude Code integration docs](https://docs.ollama.com/integrations/claude-code) for full details.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model and launch Claude Code
ollama pull gemma4
ollama launch claude-code
```

### 4. Launch Claude Code with the plugin

```bash
# With the Anthropic API (default)
claude --plugin-dir .

# Then use the plugin skills inside Claude Code:
#   /onc-data-wrangler:make-database
#   /onc-data-wrangler:aggregate-database-query
#   /onc-data-wrangler:derive-dataset
#   /onc-data-wrangler:extract-notes
#   /onc-data-wrangler:generate-synthetic-data
```

## Skills

| Skill | Command | Description |
|-------|---------|-------------|
| Make Database | `/onc-data-wrangler:make-database` | Interactively build a DuckDB database from raw tabular data files |
| Extract Notes | `/onc-data-wrangler:extract-notes` | Standalone extraction from clinical notes |
| Aggregate Database Query | `/onc-data-wrangler:aggregate-database-query` | Interactive database querying with privacy enforcement |
| Reproduce Paper | `/onc-data-wrangler:reproduce-paper` | Reproduce published paper results from raw data |
| Build Ontology | `/onc-data-wrangler:build-ontology` | Create custom ontology from a data dictionary |
| Red-Team | `/onc-data-wrangler:red-team` | Test agent resistance to prompt injection PHI exfiltration |
| Generate Synthetic Data | `/onc-data-wrangler:generate-synthetic-data` | Generate synthetic clinical data (events, documents, structured tables) from a text description |
| Answer Questions | `/onc-data-wrangler:answer-questions` | Answer clinical questions about patients from their notes with confidence scores |
| Derive Dataset | `/onc-data-wrangler:derive-dataset` | Create a one-row-per-patient analysis dataset with biostatistics guidance and reproducible script |
| Analyze Data | `/onc-data-wrangler:analyze-data` | Interactive Python-based data analysis with oncology domain knowledge |

## Extraction LLM Backends

The extraction engine supports multiple LLM backends:

- **Local models** (`provider: openai`): Any OpenAI-compatible server (vLLM, Ollama, TGI, etc.). For PHI data that can't leave the network.
- **Azure OpenAI** (`provider: azure`): Institutional Azure deployments.
- **Claude API** (`provider: anthropic` or `vertex`): Direct Anthropic API or Google Vertex AI.
- **Claude Code** (`provider: claude-code`): Claude Code itself acts as the extractor. Specify which model with `claude_code_model: opus|sonnet|haiku`.

## Synthetic Data Generation

The `generate-synthetic-data` skill creates realistic synthetic clinical data from one or more clinical scenario descriptions. Each scenario is a short text blurb (e.g., "Stage III NSCLC patients with EGFR L858R mutation") paired with a patient count.

**Multi-scenario support:** Provide a single blurb, an inline list of scenarios, or a JSON/CSV file. Each scenario specifies its own patient count and optional label. Patients are tagged with their originating scenario throughout all outputs.

```json
[
  {"blurb": "Stage III NSCLC with EGFR L858R", "n_patients": 5, "label": "nsclc_egfr"},
  {"blurb": "Metastatic HER2+ breast cancer", "n_patients": 3, "label": "breast_her2"}
]
```

**Pipeline stages:**
1. **Event generation** — Creates 20-30 chronological clinical events per patient (diagnoses, treatments, notes, imaging, pathology, NGS reports). Runs once per scenario.
2. **Document generation** — Produces realistic clinical documents (progress notes, imaging reports, pathology reports, NGS reports) for each document-type event
3. **Structured data generation** — Creates tabular data (encounters, labs) consistent with the events and documents

**Inference modes:** Same as extraction — use `claude-code` to have Claude Code generate the data directly, or specify an external LLM provider.

**Extensible table schemas:** Add new structured table types (medications, vitals, procedures, etc.) by dropping a YAML file in `data/synthetic_schemas/`. The pipeline discovers and generates data for all schemas automatically.

**Output:**
- `all_documents.json` — Combined clinical documents
- `tables/encounters.csv` — One row per clinical encounter (includes `scenario_index`/`scenario_label` when multi-scenario)
- `tables/labs.csv` — One row per lab result
- `summary.json` — Generation metadata with per-scenario breakdown

## Derive Dataset

The `derive-dataset` skill creates a **one-row-per-patient analysis dataset** from a DuckDB database (built by `make-database`) or raw tabular files. It combines interactive column definition with oncology and biostatistics domain expertise.

**Typical workflow:**
```
/onc-data-wrangler:make-database    # discover data, configure project, build DuckDB
/onc-data-wrangler:derive-dataset   # create analysis dataset
```

**Key features:**

- **Interactive column definition** — Describe columns in natural language (e.g., "overall survival time", "stage as binary IV vs I-III") or reference database columns directly. A running column tracker and 5-row preview update after each addition.
- **Oncology domain guidance** — Disambiguates clinically important distinctions:
  - *Stage IV vs advanced vs metastatic*: de novo stage IV only, or including recurrent metastatic disease?
  - *Line of therapy*: relative to what index event (metastatic diagnosis, initial diagnosis, surgery)?
  - *Survival endpoints*: time zero definition, event indicators, censoring rules
- **Biostatistics guidance** — Proactively identifies methodological pitfalls:
  - Left truncation / delayed entry for referral-based cohorts (immortal time bias)
  - Risk set adjustment requiring both `entry_time` and `event_time` fields
  - Multi-tumor patient handling and many-to-one aggregation strategies
- **Reproducible script** — Generates a standalone Python script (`derive_dataset.py`) using only `duckdb` + `pandas` + `numpy`. The script recreates the exact dataset without any plugin dependencies.

**Outputs:**
- `analysis_dataset.csv` — The final one-row-per-patient dataset
- `derive_dataset.py` — Standalone reproducible derivation script

## Privacy Modes

The query system supports three privacy modes (set in project config):

| Mode | Aggregate Queries | Individual Queries | Cell Suppression | Audit Log |
|------|------------------|--------------------|-----------------|-----------|
| `aggregate-only` (default) | Yes | No | Yes | No |
| `individual-allowed` | Yes | Yes | Aggregate only | No |
| `individual-with-audit` | Yes | Yes | Aggregate only | Yes |

## Built-in Ontologies

- **naaccr**: NAACCR v26 cancer registry (771 items, 22 cancer schemas)
- **generic_cancer**: General oncology fields
- **omop**: OMOP CDM clinical fields
- **msk_chord**: MSK-CHORD dataset fields
- **prissmm**: PRISSMM classification fields
- **pan_top**: Pan-cancer therapy ontology
- **matchminer_ai**: MatchMiner AI clinical fields
- **clinical_summary**: Free-text clinical summaries


## Security Considerations

### API Key Management

API keys are resolved from environment variables — **never store keys in config files**:
- `ANTHROPIC_API_KEY` for Claude API (`provider: anthropic`)
- `OPENAI_API_KEY` for OpenAI-compatible servers (`provider: openai`)
- `AZURE_OPENAI_API_KEY` for Azure deployments (`provider: azure`)
- `ANTHROPIC_VERTEX_PROJECT_ID` for Vertex AI (`provider: vertex`)

### Protected Health Information (PHI)

**For data that cannot leave your network**, use a local model:
```yaml
extraction:
  llm:
    provider: openai
    base_url: "http://localhost:8000/v1"
    model: "your-local-model"
```
This keeps all clinical text on-premises. The `openai` provider works with any OpenAI-compatible API server (vLLM, Ollama, TGI, etc.).

### De-identification

The database builder applies multiple layers of de-identification:
- **PII column stripping**: Columns containing MRN, SSN, patient names, addresses, phone numbers, and email are automatically removed
- **ID anonymization**: Original patient IDs are replaced with sequential de-identified IDs (e.g., `patient_000001`)
- **Date de-identification** (optional): When `database.deidentify_dates: true`, dates are converted to years-since-birth and calendar year only

### Query Privacy

The query system enforces privacy at multiple levels (see [Privacy Modes](#privacy-modes) table):
- **SQL validation**: Blocks DDL/DML statements, `SELECT *`, and forbidden columns (e.g., `record_id`) in output
- **Aggregation required**: In `aggregate-only` mode, queries must contain `GROUP BY` or aggregate functions
- **Cell suppression**: Counts below `min_cell_size` (default: 10) are replaced with `<N`; associated rates are marked `suppressed`
- **Output size guard**: Queries returning more than 50% of the cohort are rejected to prevent row-level data exfiltration
- **Audit logging**: In `individual-with-audit` mode, all queries are logged with timestamps and result hashes to `query_audit.jsonl`

### Agent Isolation

Subagent workers (extraction, analysis, validation) are sandboxed:
- No internet access (`WebSearch` and `WebFetch` are disallowed)
- Each worker processes exactly one patient or question
- Workers cannot communicate with each other or access other patients' data

### Red-Team Testing

Test your deployment's resistance to prompt injection attacks using `/onc-data-wrangler:red-team`. This runs scenarios that attempt to trick the agent into exfiltrating synthetic PHI data, and reports pass/fail rates.

## Configuration

See `configs/example_project.yaml` for a complete configuration reference.

## Architecture

```
Plugin (skills, agents, query CLI)
  |
  ├── Skills orchestrate workflows (setup, pipeline, query, reproduce)
  ├── Agents parallelize work (extraction, analysis, validation)
  ├── Query CLI (scripts/query.py) wraps DuckDB with privacy enforcement
  |
  └── Internal Python package (src/onc_wrangler/)
      ├── config.py          - YAML configuration
      ├── llm/               - LLM client abstraction
      ├── cohort/             - Patient roster building
      ├── database/           - DuckDB creation & metadata
      ├── extraction/         - Extraction engine & utilities
      ├── harmonization/      - Column-to-field mapping
      ├── ontologies/         - Ontology loading & registry
      ├── output/             - NAACCR output formats
      ├── query/              - SQL validation & privacy
      └── synthetic/          - Synthetic data generation pipeline
```

## Running with a Local Model

You can run Claude Code itself against a local model, keeping all data — including the agent's reasoning — on-premises. This is separate from the extraction LLM backend; it replaces the Claude API for the entire Claude Code session. See the [Installation & Quick Start](#installation--quick-start) section above for setup instructions.

### Wrapper script (vLLM)

For convenience, save the vLLM launch command as a shell script (e.g., `localclaude`):

```bash
#!/usr/bin/env bash
CLAUDE_CODE_USE_VERTEX=0 \
ANTHROPIC_BASE_URL=http://localhost:8000 \
ANTHROPIC_API_KEY=dummy \
ANTHROPIC_AUTH_TOKEN=dummy \
ANTHROPIC_DEFAULT_OPUS_MODEL=gemma4-31b \
ANTHROPIC_DEFAULT_SONNET_MODEL=gemma4-31b \
ANTHROPIC_DEFAULT_HAIKU_MODEL=gemma4-31b \
claude --model opus "$@"
```

```bash
chmod +x localclaude
./localclaude --plugin-dir .
```

Replace `localhost:8000` with the hostname of your vLLM server if it runs on a different machine.

## Distribution

### Local testing

```bash
claude --plugin-dir ./onc-data-wrangler-plugin
```

### Install from GitHub

```bash
/plugin install owner/repo
```

### Marketplace distribution

To create a discoverable plugin marketplace, add `.claude-plugin/marketplace.json`:

```json
{
  "name": "your-marketplace-name",
  "owner": { "name": "Your Name" },
  "plugins": [
    { "name": "onc-data-wrangler", "source": "./", "description": "Oncology data wrangling plugin" }
  ]
}
```

Users can then discover and install via `/plugin marketplace add owner/repo`.
