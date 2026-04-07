---
name: generate-synthetic-data
description: Generate synthetic clinical data (patient events, clinical documents, and structured tables) from one or more clinical scenario descriptions. Supports external LLM backends with parallel Python workers, or Claude Code native generation with parallel subagents.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write, Agent
model: inherit
effort: max
---

# Generate Synthetic Clinical Data

You are generating synthetic but clinically realistic oncology data. The pipeline produces patient event timelines, detailed clinical documents, and structured tabular data (encounters, labs, hospitalizations, medications, PROs, and any additional table schemas).

**Supports multiple scenarios**: The user can provide a single blurb or multiple scenario descriptions, each with its own patient count. Patients are tagged with their originating scenario throughout all outputs.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## STEP 0: Configuration

Accept either:
- Direct arguments from the user
- A previously saved config

### Input Specification

Ask the user to specify one or more clinical scenarios (based on a clinical context blurb) for which to generate synthetic data; also specify the option to have Claude create the scenarios itself. Ask how many patients to generate for each scenario. Also inform the user they can refer to a JSON or CSV file with multiple scenarios or provide them as an inline list in the conversation. The JSON file would be in this style:

```json
   [
     {"blurb": "Stage III NSCLC with EGFR L858R mutation", "n_patients": 5, "label": "nsclc_egfr"},
     {"blurb": "Metastatic HER2+ breast cancer", "n_patients": 3, "label": "breast_her2"},
     {"blurb": "Stage IV colorectal cancer with KRAS G12D", "n_patients": 4, "label": "crc_kras"}
   ]
```

A CSV file would have the same columns: `blurb`, `n_patients`, and optionally `label`.


You should then ask the user to specify:
### Inference Configuration

Ask if not provided:
1. **LLM provider**: `openai-compatible`, `azure`, `anthropic`, `vertex`, `gemini`, or `claude-code`.
   - External LLM providers run all generation in Python with parallel threads.
   - `claude-code` uses Claude Code subagents for all generation (no external API needed).
2. If external provider: model name, base_url (if applicable), and confirm API key is set in environment
3. If `gemini`: which model? (gemini-3-flash-preview, gemini-2.5-flash, gemini-2.5-pro, etc.)
   - If using Vertex AI: confirm GCP project ID and region (or that `GOOGLE_VERTEX_PROJECT_ID` env var is set and `gcloud auth application-default login` has been run)
   - If using AI Studio: confirm `GOOGLE_API_KEY` env var is set
4. If `claude-code`:
   - **Event list model** (opus, sonnet, or haiku): which Claude model to use for Stage 1 (patient event list generation)
   - **Document model** (opus, sonnet, or haiku): which Claude model to use for Stages 2+3 (document generation and structured data)
5. **Output directory** for results
6. **num_workers** (default: 4): number of parallel threads for stages 2+3. Only applicable to external LLM providers; ignored for `claude-code`.
7. **drug_perturbation_prob** (default: 0.3): probability that each generated clinical note has generic drug names replaced with brand names or common abbreviations (e.g., pembrolizumab → Keytruda/pembro) for increased realism.

---

## STEP 1: Determine Generation Mode

Check the LLM provider selected in STEP 0:

- **MODE A**: External LLM (`openai-compatible`, `azure`, `anthropic`, `vertex`, `gemini`) → proceed to [MODE A: External LLM Pipeline](#mode-a-external-llm-pipeline)
- **MODE B**: Claude Code Native (`claude-code`) → proceed to [MODE B: Claude Code Native Pipeline](#mode-b-claude-code-native-pipeline)

---

# MODE A: External LLM Pipeline

The entire pipeline runs in Python with parallel workers — no subagent spawning.

## MODE A STEP 1: Generate Patient Event Lists (Stage 1)

For multiple scenarios, loop over each scenario — Stage 1 runs once per scenario.

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

---

## MODE A STEP 2: Generate Documents + Structured Data (Stages 2+3)

This step runs the full document generation and structured data extraction in Python with parallel workers and checkpoint/resume. If a previous run was interrupted, it automatically skips patients whose output files already exist.

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
run_stages_2_and_3(
    client, patients, schema_dir, Path("OUTPUT_DIR"),
    num_workers=NUM_WORKERS,
    drug_perturbation_prob=DRUG_PERTURBATION_PROB,
)
PYEOF
```

Replace `NUM_WORKERS` and `DRUG_PERTURBATION_PROB` with the values from STEP 0.

**Checkpoint/resume**: If the run is interrupted, simply re-run the same command. Patients with existing output files in `OUTPUT_DIR/patients/` are automatically skipped.

---

## MODE A STEP 3: Assembly

Combine per-patient outputs into final files. The assembler automatically includes `scenario_index` and `scenario_label` columns in output CSVs when scenario metadata is present.

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

## MODE A STEP 4: Report Results

Proceed to [Report Results](#report-results).

---

# MODE B: Claude Code Native Pipeline

Claude Code itself generates all data using parallel subagents. No external LLM API is needed. Each stage spawns worker agents that run in the background, batched 5 at a time.

**Important notes for timeout resilience**:
- All agents run with `run_in_background: true`
- Spawn in batches of 5, waiting for each batch to complete before the next
- Each agent has a bounded task (1 patient or 1 document) to avoid timeouts
- If the pipeline is interrupted, check for existing output files and skip completed work (checkpoint/resume)

---

## MODE B STEP 1: Generate Patient Event Lists (Stage 1)

Parallelized across patients — one `event-list-worker` agent per patient.

### 1a. Pre-generate patient IDs

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import uuid, json
from pathlib import Path

# For single scenario:
# scenarios = [{"blurb": "BLURB_TEXT", "n_patients": N, "label": "LABEL"}]

# For multiple scenarios (from file):
# from onc_wrangler.synthetic.pipeline import load_scenarios
# scenarios = load_scenarios("SCENARIOS_FILE_PATH")

# Or inline:
scenarios = SCENARIOS_LIST_HERE

output_dir = Path("OUTPUT_DIR")
events_dir = output_dir / "events"
events_dir.mkdir(parents=True, exist_ok=True)

# Build task list with pre-generated patient IDs
tasks = []
for sc_idx, scenario in enumerate(scenarios):
    blurb = scenario["blurb"]
    n_patients = int(scenario.get("n_patients", 5))
    label = scenario.get("label", "")
    for p_num in range(1, n_patients + 1):
        pid = f"patient_{uuid.uuid4().hex[:12]}"
        # Skip if already generated (checkpoint/resume)
        if (events_dir / f"{pid}.json").exists():
            continue
        tasks.append({
            "patient_id": pid,
            "patient_number": p_num,
            "total_patients": n_patients,
            "scenario_index": sc_idx,
            "scenario_label": label,
            "scenario_blurb": blurb,
            "output_path": str(events_dir / f"{pid}.json"),
        })

print(json.dumps({"total_tasks": len(tasks), "tasks": tasks}, indent=2))
PYEOF
```

### 1b. Spawn event-list-worker agents

For each task from the output above, spawn an `event-list-worker` agent:

- Set `model: "<EVENT_LIST_MODEL>"` (the event list model from STEP 0, e.g., `"opus"`, `"sonnet"`, or `"haiku"`)
- Set `run_in_background: true`
- Spawn in **batches of 5**. Wait for each batch to complete before spawning the next.

Each agent's prompt should include:

```
Generate a synthetic patient event list.

Clinical scenario: <SCENARIO_BLURB>

Patient ID: <PATIENT_ID>
Patient number: <PATIENT_NUMBER> of <TOTAL_PATIENTS> for this scenario

Scenario metadata:
- scenario_index: <SCENARIO_INDEX>
- scenario_label: <SCENARIO_LABEL>
- scenario_blurb: <SCENARIO_BLURB>

Output path: <OUTPUT_PATH>

IMPORTANT: This generation may require significant processing time. Take your time to produce a thorough, clinically realistic event list with 20-30 events. Do not truncate.
```

### 1c. Verify event files

After all agents complete:

```bash
ls OUTPUT_DIR/events/*.json | wc -l
```

Confirm the count matches the expected number of patients.

---

## MODE B STEP 2: Generate Documents (Stage 2)

Parallelized across individual document events — one `document-gen-worker` agent per document.

### 2a. Enumerate document tasks

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from pathlib import Path

events_dir = Path("OUTPUT_DIR") / "events"
docs_dir = Path("OUTPUT_DIR") / "documents"
docs_dir.mkdir(parents=True, exist_ok=True)

doc_types = {"clinical_note", "imaging_report", "pathology_report", "ngs_report"}
tasks = []

for f in sorted(events_dir.glob("*.json")):
    with open(f) as fh:
        patient = json.load(fh)
    pid = patient["patient_id"]
    events = patient["events"]

    for i, event in enumerate(events):
        if event["type"] in doc_types:
            out_path = docs_dir / f"{pid}_evt{i}.json"
            # Skip if already generated (checkpoint/resume)
            if out_path.exists():
                continue
            tasks.append({
                "patient_id": pid,
                "event_index": i,
                "event_type": event["type"],
                "events": events,
                "output_path": str(out_path),
            })

print(json.dumps({"total_documents": len(tasks), "tasks": tasks}, indent=2))
PYEOF
```

### 2b. Spawn document-gen-worker agents

For each task, spawn a `document-gen-worker` agent:

- Set `model: "<DOCUMENT_MODEL>"` (the document model from STEP 0)
- Set `run_in_background: true`
- Spawn in **batches of 5**. Wait for each batch to complete before spawning the next.

Each agent's prompt should include:

```
Generate a synthetic clinical document.

Patient ID: <PATIENT_ID>
Target event index: <EVENT_INDEX>
Event type: <EVENT_TYPE>

Patient events (JSON array):
<EVENTS_JSON>

Output path: <OUTPUT_PATH>

IMPORTANT: This generation may require significant processing time. Take your time to produce a thorough, detailed, realistic clinical document. Clinical notes should be ~2 pages. Reports should be ~1 page. Do not truncate.
```

Pass the full events list as a JSON array in the prompt so the agent has full patient context.

### 2c. Verify document files

After all agents complete:

```bash
ls OUTPUT_DIR/documents/*.json | wc -l
```

Confirm the count matches the expected number of document events.

---

## MODE B STEP 3: Drug Perturbation (Post-Processing)

Apply drug name perturbation to generated documents using the existing Python utility:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
import numpy as np
from pathlib import Path
from onc_wrangler.synthetic.drug_perturbation import (
    DEFAULT_DRUG_MAP, apply_drug_perturbation, compile_replacement_patterns
)

doc_dir = Path("OUTPUT_DIR") / "documents"
patterns = compile_replacement_patterns(DEFAULT_DRUG_MAP)
drug_prob = DRUG_PERTURBATION_PROB
perturbed = 0

for f in sorted(doc_dir.glob("*.json")):
    with open(f) as fh:
        doc = json.load(fh)
    rng = np.random.default_rng(hash(doc["patient_id"] + str(doc["event_index"])) & 0xFFFFFFFF)
    if rng.random() < drug_prob:
        doc["text"] = apply_drug_perturbation(doc["text"], patterns, rng)
        perturbed += 1
        with open(f, "w") as fh:
            json.dump(doc, fh, indent=2)

print(f"Drug perturbation applied to {perturbed} documents")
PYEOF
```

Replace `DRUG_PERTURBATION_PROB` with the value from STEP 0. Skip this step if `drug_perturbation_prob` is 0.

---

## MODE B STEP 4: Generate Structured Data (Stage 3)

Parallelized across patients — one `structured-data-worker` agent per patient.

### 4a. Enumerate structured data tasks

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from pathlib import Path

events_dir = Path("OUTPUT_DIR") / "events"
docs_dir = Path("OUTPUT_DIR") / "documents"
struct_dir = Path("OUTPUT_DIR") / "structured"
struct_dir.mkdir(parents=True, exist_ok=True)

schema_dir = Path("${CLAUDE_PLUGIN_ROOT}") / "data" / "synthetic_schemas"

tasks = []
for f in sorted(events_dir.glob("*.json")):
    with open(f) as fh:
        patient = json.load(fh)
    pid = patient["patient_id"]

    out_path = struct_dir / f"{pid}.json"
    # Skip if already generated (checkpoint/resume)
    if out_path.exists():
        continue

    # Collect document file paths for this patient
    doc_files = sorted(docs_dir.glob(f"{pid}_evt*.json"))

    tasks.append({
        "patient_id": pid,
        "events_path": str(f),
        "document_paths": [str(d) for d in doc_files],
        "schema_dir": str(schema_dir),
        "output_path": str(out_path),
    })

print(json.dumps({"total_tasks": len(tasks), "tasks": tasks}, indent=2))
PYEOF
```

### 4b. Spawn structured-data-worker agents

For each task, spawn a `structured-data-worker` agent:

- Set `model: "<DOCUMENT_MODEL>"` (same model used for document generation)
- Set `run_in_background: true`
- Spawn in **batches of 5**. Wait for each batch to complete before spawning the next.

Each agent's prompt should include:

```
Generate structured tabular data for a patient.

Patient ID: <PATIENT_ID>
Events file: <EVENTS_PATH>
Document files:
<DOCUMENT_PATHS, one per line>

Schema directory: <SCHEMA_DIR>
(Read all .yaml files in this directory for table definitions)

Output path: <OUTPUT_PATH>

IMPORTANT: This generation may require significant processing time. Take your time to produce complete, clinically realistic structured data for all tables. Do not truncate.
```

### 4c. Verify structured data files

After all agents complete:

```bash
ls OUTPUT_DIR/structured/*.json | wc -l
```

---

## MODE B STEP 5: Assemble Per-Patient JSONs

Combine the separate event, document, and structured data files into the per-patient format expected by the assembler:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from pathlib import Path

events_dir = Path("OUTPUT_DIR") / "events"
docs_dir = Path("OUTPUT_DIR") / "documents"
struct_dir = Path("OUTPUT_DIR") / "structured"
patients_dir = Path("OUTPUT_DIR") / "patients"
patients_dir.mkdir(parents=True, exist_ok=True)

assembled = 0
for event_file in sorted(events_dir.glob("*.json")):
    with open(event_file) as f:
        patient = json.load(f)
    pid = patient["patient_id"]

    # Collect documents for this patient (sorted by event index)
    documents = []
    for doc_file in sorted(docs_dir.glob(f"{pid}_evt*.json")):
        with open(doc_file) as f:
            doc = json.load(f)
        documents.append({
            "event_index": doc["event_index"],
            "event_type": doc["event_type"],
            "text": doc["text"],
        })

    # Load structured data
    struct_file = struct_dir / f"{pid}.json"
    tables = {}
    if struct_file.exists():
        with open(struct_file) as f:
            tables = json.load(f)

    # Build combined patient result (matches pipeline.py _process_single_patient format)
    result = {
        "patient_id": pid,
        "events": patient["events"],
        "documents": documents,
        "tables": tables,
    }
    for key in ("scenario_index", "scenario_blurb", "scenario_label"):
        if key in patient:
            result[key] = patient[key]

    out_path = patients_dir / f"{pid}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    assembled += 1

print(f"Assembled {assembled} patient files into {patients_dir}")
PYEOF
```

---

## MODE B STEP 6: Final Assembly

Run the standard assembler to produce combined output files:

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

## MODE B STEP 7: Report Results

Proceed to [Report Results](#report-results).

---

# Report Results

Present to the user:
- Number of patients generated (total and per scenario if multi-scenario)
- Average events per patient
- Number of clinical documents generated
- Row counts for each structured table (encounters, labs, hospitalizations, medications, pros, etc.)
- Per-scenario breakdown (if applicable)
- Location of output files:
  - `OUTPUT_DIR/all_documents.json` — all clinical documents
  - `OUTPUT_DIR/tables/encounters.csv` — encounters table (includes `scenario_index`, `scenario_label` columns when multi-scenario)
  - `OUTPUT_DIR/tables/labs.csv` — labs table
  - `OUTPUT_DIR/tables/hospitalizations.csv` — hospitalizations table
  - `OUTPUT_DIR/tables/medications.csv` — medications table
  - `OUTPUT_DIR/tables/pros.csv` — patient-reported outcomes table
  - `OUTPUT_DIR/summary.json` — generation summary with per-scenario stats

Suggest next steps:
- Review the generated data for clinical realism
- Add more table schemas to `${CLAUDE_PLUGIN_ROOT}/data/synthetic_schemas/` (e.g., `vitals.yaml`, `diagnoses.yaml`) and re-run to generate additional structured tables
- Use `/onc-data-wrangler:make-database` to build a DuckDB database from the structured tables
- Use `/onc-data-wrangler:extract-notes` to test extraction pipelines against the synthetic documents
