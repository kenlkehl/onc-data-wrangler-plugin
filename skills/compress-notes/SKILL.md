---
name: compress-notes
description: Summarize individual oncology clinical documents into concise document-level summaries using local OpenAI-compatible/vLLM, Azure OpenAI, Anthropic, Vertex Claude, Gemini, or Claude Code native mode. Use when the user wants compressed clinical notes or short per-document clinical summaries before extraction, review, or downstream analysis.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write, Agent
model: inherit
effort: high
---

# Compress Notes

You are compressing individual clinical documents into concise oncology-focused summaries. Each input row is one document; do not concatenate notes by patient.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## STEP 0: Configuration

Accept either:
- A project config file path using the same `extraction.llm` and notes column settings as `/onc-data-wrangler:extract-notes`
- Direct arguments: notes file path, output directory, LLM provider, model, and column names

If missing, ask for:
1. Path to notes file (CSV/parquet/TSV with one clinical document per row)
2. Text column name (default: `text`)
3. Patient ID column name (default: `patient_id`; optional but recommended)
4. Date column name (default: `date`; optional)
5. Note type column name (default: `note_type`; optional)
6. Optional document ID column name
7. LLM provider: `openai`, `azure`, `anthropic`, `vertex`, `gemini`, or `claude-code`
8. Output directory

Provider notes match `extract-notes`:
- `openai`: local OpenAI-compatible servers such as vLLM, Ollama, or TGI; ask for `base_url` and model.
- `azure`: Azure OpenAI deployment; use `AZURE_OPENAI_API_KEY` or Azure token flow already supported by the package.
- `anthropic`: direct Claude API; use `ANTHROPIC_API_KEY`.
- `vertex`: Claude through Vertex AI; use application default credentials and project/region.
- `gemini`: Gemini through Vertex AI or AI Studio.
- `claude-code`: Claude Code native summarization with `compression-worker` agents.

---

## STEP 0.5: Inspect the Notes File

Always inspect the notes file before running compression. Verify the column names by name, not position, and confirm that the row count is the number of documents.

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
from pathlib import Path
import pandas as pd

path = Path('NOTES_PATH')
df = pd.read_parquet(path) if path.suffix.lower() == '.parquet' else pd.read_csv(path, low_memory=False)
print('Columns:', df.columns.tolist())
print('Shape:', df.shape)
if 'PATIENT_COL' in df.columns:
    print('Unique patients:', df['PATIENT_COL'].nunique())
if 'TEXT_COL' in df.columns:
    lengths = df['TEXT_COL'].dropna().astype(str).str.len()
    print('Documents with text:', int((lengths > 0).sum()))
    print('Text length summary:')
    print(lengths.describe())
"
```

---

## STEP 1: Determine Compression Mode

Check the LLM provider.

### MODE A: External LLM (`openai`, `azure`, `anthropic`, `vertex`, `gemini`)

Run the Python compressor. With a project config:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -m onc_wrangler.extraction.compressor \
  --config CONFIG_PATH \
  --output-dir OUTPUT_DIR/compressed_notes
```

Direct arguments:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -m onc_wrangler.extraction.compressor \
  --notes-path NOTES_PATH \
  --output-dir OUTPUT_DIR/compressed_notes \
  --provider PROVIDER \
  --model MODEL_NAME \
  --base-url BASE_URL_IF_NEEDED \
  --patient-id-column PATIENT_COL \
  --text-column TEXT_COL \
  --date-column DATE_COL \
  --note-type-column NOTE_TYPE_COL \
  --document-id-column DOCUMENT_ID_COL \
  --max-workers 4
```

Omit optional column flags that do not exist in the notes file. For local vLLM or other OpenAI-compatible servers, use `--provider openai --base-url http://localhost:8000/v1`.

The compressor writes:
- `OUTPUT_DIR/compressed_notes.csv`
- `OUTPUT_DIR/compressed_notes.jsonl`

Output columns include `source_file`, `source_row_index`, `document_id`, `patient_id`, `date`, `note_type`, `text_chars`, `summary`, and `error`.

### MODE B: Claude Code Native (`claude-code`)

Use Claude Code itself to summarize each document. For more than a handful of documents, spawn `compression-worker` agents in batches of 5. Each worker receives:
- One document's metadata and text
- The output JSON path
- The instruction to output one summary paragraph of three sentences or less, or one paragraph per independent primary cancer diagnosis if multiple primaries are documented

After workers finish, combine their JSON outputs into `compressed_notes.csv` and `compressed_notes.jsonl`.

---

## STEP 2: Clinical Compression Rules

Every summary must follow these rules:

- Summarize each clinical document in three sentences or less.
- If multiple independent primary cancers are documented, summarize them independently in one output with one paragraph of three sentences or less per primary cancer diagnosis.
- Capture age, sex, cancer type, histology, disease burden at diagnosis, current disease burden, biomarkers, current or prior treatments, adverse events, comorbidities, performance status, and planned next steps for clinician notes when present.
- If a concept is not mentioned in the note, do not mention it.
- Capture all biomarkers; do not compress multiple biomarker findings into vague statements. Biomarkers are not routine lab values and are not tumor markers such as carcinoembryonic antigen, CA 19-9, CA-125, alpha-fetoprotein, or prostate-specific antigen. Tumor markers belong with current disease burden when clinically relevant.
- Include explicit disease risk scores, such as International Prognostic Index or Follicular Lymphoma International Prognostic Index, as disease burden.
- Spell drug names out in full; expand common oncology shorthand when the expansion is clear.
- Preserve dates for diagnosis, disease burden, treatments, adverse events, comorbidities, performance status, and planned next steps when present.
- Do not invent facts or infer undocumented biomarkers, stages, treatments, adverse events, or plans.

---

## STEP 3: Report Results

Present:
- Number of documents processed
- Number of errors or empty-text rows
- Output file locations
- A short preview of several `document_id`, `patient_id`, `date`, and `summary` rows

Suggested next steps:
- Review summaries for fidelity before using them as a replacement for source notes.
- Use the compressed CSV as the notes input to `/onc-data-wrangler:extract-notes` only when the user explicitly wants extraction over summaries instead of full notes.
