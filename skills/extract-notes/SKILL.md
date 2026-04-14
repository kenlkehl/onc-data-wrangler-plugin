---
name: extract-notes
description: Extract structured data from unstructured clinical notes using dictionary-driven LLM extraction. Supports local models, Azure, Claude API, Google Gemini, or Claude Code native extraction. Use when the user wants to extract data from clinical text.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Write, Agent
model: inherit
effort: max
---

# Extract Notes

You are performing dictionary-driven extraction of structured data from unstructured clinical notes. The extraction uses domain groups (sequential groups of related fields) with per-field confidence scoring and code resolution.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`

---

## STEP 0: Configuration

Accept either:
- A config file path (loads full project config)
- Direct arguments: notes file path, ontology ID, LLM provider

If no config provided, ask:
1. Path to notes file (CSV/parquet with patient_id, text columns)
2. Ontology to use (list from `${CLAUDE_PLUGIN_ROOT}/data/ontologies/`)
3. LLM provider: openai, azure, anthropic, vertex, gemini, or claude-code
4. If gemini: which model? (gemini-3-flash-preview, gemini-2.5-flash, gemini-2.5-pro, etc.)
5. If claude-code: which model? (opus, sonnet, haiku)

---

## STEP 0.5: Inspect the Notes File

Before proceeding, **always inspect the notes file** to identify the correct columns and understand the data shape. Never assume column positions — always use column names.

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
import pandas as pd
df = pd.read_csv('NOTES_PATH')  # or pd.read_parquet() for .parquet
print('Columns:', df.columns.tolist())
print('Shape:', df.shape)
# Identify the patient ID column by NAME, not by position
patient_col = 'patient_id'  # or whatever the actual column name is
print(f'Unique patients ({patient_col}):', df[patient_col].nunique())
print(f'Notes per patient:')
print(df.groupby(patient_col).size().describe())
print(f'Avg text length:', df['text'].dropna().str.len().mean())
"
```

**Important**: The total row count is the number of *notes*, NOT the number of patients. A cohort may have many notes per patient. Always use `df[patient_col].nunique()` (referencing the column by name) to get the true patient count — never use `df.iloc[:,0].nunique()` or assume the first column is the patient ID.

---

## STEP 1: Determine Extraction Mode

Check the LLM provider:

### MODE A: External LLM (openai, azure, anthropic, vertex, gemini)

Run the Python extraction engine which handles the full domain-group loop:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import pandas as pd, json, sys
from pathlib import Path
from onc_wrangler.config import load_config, LLMConfig, ExtractionConfig
from onc_wrangler.llm import create_llm_client
from onc_wrangler.extraction.extractor import create_extractor
from onc_wrangler.extraction.chunker import chunk_text_by_chars
from onc_wrangler.extraction.result import ExtractionResult

# Load config or build from arguments
config = load_config('CONFIG_PATH')
client = create_llm_client(config.extraction.llm)
extractor = create_extractor(
    client,
    config.extraction.ontology_ids,
    config.extraction.cancer_type,
    config.extraction.items_per_call,
)

# Load notes
notes_df = pd.read_csv('NOTES_PATH')
patient_col = config.extraction.patient_id_column
text_col = config.extraction.notes_text_column

results = {}
for pid, group in notes_df.groupby(patient_col):
    # Concatenate all notes for this patient
    all_text = "\n\n---\n\n".join(group[text_col].dropna().tolist())

    # Chunk if needed
    chunks = chunk_text_by_chars(all_text, chunk_size_chars=config.extraction.chunk_tokens * 4)

    # Extract iteratively across chunks
    patient_results = extractor.extract_iterative(chunks, config.extraction.cancer_type)
    results[str(pid)] = patient_results
    print(f"Patient {pid}: extracted {len(patient_results)} result groups")

# Save results
out_dir = Path(config.output_dir) / "extractions"
out_dir.mkdir(parents=True, exist_ok=True)
with open(out_dir / "extraction_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print(f"Extraction complete: {len(results)} patients processed")
PYEOF
```

### MODE B: Claude Code Native (claude-code)

Claude Code itself acts as the extractor. Spawn `extraction-worker` agents in parallel.

1. Read the ontology definitions:
   ```
   Read ${CLAUDE_PLUGIN_ROOT}/data/ontologies/<ontology_id>/ontology.yaml
   ```

2. Read the domain group definitions (if NAACCR):
   ```
   Read ${CLAUDE_PLUGIN_ROOT}/data/ontologies/naaccr/domain_groups.yaml
   ```

3. Load the notes file and get patient list:
   ```bash
   uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 -c "
   import pandas as pd, json
   df = pd.read_csv('NOTES_PATH')
   patients = df['PATIENT_COL'].unique().tolist()
   print(json.dumps(patients[:5]))  # first 5 for preview
   print(f'Total patients: {len(patients)}')
   "
   ```

4. For each patient (or batch), spawn an `extraction-worker` agent:
   - Pass `model: "<claude_code_model>"` to the Agent tool (e.g., `model: "sonnet"`)
   - Set `run_in_background: true`
   - Spawn in batches of 5, wait for each batch to complete before the next
   - Each worker receives:
     - Patient's notes text (or file path + patient ID)
     - Ontology YAML path
     - Domain group definitions
     - Output path for results JSON

5. Collect results from all workers after completion.

---

## STEP 2: Consolidate Extractions to Parquet (Both Modes)

After extraction completes, consolidate per-patient results into `extractions.parquet` so that `/onc-data-wrangler:make-database` can load them directly.

The script handles both output formats:
- **Mode B** (claude-code native): individual `patient_*.json` files with `{patient_id, ontology, categories}` structure
- **Mode A** (external LLM): single `extraction_results.json` with `{patient_id: extraction_list}` structure

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import logging
from pathlib import Path
from onc_wrangler.extraction.consolidate import consolidate_extractions

logging.basicConfig(level=logging.INFO)

output_dir = Path('OUTPUT_DIR')
extractions_dir = output_dir / "extractions"
ontologies_dir = Path('${CLAUDE_PLUGIN_ROOT}') / "data" / "ontologies"

df = consolidate_extractions(extractions_dir, ontologies_dir=ontologies_dir)
if not df.empty:
    print(f"Consolidated: {len(df)} rows, {df['patient_id'].nunique()} patients")
    print(f"Categories: {sorted(df['category'].unique().tolist())}")
    print(f"Rows per category:")
    for cat, count in df['category'].value_counts().items():
        print(f"  {cat}: {count}")
else:
    print("WARNING: No extraction data to consolidate")
PYEOF
```

---

## STEP 3: Post-Processing (Both Modes)

After consolidation, run validation and generate audit trail:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
from pathlib import Path
from onc_wrangler.extraction.validator import EnhancedValidator
from onc_wrangler.extraction.audit import generate_audit_trail, generate_review_queue

# Load results
results_path = Path('OUTPUT_DIR') / "extractions" / "extraction_results.json"
with open(results_path) as f:
    results = json.load(f)

# Validate
validator = EnhancedValidator()
# ... run validation on results

# Generate audit trail
# generate_audit_trail(results, Path('OUTPUT_DIR') / "audit_trail.csv")
# generate_review_queue(results, Path('OUTPUT_DIR') / "review_queue.csv")

print("Post-processing complete")
PYEOF
```

---

## STEP 4: Report Results

Present to the user:
- Number of patients processed
- Number of fields extracted per patient (average)
- Average confidence score
- Number of items flagged for human review (by priority: CRITICAL, HIGH, MEDIUM, LOW)
- Location of output files (extraction results, audit trail, review queue)

Suggest next steps:
- `/onc-data-wrangler:make-database` to build a database from tabular data
- Review the `review_queue.csv` for items needing human attention
