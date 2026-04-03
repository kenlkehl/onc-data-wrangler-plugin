---
name: generate-synthetic-data
description: Generate synthetic clinical data (patient events, clinical documents, and structured tables) from one or more clinical scenario descriptions. Supports external LLMs and Claude Code native generation.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write, Agent
model: inherit
effort: max
---

# Generate Synthetic Clinical Data

You are generating synthetic but clinically realistic oncology data. The pipeline produces patient event timelines, detailed clinical documents, and structured tabular data (encounters, labs, and any additional table schemas).

**Supports multiple scenarios**: The user can provide a single blurb or multiple scenario descriptions, each with its own patient count. Patients are tagged with their originating scenario throughout all outputs.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## STEP 0: Configuration

Accept either:
- Direct arguments from the user
- A previously saved config

### Input Modes

**Single scenario** — user provides one blurb and one patient count:
- Clinical context blurb (e.g., "Stage III NSCLC patients with EGFR L858R mutation")
- Number of patients (default: 5)

**Multiple scenarios** — user provides several clinical contexts, each with its own patient count. Accept as:

1. **Inline list** — user describes scenarios in conversation. Build a scenarios list:
   ```json
   [
     {"blurb": "Stage III NSCLC with EGFR L858R mutation", "n_patients": 5, "label": "nsclc_egfr"},
     {"blurb": "Metastatic HER2+ breast cancer", "n_patients": 3, "label": "breast_her2"},
     {"blurb": "Stage IV colorectal cancer with KRAS G12D", "n_patients": 4, "label": "crc_kras"}
   ]
   ```

2. **JSON file** — path to a `.json` file with the above format.

3. **CSV file** — path to a `.csv` file with columns: `blurb`, `n_patients`, and optionally `label`.

Each scenario's `label` is optional but helpful for identifying scenarios in outputs.

### Additional Configuration

Ask if not provided:
1. **Inference mode**: `claude-code` or an external provider (`openai`, `azure`, `anthropic`, `vertex`)
2. If external provider: model name, base_url (if applicable), and confirm API key is set in environment
3. **Output directory** for results

---

## STEP 1: Generate Patient Event Lists (Stage 1)

Check the inference mode. For multiple scenarios, loop over each scenario — Stage 1 runs once per scenario.

### MODE A: External LLM (openai, azure, anthropic, vertex)

**Single scenario:**
```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from pathlib import Path
from onc_wrangler.config import LLMConfig
from onc_wrangler.llm import create_llm_client
from onc_wrangler.synthetic.pipeline import run_stage1

config = LLMConfig(
    provider="PROVIDER",
    model="MODEL_NAME",
    base_url="BASE_URL_OR_NONE",   # set to None if not needed
    temperature=0.8,
)
client = create_llm_client(config)
patients = run_stage1(client, """BLURB_TEXT""", N_PATIENTS, Path("OUTPUT_DIR"))
print(json.dumps({"n_patients": len(patients), "patient_ids": [p["patient_id"] for p in patients]}))
PYEOF
```

**Multiple scenarios (from file or inline list):**
```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from pathlib import Path
from onc_wrangler.config import LLMConfig
from onc_wrangler.llm import create_llm_client
from onc_wrangler.synthetic.pipeline import run_stage1_multi, load_scenarios

config = LLMConfig(
    provider="PROVIDER",
    model="MODEL_NAME",
    base_url="BASE_URL_OR_NONE",
    temperature=0.8,
)
client = create_llm_client(config)

# Load scenarios from file:
# scenarios = load_scenarios("SCENARIOS_FILE_PATH")

# Or build inline:
scenarios = SCENARIOS_LIST_HERE

patients = run_stage1_multi(client, scenarios, Path("OUTPUT_DIR"))
print(json.dumps({
    "n_patients": len(patients),
    "scenarios": len(scenarios),
    "patients": [{"id": p["patient_id"], "scenario": p.get("scenario_index")} for p in patients]
}, indent=2))
PYEOF
```

### MODE B: Claude Code (claude-code)

You ARE the LLM. For each scenario (or just the single blurb), generate the event lists by following these instructions:

**For each scenario, generate the longitudinal clinical history for {N} patients matching the clinical context:**

{Insert the scenario blurb here}

**Event generation rules:**
- Generate 20-30 events per patient covering the full disease trajectory
- Event types: `<demographics>`, `<diagnosis>`, `<systemic>`, `<surgery>`, `<radiation>`, `<adverse_event>`, `<clinical_note>`, `<imaging_report>`, `<pathology_report>`, `<ngs_report>`
- One event per line, formatted as `<event_type>descriptive sentence`
- Separate patients with `<new_patient>` on its own line
- Vary age, gender, stage, biomarkers, treatments, and disease course across patients
- Diagnosis events: include TNM stage, summary stage, site description/code, histology description/code, site-specific data elements
- Imaging events: specify study type, whether cancer present, response/progression status, metastatic sites
- Clinical note events: indicate cancer present/absent, response/progression status
- NGS events: include diagnosis, specimen site, detailed genomic findings with comutations
- CRITICAL: Genomic findings must respect biological patterns (EGFR mutant lung cancers almost never have KRAS co-mutations)
- CRITICAL: Do NOT mention trial enrollment or screening

**For multiple scenarios**: Generate events for each scenario separately. After generating each scenario's events, parse them immediately so you can tag patients with the correct scenario index. Process scenarios sequentially (one Stage 1 generation per scenario).

After generating the events for a scenario, parse them:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json, sys
from pathlib import Path
from onc_wrangler.synthetic.pipeline import parse_events, write_events

raw_text = """PASTE_THE_GENERATED_EVENT_TEXT_HERE"""

patients = parse_events(
    raw_text,
    scenario_index=SCENARIO_INDEX,        # 0-based index for this scenario
    scenario_blurb="""SCENARIO_BLURB""",  # the blurb text
    scenario_label="SCENARIO_LABEL",      # optional label (or None)
)
output_dir = Path("OUTPUT_DIR")
write_events(patients, output_dir)

print(json.dumps({
    "n_patients": len(patients),
    "scenario_index": SCENARIO_INDEX,
    "patients": [{"id": p["patient_id"], "n_events": len(p["events"])} for p in patients]
}, indent=2))
PYEOF
```

Repeat for each scenario, incrementing SCENARIO_INDEX.

---

## STEP 2: Generate Documents + Structured Data (Stages 2+3)

### MODE A: External LLM

Continue the Python pipeline (works for both single and multi-scenario — patients carry their scenario metadata):

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from pathlib import Path
from onc_wrangler.config import LLMConfig
from onc_wrangler.llm import create_llm_client
from onc_wrangler.synthetic.pipeline import run_stages_2_and_3

config = LLMConfig(
    provider="PROVIDER",
    model="MODEL_NAME",
    base_url="BASE_URL_OR_NONE",
)
client = create_llm_client(config)

# Load patients from Stage 1 (all scenarios combined)
events_dir = Path("OUTPUT_DIR") / "events"
patients = []
for f in sorted(events_dir.glob("*.json")):
    with open(f) as fh:
        patients.append(json.load(fh))

schema_dir = Path("${CLAUDE_PLUGIN_ROOT}") / "data" / "synthetic_schemas"
run_stages_2_and_3(client, patients, schema_dir, Path("OUTPUT_DIR"))
PYEOF
```

### MODE B: Claude Code (claude-code)

Spawn `synthetic-data-worker` agents in parallel, one per patient (across all scenarios).

1. Read the patient event files from `OUTPUT_DIR/events/`:
   ```bash
   uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
   import json
   from pathlib import Path
   events_dir = Path('OUTPUT_DIR') / 'events'
   patients = []
   for f in sorted(events_dir.glob('*.json')):
       with open(f) as fh:
           p = json.load(fh)
           patients.append(p)
           sc = f' [scenario {p[\"scenario_index\"]}]' if 'scenario_index' in p else ''
           print(f'{p[\"patient_id\"]}: {len(p[\"events\"])} events{sc}')
   print(f'Total: {len(patients)} patients')
   "
   ```

2. For each patient, spawn a `synthetic-data-worker` agent:
   - Set `model: "inherit"` on the Agent tool to inherit the parent model
   - Set `run_in_background: true`
   - Spawn in batches of 5 — wait for each batch to complete before starting the next
   - Each worker receives this prompt (include scenario metadata if present):

   ```
   You are generating synthetic clinical data for one patient.

   Patient ID: {patient_id}
   Scenario index: {scenario_index}
   Scenario label: {scenario_label}
   Scenario description: {scenario_blurb}

   Patient event list:
   {events formatted as <event_type>text lines}

   Schema directory: ${CLAUDE_PLUGIN_ROOT}/data/synthetic_schemas

   Output directory: OUTPUT_DIR

   Follow the instructions in your agent definition to generate clinical documents
   and structured tabular data for this patient. Include the scenario metadata
   (scenario_index, scenario_blurb, scenario_label) in your output JSON.
   Write your output JSON to:
   OUTPUT_DIR/patients/{patient_id}.json
   ```

3. After all workers complete, verify outputs:
   ```bash
   ls OUTPUT_DIR/patients/*.json | wc -l
   ```

---

## STEP 3: Assembly

Combine per-patient outputs into final files (both modes). The assembler automatically includes `scenario_index` and `scenario_label` columns in output CSVs when scenario metadata is present.

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from pathlib import Path
from onc_wrangler.synthetic.assembler import assemble_outputs

schema_dir = Path("${CLAUDE_PLUGIN_ROOT}") / "data" / "synthetic_schemas"
summary = assemble_outputs("OUTPUT_DIR", schema_dir)
print(json.dumps(summary, indent=2))
PYEOF
```

---

## STEP 4: Report Results

Present to the user:
- Number of patients generated (total and per scenario if multi-scenario)
- Average events per patient
- Number of clinical documents generated
- Row counts for each structured table (encounters, labs, etc.)
- Per-scenario breakdown (if applicable)
- Location of output files:
  - `OUTPUT_DIR/all_documents.json` — all clinical documents
  - `OUTPUT_DIR/tables/encounters.csv` — encounters table (includes `scenario_index`, `scenario_label` columns when multi-scenario)
  - `OUTPUT_DIR/tables/labs.csv` — labs table
  - `OUTPUT_DIR/summary.json` — generation summary with per-scenario stats

Suggest next steps:
- Review the generated data for clinical realism
- Add more table schemas to `${CLAUDE_PLUGIN_ROOT}/data/synthetic_schemas/` (e.g., `medications.yaml`, `vitals.yaml`) and re-run to generate additional structured tables
- Use `/onc-data-wrangler:run-pipeline` to build a DuckDB database from the structured tables
- Use `/onc-data-wrangler:extract-notes` to test extraction pipelines against the synthetic documents
