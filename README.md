# onc-data-wrangler

A Claude Code plugin for oncology data wrangling: extracting structured data from clinical notes, building privacy-preserving DuckDB databases, querying cohorts, and reproducing published paper results.

## Skills

| Skill | Command | Description |
|-------|---------|-------------|
| Setup Project | `/onc-data-wrangler:setup-project` | Interactive wizard to configure a new project |
| Run Pipeline | `/onc-data-wrangler:run-pipeline` | Full pipeline: cohort -> extract -> harmonize -> database -> metadata |
| Extract Notes | `/onc-data-wrangler:extract-notes` | Standalone extraction from clinical notes |
| Query Database | `/onc-data-wrangler:query-database` | Interactive database querying with privacy enforcement |
| Reproduce Paper | `/onc-data-wrangler:reproduce-paper` | Reproduce published paper results from raw data |
| Build Ontology | `/onc-data-wrangler:build-ontology` | Create custom ontology from a data dictionary |
| Red-Team | `/onc-data-wrangler:red-team` | Test agent resistance to prompt injection PHI exfiltration |
| Generate Synthetic Data | `/onc-data-wrangler:generate-synthetic-data` | Generate synthetic clinical data (events, documents, structured tables) from a text description |
| Answer Questions | `/onc-data-wrangler:answer-questions` | Answer clinical questions about patients from their notes with confidence scores |
| Derive Dataset | `/onc-data-wrangler:derive-dataset` | Create a one-row-per-patient analysis dataset with biostatistics guidance and reproducible script |

## Extraction LLM Backends

The extraction engine supports multiple LLM backends:

- **Local models** (`provider: openai` or `vllm`): vLLM or any OpenAI-compatible server. For PHI data that can't leave the network.
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

The `derive-dataset` skill creates a **one-row-per-patient analysis dataset** from a DuckDB database (built by `run-pipeline`) or raw tabular files. It combines interactive column definition with oncology and biostatistics domain expertise.

**Typical workflow:**
```
/onc-data-wrangler:setup-project    # configure project
/onc-data-wrangler:run-pipeline     # build DuckDB
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

## Quick Start

```bash
# 1. Install uv (Python package manager) if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh  # or: pip install uv

# 2. Install dependencies (requires Python 3.13+)
cd /path/to/onc-data-wrangler-plugin
uv sync

# 3. Launch Claude Code with the plugin
claude --plugin-dir .

# 4. Set up a project (interactive wizard)
#    In Claude Code, type: /onc-data-wrangler:setup-project

# 5. Generate synthetic test data
#    /onc-data-wrangler:generate-synthetic-data

# 6. Run the full pipeline
#    /onc-data-wrangler:run-pipeline

# 7. Query your database
#    /onc-data-wrangler:query-database

# 8. Build an analysis dataset
#    /onc-data-wrangler:derive-dataset
```

## Setup

**Requirements:**
- Python 3.13 or higher
- [uv](https://docs.astral.sh/uv/) package manager

```bash
# Install uv if needed
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or: pip install uv

# Install dependencies
cd /path/to/onc-data-wrangler-plugin
uv sync

# Test with Claude Code
claude --plugin-dir .
```

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
    provider: openai   # or vllm
    base_url: "http://localhost:8000/v1"
    model: "your-local-model"
```
This keeps all clinical text on-premises. The `openai` and `vllm` providers work with any OpenAI-compatible API server (vLLM, Ollama, TGI, etc.).

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
Plugin (skills, agents, MCP server)
  |
  ├── Skills orchestrate workflows (setup, pipeline, query, reproduce)
  ├── Agents parallelize work (extraction, analysis, validation)
  ├── MCP Server exposes DuckDB with privacy enforcement
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
