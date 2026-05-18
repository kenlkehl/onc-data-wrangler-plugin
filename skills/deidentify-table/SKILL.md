---
name: deidentify-table
description: De-identify one structured tabular data file (CSV, TSV, or parquet). Detects likely PHI columns, replaces patient IDs/MRNs/names with stable pseudonyms and realistic fake names, shifts dates per patient, and optionally uses an explicitly approved LLM to rewrite short free-text clinical evidence columns.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write
model: inherit
effort: high
---

# Deidentify Table

You are helping the user de-identify one structured tabular data file. This is a best-effort technical de-identification workflow, not a legal HIPAA determination.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## STEP 0: Inputs and Safety

Accept:
- Input table path: CSV, TSV, or parquet
- Optional output directory or output path
- Optional patient ID, MRN, patient name, date, and free-text column hints
- Optional manifest from a previous `deidentify-table` run
- Optional LLM provider for free-text rewriting

If the user wants cloud/remote LLM rewriting, show a clear warning before enabling it:

> This may send PHI-containing text to the configured model endpoint. Only proceed if the endpoint is institutionally approved for this data, for example through a BAA or local/on-prem deployment.

Do not print raw PHI values into chat. When inspecting data, show column names, row/column counts, data types, and non-sensitive summaries only.

---

## STEP 1: Inspect the Table

Run a non-PHI profile:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 - << 'PYEOF'
from pathlib import Path
import pandas as pd
from onc_wrangler.deidentification.table import DeidentificationConfig, classify_columns, load_table

path = Path("INPUT_PATH")
df = load_table(path)
print(f"Rows: {len(df)}")
print(f"Columns: {len(df.columns)}")
print("Column names:", list(df.columns))
print("Dtypes:")
print(df.dtypes.to_string())
decisions = classify_columns(df, DeidentificationConfig())
print("\nProposed actions:")
for d in decisions:
    print(f"- {d.column}: {d.action} ({d.phi_type or 'non-PHI'}; confidence={d.confidence:.2f}) - {d.reason}")
PYEOF
```

Present the proposed actions to the user without sample values:
- `patient_id`: replace with stable `patient_000001` style pseudonym
- `mrn`: replace with stable `MRN000001` style pseudo-MRN
- `name`: replace with stable realistic fake name for the patient
- `date`: apply stable patient-level date shift
- `birth_date`: drop to avoid exact or bounded age derivation
- `age`: cap exact ages over 89 as `90+`
- `text`: deterministic PHI replacement/redaction, optional LLM pass
- `drop`: remove direct identifier column
- `keep`: retain as-is

Ask for corrections only if the detected actions look ambiguous or the user has not confirmed column roles.

---

## STEP 2: Decide on Free Text

For likely evidence/comment/summary/note columns:

- Always use deterministic redaction first: known patient IDs, MRNs, names, phone numbers, emails, SSNs, addresses, parseable dates, and over-89 ages.
- If the user wants LLM rewriting, require explicit cloud/remote opt-in unless the endpoint is local.
- Prefer local OpenAI-compatible endpoints for PHI unless the user confirms an approved remote/cloud endpoint.

---

## STEP 3: Run De-identification

Run the CLI. Fill in only flags that apply.

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -m onc_wrangler.deidentification.table \
  --input-path INPUT_PATH \
  --output-dir OUTPUT_DIR \
  --patient-id-column PATIENT_ID_COL \
  --mrn-column MRN_COL \
  --name-column NAME_COL \
  --text-column TEXT_COL \
  --manifest-in PREVIOUS_MANIFEST_IF_ANY \
  --date-shift-range-days 180 \
  --yes
```

For LLM rewriting, add:

```bash
  --use-llm \
  --provider PROVIDER \
  --model MODEL \
  --base-url BASE_URL_IF_NEEDED
```

Add `--allow-cloud-llm` only after the explicit warning/confirmation step.

The command writes:
- `<stem>_deidentified.<ext>`: de-identified table
- `<stem>_deidentification_manifest.json`: private sensitive manifest with mappings and exact date shifts
- `<stem>_deidentification_report.json`: non-PHI summary report
- `<stem>_review_queue.csv`: de-identified snippets needing review

---

## STEP 4: Report Results

Report:
- Input and output row/column counts
- Output table path
- Private manifest path, clearly labeled sensitive
- Report and review queue paths
- Dropped columns and any review queue count

Remind the user to keep the private manifest out of shared analysis folders unless re-identification linkage is intended.
