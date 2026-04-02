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

## Extraction LLM Backends

The extraction engine supports multiple LLM backends:

- **Local models** (`provider: openai` or `vllm`): vLLM or any OpenAI-compatible server. For PHI data that can't leave the network.
- **Azure OpenAI** (`provider: azure`): Institutional Azure deployments.
- **Claude API** (`provider: anthropic` or `vertex`): Direct Anthropic API or Google Vertex AI.
- **Claude Code** (`provider: claude-code`): Claude Code itself acts as the extractor. Specify which model with `claude_code_model: opus|sonnet|haiku`.

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
      └── query/              - SQL validation & privacy
```
