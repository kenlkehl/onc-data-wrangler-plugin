---
name: answer-questions
description: Answer clinical questions about patients from their notes using LLM-based extraction. Provide a questions file (one question per line) and a notes file to get per-patient answers with confidence scores and evidence. Use when the user wants to answer specific clinical questions across a patient cohort.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write
model: inherit
effort: high
---

# Answer Questions

You are running clinical question-answering over a cohort of patients. Given a text file of questions and a file of patient notes, you answer each question per patient using an LLM, with confidence scoring and evidence extraction.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## STEP 0: Configuration

Accept:
- **Questions file path** (text file, one question per line; optionally with valid answers in trailing parentheses delimited by semicolons, e.g. `Has the patient had children? (Yes; No; Unknown)`)
- **Notes file path** (CSV or parquet with patient_id, text, and optionally date columns)
- **LLM provider**: openai, azure, anthropic, or vertex

If not provided, ask for each. Also ask for:
- Patient ID column name (default: `patient_id`)
- Text column name (default: `text`)
- Date column name (default: `date`)
- Base URL (if provider is openai, default: `http://localhost:8000/v1`)
- Model name (optional)

---

## STEP 1: Run QA Extraction

Run the Python QA extraction engine:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import pandas as pd
import sys
from pathlib import Path

from onc_wrangler.extraction.qa_extractor import parse_questions, build_qa_output
from onc_wrangler.extraction.extractor import create_extractor
from onc_wrangler.extraction.chunker import ChunkedExtractor, CheckpointManager
from onc_wrangler.llm.vllm_client import VLLMClient  # or appropriate client

# --- Configuration (fill in from user inputs) ---
QUESTIONS_PATH = 'QUESTIONS_FILE'
NOTES_PATH = 'NOTES_FILE'
OUTPUT_PATH = 'OUTPUT_JSONL'
PATIENT_ID_COL = 'patient_id'
TEXT_COL = 'text'
DATE_COL = 'date'
NOTE_TYPE_COL = 'note_type'
VLLM_URL = 'http://localhost:8000/v1'
MODEL = 'default'
CHUNK_TOKENS = 50000
OVERLAP_TOKENS = 500
PATIENT_WORKERS = 8
MAX_TOKENS = 16384

# --- Load questions ---
questions = parse_questions(QUESTIONS_PATH)
print(f"Loaded {len(questions)} questions")

# --- Load notes ---
suffix = Path(NOTES_PATH).suffix.lower()
if suffix == '.parquet':
    raw_df = pd.read_parquet(NOTES_PATH)
else:
    raw_df = pd.read_csv(NOTES_PATH, low_memory=False)

notes_df = raw_df[raw_df[TEXT_COL].notna()].copy()
notes_df[TEXT_COL] = notes_df[TEXT_COL].astype(str)
notes_df = notes_df[notes_df[TEXT_COL].str.strip().str.len() > 10].copy()
notes_df[PATIENT_ID_COL] = notes_df[PATIENT_ID_COL].astype(str)
if DATE_COL in notes_df.columns:
    notes_df = notes_df.sort_values(by=[PATIENT_ID_COL, DATE_COL]).reset_index(drop=True)
n_patients = notes_df[PATIENT_ID_COL].nunique()
print(f"Loaded {len(notes_df)} notes, {n_patients} patients")

# --- Create LLM client ---
# Replace with appropriate client for your provider:
client = VLLMClient(base_url=VLLM_URL, api_key='none', model=MODEL)
# For Anthropic: from onc_wrangler.llm.claude_client import ClaudeClient
# For Azure: from onc_wrangler.llm.azure_client import AzureClient

# --- Create QA extractor ---
extractor = create_extractor(llm_client=client, ontology_ids=[], questions=questions)

# --- Run extraction ---
output_path = Path(OUTPUT_PATH)
work_dir = output_path.parent / f"{output_path.stem}_work"
work_dir.mkdir(parents=True, exist_ok=True)

chunked = ChunkedExtractor(
    extractor=extractor,
    chunk_size=CHUNK_TOKENS,
    overlap=OVERLAP_TOKENS,
    max_retries=3,
    patient_workers=PATIENT_WORKERS,
    max_tokens=MAX_TOKENS,
)
chunked.extract_cohort(
    notes_df=notes_df,
    output_dir=work_dir,
    patient_id_column=PATIENT_ID_COL,
    text_column=TEXT_COL,
    date_column=DATE_COL,
    type_column=NOTE_TYPE_COL,
)

# --- Write JSONL + CSV ---
final = CheckpointManager(work_dir).load_final_extractions()
build_qa_output(final, output_path)
print(f"JSONL: {output_path}")
print(f"CSV:   {output_path.with_suffix('.csv')}")
print(f"Done: {len(final)} patients, {len(questions)} questions")
PYEOF
```

Substitute the placeholder values (QUESTIONS_FILE, NOTES_FILE, OUTPUT_JSONL, column names, LLM URL/model) with the user's actual inputs before running.

For different LLM providers, replace the client creation:
- **openai**: `VLLMClient(base_url=url, api_key=key, model=model)`
- **anthropic**: `ClaudeClient(provider='anthropic', model=model, api_key=key)`
- **vertex**: `ClaudeClient(provider='vertex', model=model)`
- **azure**: `AzureClient(azure_endpoint=url, api_key=key, model=model)`

---

## STEP 2: Report Results

After extraction completes, present to the user:
- Number of patients processed
- Number of questions answered
- Output file locations (JSONL and CSV)
- Preview the first few rows of the CSV output

Suggest next steps:
- Review the JSONL for per-patient confidence scores and evidence
- Use the CSV for downstream analysis or import into a spreadsheet
