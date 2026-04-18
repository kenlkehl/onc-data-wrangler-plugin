---
name: reproduce-paper
description: Reproduce Published Biomedical Paper Results. End-to-end pipeline that extracts every quantitative result from a published biomedical paper, independently reproduces each result from raw data, and performs discrepancy analysis. Use when the user wants to reproduce or validate published paper results against local datasets.
disable-model-invocation: true
user-invocable: true
allowed-tools: Read, Bash, Edit, Write, Grep, Glob, Agent
model: inherit
effort: max
---

# Reproduce Published Biomedical Paper Results

You are orchestrating an end-to-end pipeline to independently reproduce every quantitative result from a published biomedical paper using local data files. The pipeline has five phases: File Discovery, Question Extraction, Independent Analysis, Discrepancy Analysis, and Summary.

---

## PHASE 0: FILE DISCOVERY AND SETUP

### 0.1 Auto-discover files

Recursively scan the current working directory. Categorize all files into:

**Papers / Publications:**
- PDF files that appear to be research papers or manuscripts
- PDF files that appear to be supplementary materials

**Data Files:**
- CSV, TSV, or TXT files containing tabular data (clinical, genomic, imaging, etc.)
- Note the number of rows and first few column names for each

**Data Dictionaries / Documentation:**
- Excel files (.xlsx) that appear to contain variable definitions or synopses
- PDF files that appear to be data guides, release notes, or curation manuals
- Any README or documentation files

Use these heuristics for auto-discovery:
- Look in `./data_files/`, `./data/`, or the working directory root for tabular data
- Look in `./data_dictionaries/`, `./docs/`, `./documentation/` for dictionaries
- PDFs larger than 5 pages in the root or `./paper/`, `./papers/`, `./manuscript/` are likely the paper
- PDFs named with "supplement" or "supp" are supplementary materials
- Excel files with "dictionary", "synopsis", "codebook", or "data_guide" in the name are data dictionaries

### 0.2 Present findings to the user

Display the discovered files in a structured list, grouped by category. For data files, show row count and a few column names. For PDFs, show page count.

### 0.3 Confirm with the user

Ask the user to confirm or correct:
1. Which PDF is the main paper?
2. Which PDF(s) are supplements?
3. Which PDF(s) are data documentation (not the paper itself)?
4. Which directory contains the data files?
5. Which directory contains data dictionaries?

### 0.4 Execution mode

Ask the user which execution mode to use for per-question analysis (Phases 2 and 3):

- **claude-code** (default): Native Claude Code subagents. No external API key needed. Choose a model:
  - **opus** (default): Most capable, best for complex survival analyses. Higher cost.
  - **sonnet**: Faster and cheaper, suitable for simpler questions.
  - **inherit**: Use the default model specified in the agent definitions.
  - Store this choice -- it will be passed as the `model` parameter when spawning subagents.

- **external**: Use an external LLM via API. The user must provide:
  - **provider**: `openai` (vLLM/OpenAI-compatible), `anthropic`, `vertex`, `azure`, or `gemini`
  - **model**: Model name or deployment name (e.g., `claude-opus-4-6`, `gemma4-31b`)
  - **base_url** (for openai provider): API endpoint URL (e.g., `http://localhost:8000/v1`)
  - **api_key** (optional): API key, or set via environment variable
  - **num_workers** (optional, default 5): Number of parallel workers
  - Store these as `EXECUTION_MODE = "external"` and the LLM configuration values. These will be used to create `LLMConfig` and run the Python pipeline in Phases 2 and 3.

### 0.5 Build data context

Construct a DATA_CONTEXT string that will be provided to every analysis subagent. This string should contain:

```
DATA FILES AVAILABLE:
- [filename]: [row_count] rows, [col_count] columns. Key columns: [first 5-10 column names]
- ... (for each data file)

DATA DICTIONARIES / DOCUMENTATION:
- [filename]: [brief description of what it documents]
- ... (for each documentation file)

NOTES:
- When loading .txt data files, they may be tab-separated with comment lines starting with '#' -- use comment='#' and sep='\t' with pd.read_csv.
```

Also record the absolute paths to:
- `DATA_DIR`: the data files directory
- `DICT_DIR`: the data dictionaries directory
- `PAPER_PDF`: the main paper PDF

These will be included in every subagent spawn prompt.

---

## PHASE 1: QUESTION EXTRACTION (Step A)

### 1.1 Construct the question extraction prompt

Build the prompt below, replacing the four placeholders with actual values from Phase 0:
- `{{PAPER_PDF_PATH}}`: Path to the main paper PDF
- `{{SUPPLEMENT_PDF_PATHS}}`: Paths to supplement PDFs (or "None" if none)
- `{{DATA_DICTIONARY_PATHS}}`: Paths to data dictionary files
- `{{DATA_FILE_LIST}}`: List of available data files with brief descriptions

**Question extraction prompt (fill in placeholders before use):**

> You are a systematic reviewer tasked with extracting every individual quantitative result from a published biomedical paper so that each result can be independently reproduced from raw data.
>
> INPUT FILES:
> - Paper: {{PAPER_PDF_PATH}}
> - Supplements: {{SUPPLEMENT_PDF_PATHS}}
> - Data dictionaries: {{DATA_DICTIONARY_PATHS}}
> - Data files available: {{DATA_FILE_LIST}}
>
> TASK:
> Read the entire paper (main text, tables, figures, and all supplements). Cross-reference with the data dictionary to understand what variables and data structures are available in the underlying dataset. Then generate one analysis question for every individual quantitative result reported in the paper.
>
> QUESTION TYPES TO EXTRACT:
> You must systematically work through the paper and extract questions for ALL of the following:
>
> 1. STUDY DESIGN
>    - Total cohort size and how it was derived
>    - Verification of each inclusion/exclusion criterion (one question per criterion)
>    - Sample sizes at each stage of any flow diagram
>
> 2. DEMOGRAPHICS / BASELINE CHARACTERISTICS
>    - Each ROW of each demographics or baseline characteristics table is a SEPARATE question
>    - If the table has multiple comparison columns (e.g., treatment arms), each CELL is a separate question
>    - Examples: age distribution, sex distribution, race/ethnicity breakdown, disease stage, comorbidities
>
> 3. CLINICAL CHARACTERISTICS
>    - Each row of each clinical characteristics table
>    - Disease subtypes, histology, staging, biomarker status, performance status
>    - Prior treatments, comorbidities
>
> 4. TREATMENT / MEDICATION DATA
>    - Each reported treatment frequency or drug class frequency
>    - Treatment by subgroup if applicable
>    - Lines of therapy distributions
>    - Treatment sequences or combinations
>
> 5. GENOMIC / MOLECULAR DATA
>    - Each reported gene alteration frequency
>    - Each comparison of alteration frequencies between groups
>    - Co-alteration patterns
>    - Mutational signatures, tumor mutational burden, microsatellite instability
>
> 6. SURVIVAL / TIME-TO-EVENT ANALYSES
>    - Each Kaplan-Meier estimate (median survival, 1-year rate, 3-year rate, etc.)
>    - Each hazard ratio from Cox regression
>    - Each survival analysis by subgroup
>    - Both with and without left truncation if reported
>
> 7. STATISTICAL TESTS
>    - Each reported p-value, q-value, odds ratio, hazard ratio, or confidence interval
>    - Each comparison between groups
>    - Each multivariable model result
>
> 8. SUPPLEMENTARY RESULTS
>    - Every quantitative result from supplementary tables and figures
>    - These often contain the most granular data and must not be skipped
>
> QUESTION QUALITY REQUIREMENTS:
>
> Each question MUST be:
>
> 1. SELF-CONTAINED: Answerable from the raw dataset and data dictionary alone, WITHOUT access to the paper. Include all necessary context within the question itself.
>
> 2. SPECIFIC: Define the exact cohort, exact variable, exact method. Never write a vague question.
>
> 3. GRANULAR: One question per individual result. A demographics table with 15 rows should generate at least 15 questions (more if multiple comparison columns).
>
> 4. HINT AT DATA STRUCTURE: Where possible, reference the type of data file likely needed (e.g., "in the patient-level dataset" or "using the treatment/regimen records").
>
> 5. METHODOLOGICALLY COMPLETE: Include the statistical method if the paper specifies one. Include subgroup definitions, inclusion/exclusion criteria, and any special handling (e.g., "using left-truncated Kaplan-Meier analysis with time zero at sequencing date").
>
> EXAMPLES OF GOOD QUESTIONS:
>
> GOOD: "How many patients were in the [STUDY NAME] cohort?"
> Result: "1,846"
>
> GOOD: "What number and proportion of patients in the cohort were female?"
> Result: "1064 (58%)"
>
> GOOD: "What is the median age at diagnosis? Report the median and the full range (minimum-maximum). If a patient had multiple diagnoses with associated genomic sequencing, select the earliest for analysis."
> Result: "65 (18-88)"
>
> GOOD: "What number and proportion of patients had Stage IV disease at diagnosis of the index cancer? If there were multiple qualifying diagnoses, select the earliest."
> Result: "892 (48%)"
>
> GOOD: "How many patients who received a first-line regimen containing either cisplatin or carboplatin without concurrent targeted therapies or investigational agents for the treatment of metastatic disease harbored tumors with KRAS mutations? Define oncogenic alterations as somatic oncogenic and likely oncogenic alterations. Only count sequenced tumor samples obtained before the start of the relevant treatment regimen."
> Result: "127"
>
> GOOD: "What is the median overall survival from diagnosis, using left-truncated Kaplan-Meier analysis with risk set entry at the time of genomic sequencing, among patients with metastatic disease? Report the median and 95% confidence interval."
> Result: "Median 18.2 months (95% CI: 16.4-20.1)"
>
> BAD: "What are the demographics?" (too vague, multiple answers)
> BAD: "Is there a difference?" (unspecified comparison, unspecified variable)
> BAD: "What is the survival?" (which endpoint? which cohort? which method?)
>
> REPORTED RESULT FORMAT:
> For each question, extract the paper's stated answer EXACTLY as reported in the paper.
> - Include units, confidence intervals, and p-values as reported
> - Use the exact numbers from the paper (do not round or recalculate)
> - If a result is reported as "n (%)", include both the count and the percentage
>
> OUTPUT FORMAT:
> Write a Python script using openpyxl to save the results as TWO Excel files:
>
> 1. `questions_with_answers.xlsx` with these columns:
> - analysis_id (integer, sequential starting from 1)
> - category (one of: Study Design, Demographics, Clinical Characteristics, Treatment, Genomic/Molecular, Survival, Statistical Tests, Supplementary)
> - analysis_question (the full self-contained question)
> - reported_analysis_result (the paper's stated answer, exactly as reported)
>
> 2. `questions_only.xlsx` with ONLY these columns:
> - analysis_id
> - category
> - analysis_question
>
> This second file intentionally omits reported_analysis_result. It will be read by
> the orchestrator during Phase 2 to maintain blinding to reported answers.
>
> Also save a companion file paper_context.txt containing a structured summary of the paper's key information:
> - Full citation
> - Study name and design
> - Primary cohort definition and size (N)
> - Key inclusion/exclusion criteria
> - Summary of each major table (table number, title, column headers, and the overall N for that table)
> - Summary of each survival analysis (endpoint, method, key subgroups)
> This file will be used later for discrepancy analysis context.
>
> After writing the files, print a summary:
> - Total number of questions generated
> - Breakdown by category
> - First 5 questions as examples

### 1.2 Spawn question extraction agent

Spawn a `question-extraction-worker` agent using the Agent tool. Pass the constructed prompt as the agent's prompt, including:

- Paper PDF path: `{PAPER_PDF}`
- Supplement PDF paths: list of paths, or "None"
- Data dictionary paths: list of files in `{DICT_DIR}`
- Data file list: brief list from DATA_CONTEXT (filenames and column summaries only)

The agent will read the paper and write three output files:
- `questions_with_answers.xlsx` (columns: analysis_id, category, analysis_question, reported_analysis_result)
- `questions_only.xlsx` (columns: analysis_id, category, analysis_question — NO reported answers)
- `paper_context.txt` (structured summary of the paper for later use in Phase 3)

**IMPORTANT: Do NOT read the paper PDF yourself. Do NOT read `questions_with_answers.xlsx` until Phase 3. You will only read `questions_only.xlsx` (which contains no reported answers) until Phase 3.**

Wait for the agent to complete, then verify that all three output files exist on disk.

### 1.2.1 If the extraction agent fails

If the `question-extraction-worker` fails to produce all three output files:
1. Re-spawn it with the same prompt (up to 2 retries).
2. If it fails 3 times total, inform the user and ask if they want to:
   a. Provide a pre-existing `questions_with_answers.xlsx` manually
   b. Abort the pipeline
3. If the user provides files manually, generate `questions_only.xlsx` from `questions_with_answers.xlsx` by running a Python script that copies only the first 3 columns (analysis_id, category, analysis_question) programmatically, without displaying or printing column 4.

**The orchestrator MUST NEVER read the paper PDF and perform extraction itself. This is a hard constraint for scientific integrity.**

### 1.3 Display summary and get user approval

Read **`questions_only.xlsx`** (NOT `questions_with_answers.xlsx`). Show the user:
- Total number of questions generated
- Breakdown by category
- A sample of 5-10 question TEXTS spanning different categories

**Do NOT display `reported_analysis_result` values.** If the user wants to review the full file including reported answers, direct them to open `questions_with_answers.xlsx` externally (in Excel, LibreOffice, etc.).

Ask the user to confirm the questions look reasonable. They may want to add, remove, or modify questions before proceeding. If the user edits `questions_with_answers.xlsx` externally, regenerate `questions_only.xlsx` by running:

```python
import openpyxl
wb = openpyxl.load_workbook('questions_with_answers.xlsx', read_only=True)
ws = wb.active
wb_out = openpyxl.Workbook()
ws_out = wb_out.active
for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=3, values_only=True):
    ws_out.append(list(row))
wb_out.save('questions_only.xlsx')
wb.close()
wb_out.close()
```

This script copies only the first 3 columns programmatically without displaying column 4. Then re-read `questions_only.xlsx` before continuing.

---

## PHASE 2: INDEPENDENT ANALYSIS (Step B)

**If `EXECUTION_MODE == "external"`, use MODE A below. Otherwise (default), use MODE B.**

### MODE A: External LLM Pipeline

Run the analysis phase using the external LLM agentic pipeline. This uses Python with ThreadPoolExecutor to run workers in parallel, where each worker runs an agentic loop with the external LLM using tool-use (execute_python, read_file, list_files).

Execute this Python script via Bash, filling in the configuration values from Phase 0:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from onc_wrangler.config import LLMConfig
from onc_wrangler.reproduce.pipeline import run_analysis_phase

config = LLMConfig(
    provider="PROVIDER",       # Replace with actual provider
    model="MODEL",             # Replace with actual model
    base_url="BASE_URL",       # Replace with actual base_url (or None)
    # api_key is resolved from environment variables by default
)

# Load questions from the blinded Excel file (no reported answers)
import openpyxl
wb = openpyxl.load_workbook("questions_only.xlsx", read_only=True)
ws = wb.active
headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
q_col = headers.index("analysis_question") + 1
questions = []
for row_idx in range(2, ws.max_row + 1):
    q = ws.cell(row_idx, q_col).value
    if q and str(q).strip():
        questions.append({"question": str(q).strip(), "index": row_idx - 1})
wb.close()

results = run_analysis_phase(
    config=config,
    questions=questions,
    data_context="""DATA_CONTEXT_HERE""",  # Replace with actual DATA_CONTEXT
    data_dir="DATA_DIR_HERE",              # Replace with absolute path
    dict_dir="DICT_DIR_HERE",              # Replace with absolute path
    output_dir="question_results/",
    num_workers=5,                         # Replace with user's choice
)

print(f"Completed: {sum(1 for r in results if r)} / {len(questions)} questions")
PYEOF
```

After the script completes, proceed to **step 2.5** below to collect, validate, and merge results into Excel. Steps 2.5 through 2.7 are shared between MODE A and MODE B.

### MODE B: Claude Code Subagents (default)

This mode uses native Claude Code subagents to analyze each question independently. Each question is handled by an `analysis-worker` agent that reads data files, writes and executes Python code, and produces a structured JSON result.

### 2.1 Read questions

Read **`questions_only.xlsx`** and extract the list of analysis questions. **Do NOT read `questions_with_answers.xlsx` — you must not have access to reported answers during Phase 2.** Use Python via Bash:

```python
import openpyxl, json
wb = openpyxl.load_workbook('questions_only.xlsx', read_only=True)
ws = wb.active
headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
q_col = headers.index('analysis_question') + 1
questions = []
for row in range(2, ws.max_row + 1):
    q = ws.cell(row, q_col).value
    if q and str(q).strip():
        questions.append(str(q).strip())
wb.close()
print(json.dumps(questions))
```

### 2.2 Prepare output directory

Create `question_results/` directory if it doesn't exist.

### 2.3 Check for existing results (resumability)

Check which questions already have result files (`question_results/q001_result.json`, etc.). Report how many are cached vs remaining.

### 2.4 Spawn analysis workers in batches

For each question that needs analysis, spawn an `analysis-worker` agent using the Agent tool. **Spawn agents in batches of 5** with `run_in_background: true`. After each batch completes, report progress before launching the next batch.

The `analysis-worker` is a thin wrapper that delegates to the `onc-data-wrangler:analyze-data` skill in `answer_one` mode. The skill chooses the appropriate backend (Python / R / scanpy) based on what the question requires and what is installed. The wrapper exists to enforce **Phase-2 blinding**: it never reads paper PDFs or `questions_with_answers.xlsx`, so the worker's analysis context contains only the question text and data paths.

The prompt for each agent spawn MUST include:

```
DATA CONTEXT:
{the DATA_CONTEXT string built in Phase 0}

Data files directory: {absolute path to DATA_DIR}
Data dictionaries directory: {absolute path to DICT_DIR}

QUESTION:
{the analysis question text}

OUTPUT:
Write your result as a JSON file to: {absolute path}/question_results/q{NNN}_result.json

The JSON must have these fields:
- analysis_result: your final answer (concise)
- denominator_used: exact N and definition
- assumptions_made: semicolon-separated list
- step_by_step_analysis: your full analysis narrative (sections A through H)
```

If the user chose **sonnet** in Phase 0, pass `model: "sonnet"` to the Agent tool to override the agent's default opus model.

**Do not** pass the paper PDF path, `questions_with_answers.xlsx`, or `paper_context.txt` in this prompt — keeping them out of the worker's context is how Phase-2 blinding is enforced.

### 2.5 Collect, validate, and retry failures

After all agents complete:

1. Read each `question_results/q{NNN}_result.json` file
2. Validate that each file contains valid JSON with the required fields
3. Log any failures (missing files, invalid JSON, or agents that did not produce output). A valid-but-intentional "backend unavailable" result (e.g., `analysis_result` starting with `BACKEND_UNAVAILABLE:` or `DATA_UNAVAILABLE:`) counts as success — do not retry these; they indicate R/scanpy is not installed or the needed data file isn't in `DATA_DIR`.
4. For true failures, **re-spawn a new `analysis-worker` agent** for each failed question (up to 2 retries per question). Use the same prompt template as step 2.4.
5. After retries, if any questions still have no valid result, write a placeholder result:
   ```json
   {
     "analysis_result": "FAILED: Agent could not produce a result after retries",
     "denominator_used": "N/A",
     "assumptions_made": "N/A",
     "step_by_step_analysis": "Agent failed to produce output after maximum retries"
   }
   ```

**CRITICAL: The orchestrator MUST NEVER perform data analysis manually. This is a scientific integrity constraint — the orchestrator has not read the paper's reported answers and must not attempt to reproduce results itself. Always re-spawn a worker agent instead.**

### 2.6 Merge results into Excel

Using Python, merge all results into `agentic_analysis_results.xlsx` with columns:
- `analysis_question`
- `analysis_result`
- `denominator_used`
- `assumptions_made`
- `step_by_step_analysis` (truncate to 32,700 chars per cell -- Excel limit)

### 2.7 Report progress

Report:
- Number of questions successfully answered
- Number of failures
- Location of output file (`agentic_analysis_results.xlsx`)

---

## PHASE 3: DISCREPANCY ANALYSIS (Step C)

**If `EXECUTION_MODE == "external"`, use MODE A below. Otherwise (default), use MODE B.**

### MODE A: External LLM Pipeline

Run the discrepancy phase using the external LLM agentic pipeline. Steps 3.1 and 3.2 are shared (prepare input file and read paper context), then run the Python pipeline instead of spawning subagents.

First complete steps 3.1 and 3.2 below (shared between modes), then execute this Python script via Bash:

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} python3 << 'PYEOF'
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from onc_wrangler.config import LLMConfig
from onc_wrangler.reproduce.pipeline import run_discrepancy_phase

config = LLMConfig(
    provider="PROVIDER",       # Replace with actual provider
    model="MODEL",             # Replace with actual model
    base_url="BASE_URL",       # Replace with actual base_url (or None)
)

# Load rows from discrepancy_analysis_input.xlsx
import openpyxl
wb = openpyxl.load_workbook("discrepancy_analysis_input.xlsx", read_only=True)
ws = wb.active
headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
rows = []
for row_idx in range(2, ws.max_row + 1):
    row = {headers[c]: ws.cell(row_idx, c + 1).value for c in range(len(headers))}
    rows.append({
        "question": str(row.get("analysis_question", "")),
        "reported_result": str(row.get("reported_analysis_result", "")),
        "model_result": str(row.get("analysis_result", "")),
        "denominator": str(row.get("denominator_used", "N/A")),
        "assumptions": str(row.get("assumptions_made", "N/A")),
        "step_by_step": str(row.get("step_by_step_analysis", "N/A")),
        "index": row_idx - 1,
    })
wb.close()

# Read paper context
with open("paper_context.txt") as f:
    paper_context = f.read()

results = run_discrepancy_phase(
    config=config,
    rows=rows,
    data_context="""DATA_CONTEXT_HERE""",   # Replace with actual DATA_CONTEXT
    data_dir="DATA_DIR_HERE",               # Replace with absolute path
    dict_dir="DICT_DIR_HERE",               # Replace with absolute path
    paper_pdf="PAPER_PDF_HERE",             # Replace with absolute path
    paper_context=paper_context,
    output_dir="row_outputs/",
    num_workers=5,                          # Replace with user's choice
)

print(f"Completed: {sum(1 for r in results if r)} / {len(rows)} rows")
PYEOF
```

After the script completes, proceed to **step 3.5** below to collect, validate, and merge results. Steps 3.1-3.2 and 3.5-3.7 are shared between MODE A and MODE B.

### MODE B: Claude Code Subagents (default)

This mode uses native Claude Code subagents to compare published results against the model's reproduced results.

### 3.1 Prepare the input file

**Note: This is the first phase where the orchestrator reads `questions_with_answers.xlsx` and sees `reported_analysis_result` values. This is appropriate because Phase 3's purpose is comparing published vs reproduced results.**

Merge data from the two previous outputs into `discrepancy_analysis_input.xlsx`:
- From `questions_with_answers.xlsx`: `analysis_question`, `reported_analysis_result`
- From `agentic_analysis_results.xlsx`: `analysis_result`, `step_by_step_analysis`, `denominator_used`, `assumptions_made`

Match rows by `analysis_question` text. Write the merged file using openpyxl.

### 3.2 Read paper context

Read `paper_context.txt` (generated in Phase 1). This contains the structured summary of the paper's key tables and cohort definitions. Store as `PAPER_CONTEXT`.

### 3.3 Check for existing results (resumability)

Check which rows already have result files (`row_outputs/row_00.json`, etc.). Create `row_outputs/` directory if it doesn't exist.

### 3.4 Spawn discrepancy workers in batches

For each row that needs analysis, spawn a `discrepancy-worker` agent using the Agent tool. **Spawn agents in batches of 5** with `run_in_background: true`.

Like `analysis-worker`, `discrepancy-worker` is a thin wrapper that delegates to the `onc-data-wrangler:analyze-data` skill — in this phase using `compare` mode. Phase 3's blinding contract is **relaxed** (the worker is allowed to read `paper_pdf`), so the prompt passes the paper PDF path through.

The prompt for each agent spawn MUST include:

```
DATA CONTEXT:
{the DATA_CONTEXT string built in Phase 0}

Data files directory: {absolute path to DATA_DIR}
Data dictionaries directory: {absolute path to DICT_DIR}
Paper PDF: {absolute path to PAPER_PDF}

PAPER CONTEXT:
{contents of paper_context.txt}

QUESTION #{row_index}:
Analysis question: {analysis_question}
Reported (published) result: {reported_analysis_result}
Model's result: {analysis_result}
Model's denominator: {denominator_used}
Model's assumptions: {assumptions_made}
Model's step-by-step: {step_by_step_analysis, truncated to 15000 chars}

OUTPUT:
Write your result as a JSON file to: {absolute path}/row_outputs/row_{NN}.json

The JSON must have these fields:
- concordance_status: CONCORDANT or DISCREPANT
- analysis_result: the reproduced result
- discrepancy_analysis: full A-G analysis text (or brief note if concordant)
- discrepancy_magnitude: MINOR/MAJOR/N/A
- root_cause_classification: from standard list or N/A
- proposed_fix: what change would fix it, or N/A
- confidence: HIGH/MEDIUM/LOW/N/A
```

If the user chose **sonnet** in Phase 0, pass `model: "sonnet"` to the Agent tool.

### 3.5 Collect and validate results

After all agents complete, read each `row_outputs/row_{NN}.json` file. Validate JSON and required fields. Log failures.

### 3.6 Merge results into Excel

Using Python, merge all results into `discrepancy_analysis_results.xlsx` with columns:
- `row_index`
- `analysis_question`
- `reported_result`
- `analysis_result`
- `concordance_status`
- `discrepancy_analysis` (truncate to 32,700 chars)
- `discrepancy_magnitude`
- `root_cause_classification`
- `proposed_fix`
- `confidence`

### 3.7 Report progress

Report:
- Number of rows analyzed
- Concordant vs discrepant counts
- Number of failures
- Location of output file (`discrepancy_analysis_results.xlsx`)

---

## PHASE 4: SUMMARY AND REPORTING

After Phase 3 completes, read `discrepancy_analysis_results.xlsx` and compute:

1. **Overall concordance**: N concordant / N total (%)
2. **Discrepancy magnitude breakdown**:
   - MINOR (10-20%): N
   - MAJOR (>20%): N
3. **Root cause distribution**: Count of each root cause category
4. **Confidence distribution**: Count of HIGH / MEDIUM / LOW
5. **Category-level concordance**: Concordance rate by question category (Demographics, Treatment, Survival, etc.)

Display these results to the user as a formatted summary table.

Highlight any systematic patterns (e.g., "All survival questions are discrepant due to left-truncation differences").

### 4.1 Save the summary to disk

Write the full summary report to `reproduction_summary.md` in the working directory. The file should include:
- Paper citation and date of reproduction
- Overall concordance table
- Discrepancy magnitude breakdown
- Root cause distribution
- Confidence distribution
- Category-level concordance table
- Systematic patterns narrative
- List of all output files produced by the pipeline

This ensures the summary persists beyond the conversation and can be reviewed later.

---

## IMPORTANT NOTES

- **Two execution modes**: Phases 2 and 3 support two modes:
  - **MODE B (default, `claude-code`)**: Uses Claude Code's Agent tool to spawn `analysis-worker` and `discrepancy-worker` subagents. No API key or external Python runner is needed.
  - **MODE A (`external`)**: Uses an external LLM via API with an agentic loop (tool use for code execution). Requires an API key and a model that supports function calling. Supports OpenAI-compatible (vLLM), Anthropic, Azure, Vertex, and Gemini providers.
- **Batch parallelism**: Agents are spawned in batches of 5 with `run_in_background: true`. After each batch completes, the next batch is launched. Adjust batch size down if resource issues occur.
- **Resumability**: Results are saved as per-question/per-row JSON files. If the pipeline is interrupted, re-running will detect and skip completed items.
- **No internet access**: Worker agents have `WebSearch` and `WebFetch` disabled via `disallowedTools`. They can only access local data files.
- **Isolation**: Each worker agent receives ONLY ONE question or row. It has no access to other questions, paper results (in Phase 2), or prior analysis outputs.
- **Data access**: Workers access the project filesystem directly via specified absolute paths. There are no sandbox temp directories.
- **Model override**: The orchestrator can pass `model: "sonnet"` to agent spawns if the user selected Sonnet in Phase 0. Default is Opus.
- **Excel cell limit**: Excel cells have a 32,767 character limit. Truncate step_by_step_analysis and discrepancy_analysis if needed.
- **Structured output**: Results are written as JSON files by the worker agents using the Write tool.
- **Scientific integrity (blinding)**: The orchestrator MUST NOT read the paper PDF or `questions_with_answers.xlsx` until Phase 3. Question extraction is delegated to a `question-extraction-worker` subagent. During Phase 2, the orchestrator reads only `questions_only.xlsx` (no reported answers). When analysis workers fail, the orchestrator re-spawns agents rather than performing analysis manually. This prevents contamination of independent reproduction by knowledge of expected results.
