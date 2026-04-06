---
name: generate-synthetic-data
description: Generate synthetic clinical data (patient events, clinical documents, and structured tables) from one or more clinical scenario descriptions. Uses an external LLM for document generation with parallel workers and checkpoint/resume support.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write
model: inherit
effort: max
---

# Generate Synthetic Clinical Data

You are generating synthetic but clinically realistic oncology data. The pipeline produces patient event timelines, detailed clinical documents, and structured tabular data (encounters, labs, hospitalizations, PROs, and any additional table schemas).

The entire pipeline runs in Python with parallel workers — no subagent spawning.

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

### Inference Configuration

Ask if not provided:
1. **LLM provider**: `openai`, `azure`, `anthropic`, or `vertex`. An external LLM is **strongly recommended** for document generation (stages 2+3) — it produces higher-quality, more detailed clinical notes and can run in parallel. If the user does not have access to an external LLM, stages 2+3 can run sequentially using the same provider configured for stage 1, but results will be slower and less detailed.
2. If external provider: model name, base_url (if applicable), and confirm API key is set in environment
3. **Output directory** for results
4. **num_workers** (default: 4): number of parallel threads for stages 2+3. Use 1 for sequential processing.
5. **drug_perturbation_prob** (default: 0.3): probability that each generated clinical note has generic drug names replaced with brand names or common abbreviations (e.g., pembrolizumab → Keytruda/pembro) for increased realism.

---

## STEP 1: Generate Patient Event Lists (Stage 1)

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

## STEP 2: Generate Documents + Structured Data (Stages 2+3)

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

## STEP 3: Assembly

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

## STEP 4: Report Results

Present to the user:
- Number of patients generated (total and per scenario if multi-scenario)
- Average events per patient
- Number of clinical documents generated
- Row counts for each structured table (encounters, labs, hospitalizations, pros, etc.)
- Per-scenario breakdown (if applicable)
- Location of output files:
  - `OUTPUT_DIR/all_documents.json` — all clinical documents
  - `OUTPUT_DIR/tables/encounters.csv` — encounters table (includes `scenario_index`, `scenario_label` columns when multi-scenario)
  - `OUTPUT_DIR/tables/labs.csv` — labs table
  - `OUTPUT_DIR/tables/hospitalizations.csv` — hospitalizations table
  - `OUTPUT_DIR/tables/pros.csv` — patient-reported outcomes table
  - `OUTPUT_DIR/summary.json` — generation summary with per-scenario stats

Suggest next steps:
- Review the generated data for clinical realism
- Add more table schemas to `${CLAUDE_PLUGIN_ROOT}/data/synthetic_schemas/` (e.g., `medications.yaml`, `vitals.yaml`) and re-run to generate additional structured tables
- Use `/onc-data-wrangler:make-database` to build a DuckDB database from the structured tables
- Use `/onc-data-wrangler:extract-notes` to test extraction pipelines against the synthetic documents
