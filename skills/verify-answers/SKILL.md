---
name: verify-answers
description: Agentic verification pass over answer-questions output. For each patient, a frontier-LLM subagent (1) checks every answer against its cited evidence, (2) checks the full answer dict for cross-question contradictions, and (3) for flagged cells does targeted note retrieval (no full re-read) to confirm or correct the value. Produces a verified JSONL/CSV and a per-cell audit trail. Use when you want a second-opinion quality pass on extraction output without rerunning the LLM over all notes.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write, Agent
model: inherit
effort: high
---

# Verify Answers

You orchestrate a per-patient verification pass over the output of the `answer-questions` skill, using subagent verifiers that catch evidence/value mismatches, cross-question contradictions, and hallucinated values — without re-reading the full note corpus.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## How it works

The first-pass extractor (`answer-questions`) records `(value, confidence, evidence)` for each (patient, question) cell, where `evidence` is a short quote from the notes. That gives this verifier two cheap signals that don't require re-reading any notes:

1. **Evidence-consistency check** — does the cited evidence actually support the value? (Catches PD-L1=100 with evidence saying "90%", value="IV" cited as an NTRK answer, etc.)
2. **Cross-answer consistency check** — within one patient's 70-answer dict, are there internal contradictions? (LMD date=N/A but method=MRI; PD-L1 ≥50%=Yes but %=20; first-line=osimertinib but EGFR classical=No; line-of-therapy counts disagree with drug-by-drug listings; age ordering broken; etc.)

Only when the cheap signals flag a cell does the verifier earn the right to **targeted retrieval**: grep that patient's notes parquet for keywords drawn from the question + suspicious evidence, read just the matching snippets, and re-answer that single question. Full-notes context is paid only on disputed cells — not 70× per patient.

What this **cannot** catch: cases where the first-pass extractor cited a plausible-but-wrong note as evidence (e.g. cited an early negative MRI when a later positive one exists). The cross-answer pass surfaces some of these as contradictions; targeted retrieval can fix more; some will pass through unflagged. The verifier is a quality-improvement pass, not a replacement for human review on critical cells.

---

## STEP 0: Configuration

Accept (or ask for):
- **`qa_jsonl`**: path to `qa_results.jsonl` produced by `answer-questions`
- **`notes`**: path to the notes file (parquet or CSV) — same one used in extraction
- **`patient_id_col`**: notes column with patient IDs (default `patient_id`)
- **`text_col`**: notes text column (default `text`)
- **`date_col`**: notes date column (default `date`, may be absent)
- **`output_dir`**: where to write verified outputs and audit (default = sibling of `qa_jsonl`)
- **`max_parallel`**: how many verifier subagents to run concurrently (default `8`)
- **`flag_only`** (optional bool, default `false`): if true, the verifier never overwrites a value — it only flags suspicious cells in the audit log and leaves the original value intact. Useful when you want human review of any change.

If the qa_jsonl was produced by a small/local model and contains a lot of low-confidence cells, recommend `max_parallel` ≤ 4 and `flag_only=false`. If it was produced by a frontier model, recommend `flag_only=true` (verifier should mostly confirm; only flag the rare disagreements).

---

## STEP 1: Prepare per-patient input files

Read `qa_jsonl`, and for each patient write a small input JSON to `${output_dir}/work/verify_input_<patient_id>.json` containing:

```json
{
  "patient_id": "...",
  "answers": { "<question text>": {"value": ..., "confidence": ..., "evidence": ...}, ... },
  "notes_path": "/absolute/path/to/notes.parquet",
  "patient_id_col": "dfci_mrn",
  "text_col": "text",
  "date_col": "date",
  "output_path": "${output_dir}/work/verify_output_<patient_id>.json",
  "flag_only": false
}
```

These files keep each worker's context tightly scoped — the worker reads its one input file and writes its one output file.

---

## STEP 2: Spawn verifier subagents

Dispatch `verify-worker` subagents in parallel batches of `max_parallel`. Each Agent call passes the absolute path of the patient's input JSON in the prompt. Example dispatch:

```
Agent(
  subagent_type="onc-data-wrangler:verify-worker",
  description="verify patient <pid>",
  prompt="Verify the QA-extraction output for one patient. Input JSON: /abs/path/verify_input_<pid>.json. Read it; perform the three-tier verification described in your skill; write verified output to the `output_path` specified in the input JSON. Do not read any file outside the input JSON, the notes file it references, or your output path."
)
```

Use `run_in_background=true` when you have a large batch and want concurrent dispatch. The orchestrator should wait for the batch to complete before moving on, but does not need to read each subagent's transcript — the verified output file is the source of truth.

---

## STEP 3: Aggregate

After all workers complete, read every `verify_output_<patient_id>.json` and build:

- **`${output_dir}/qa_results_verified.jsonl`**: one JSON object per patient with the final verified answer dict (same shape as the input `qa_results.jsonl`).
- **`${output_dir}/qa_results_verified.csv`**: wide table, one row per patient, with `<question>` and `<question> [evidence]` columns paired (same convention as `build_qa_output`). Add a third paired column `<question> [verification_status]` valued one of `confirmed` / `corrected` / `flagged_unresolved` / `not_checked`.
- **`${output_dir}/verification_audit.csv`**: long table, one row per cell that was changed or flagged. Columns: `patient_id, question, original_value, verified_value, status, reason, retrieval_query, retrieval_snippet_first_100_chars`.
- **`${output_dir}/verification_summary.json`**: counts of cells confirmed / corrected / flagged_unresolved, broken down by question. Use this to spot questions with systematic problems (e.g. a 30% correction rate on `PD-L1 (%)` would suggest the first-pass prompt for that question needs work).

The helper for assembly:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 - << 'PYEOF'
import json, csv
from pathlib import Path
from collections import Counter

WORK_DIR = Path('${output_dir}/work')
OUT_JSONL = Path('${output_dir}/qa_results_verified.jsonl')
OUT_CSV = Path('${output_dir}/qa_results_verified.csv')
AUDIT = Path('${output_dir}/verification_audit.csv')
SUMMARY = Path('${output_dir}/verification_summary.json')

patient_outputs = []
for f in sorted(WORK_DIR.glob('verify_output_*.json')):
    patient_outputs.append(json.loads(f.read_text()))

# JSONL
with open(OUT_JSONL, 'w') as fh:
    for p in patient_outputs:
        fh.write(json.dumps({'patient_id': p['patient_id'], 'answers': p['verified_answers']}) + '\n')

# CSV with verification_status columns
all_q = []
seen = set()
for p in patient_outputs:
    for q in p['verified_answers']:
        if q not in seen:
            all_q.append(q); seen.add(q)
with open(OUT_CSV, 'w', newline='') as fh:
    w = csv.writer(fh)
    header = ['patient_id']
    for q in all_q:
        header.extend([q, f'{q} [evidence]', f'{q} [verification_status]'])
    w.writerow(header)
    for p in patient_outputs:
        row = [p['patient_id']]
        for q in all_q:
            ans = p['verified_answers'].get(q, {})
            row.append(ans.get('value', ''))
            row.append(ans.get('evidence', ''))
            row.append(ans.get('verification_status', 'not_checked'))
        w.writerow(row)

# Audit log
with open(AUDIT, 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['patient_id','question','original_value','verified_value','status','reason','retrieval_query','retrieval_snippet'])
    for p in patient_outputs:
        for entry in p.get('audit', []):
            w.writerow([
                p['patient_id'], entry['question'], entry.get('original_value',''),
                entry.get('verified_value',''), entry.get('status',''), entry.get('reason',''),
                entry.get('retrieval_query',''), (entry.get('retrieval_snippet','') or '')[:100],
            ])

# Summary
counts = Counter()
per_q = {}
for p in patient_outputs:
    for q, ans in p['verified_answers'].items():
        s = ans.get('verification_status', 'not_checked')
        counts[s] += 1
        per_q.setdefault(q, Counter())[s] += 1
SUMMARY.write_text(json.dumps({
    'total_cells': sum(counts.values()),
    'overall': dict(counts),
    'per_question': {q: dict(c) for q, c in per_q.items()},
}, indent=2))

print(f'Wrote {OUT_JSONL}, {OUT_CSV}, {AUDIT}, {SUMMARY}')
print(f'Cells: {dict(counts)}')
PYEOF
```

---

## STEP 4: Report to the user

Present:
- Total patients verified, total cells reviewed
- Overall counts: `confirmed` / `corrected` / `flagged_unresolved`
- The top-5 questions by `corrected` rate (where the first-pass extractor most needed correction — useful signal about which questions to refine in future runs)
- The top-5 questions by `flagged_unresolved` rate (where even the verifier couldn't decide — these are candidates for human review)
- Paths to `qa_results_verified.csv` (the new analytic table), `verification_audit.csv` (per-cell change log), and `verification_summary.json`

Suggest next steps: open the audit log to inspect specific changes, or re-run the first-pass `answer-questions` with refined wording on the questions that had high correction rates.
