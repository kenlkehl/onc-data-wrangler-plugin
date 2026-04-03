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

## Setup

```bash
# Install dependencies
cd /path/to/onc-data-wrangler-plugin
uv sync

# Test with Claude Code
claude --plugin-dir .
```

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

## Reference: Plugin Marketplace / Installation Notes

*Captured from research session (2026-04-02)*

### Does this plugin need a `marketplace.json`?

**No — not for basic installation.** The existing `.claude-plugin/plugin.json` (name, description, version, author) is sufficient for:

- **Local testing**: `claude --plugin-dir ./onc-data-wrangler-plugin`
- **Direct install from GitHub**: `/plugin install` pointing at the repo

### When you DO need `marketplace.json`

You need `.claude-plugin/marketplace.json` to create a **marketplace** — a catalog that lets others discover and install plugins via `/plugin marketplace add`. This is how teams/communities distribute collections of plugins.

#### Directory structure for a marketplace

```
your-repo/
  .claude-plugin/
    plugin.json          # already exists
    marketplace.json     # add this for marketplace distribution
  plugins/
    onc-data-wrangler/
      .claude-plugin/
        plugin.json
      ...
```

#### Minimal `marketplace.json` example

```json
{
  "name": "your-marketplace-name",
  "owner": {
    "name": "Kenneth Kehl"
  },
  "plugins": [
    {
      "name": "onc-data-wrangler",
      "source": "./",
      "description": "Oncology data wrangling plugin"
    }
  ]
}
```

#### Required `marketplace.json` fields

| Field     | Type   | Description                                      |
|-----------|--------|--------------------------------------------------|
| `name`    | string | Marketplace identifier (kebab-case, no spaces)   |
| `owner`   | object | Maintainer info (`name` required, `email` optional) |
| `plugins` | array  | List of plugins, each with `name` and `source`   |

#### Plugin source types in marketplace

- **Relative path**: `"source": "./plugins/my-plugin"` (within same repo)
- **GitHub**: `{"source": "github", "repo": "owner/repo", "ref": "v1.0"}`
- **Git URL**: `{"source": "url", "url": "https://gitlab.com/team/plugin.git"}`
- **Git subdirectory**: `{"source": "git-subdir", "url": "...", "path": "tools/plugin"}`
- **npm**: `{"source": "npm", "package": "@org/plugin", "version": "^2.0"}`

#### User-facing commands

```bash
# Add a marketplace
/plugin marketplace add owner/repo
/plugin marketplace add ./local-path

# Install a plugin from a marketplace
/plugin install plugin-name@marketplace-name

# Validate marketplace structure
claude plugin validate .
```

#### Sources

- [Create and distribute a plugin marketplace - Claude Code Docs](https://code.claude.com/docs/en/plugin-marketplaces)
- [Official Claude Plugins Directory](https://github.com/anthropics/claude-plugins-official)
- [Claude Code Plugin Template](https://github.com/ivan-magda/claude-code-plugin-template)
