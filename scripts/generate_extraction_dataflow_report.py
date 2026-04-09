#!/usr/bin/env python3
"""Generate a PDF report documenting the extraction data flow.

Uses matplotlib with PdfPages backend -- no additional dependencies needed.

Usage:
    uv run --directory <plugin_root> python scripts/generate_extraction_dataflow_report.py

Output:
    docs/extraction_dataflow_report.pdf
"""

import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PLUGIN_ROOT / "docs"
OUTPUT_PATH = OUTPUT_DIR / "extraction_dataflow_report.pdf"


# ---------------------------------------------------------------------------
# Helper: render a text page
# ---------------------------------------------------------------------------

def _text_page(pdf: PdfPages, title: str, body: str, *, subtitle: str = ""):
    """Add a page with a title and wrapped body text."""
    fig = plt.figure(figsize=(8.5, 11))
    fig.subplots_adjust(left=0.08, right=0.92, top=0.92, bottom=0.06)

    # Title
    fig.text(0.5, 0.95, title, fontsize=16, fontweight="bold",
             ha="center", va="top", family="sans-serif")

    if subtitle:
        fig.text(0.5, 0.92, subtitle, fontsize=10, ha="center",
                 va="top", family="sans-serif", color="#555555")

    # Body -- use a single text block with manual wrapping
    fig.text(0.08, 0.88, body, fontsize=9, va="top", ha="left",
             family="monospace", wrap=True,
             transform=fig.transFigure,
             bbox=dict(boxstyle="square,pad=0.02", facecolor="white",
                       edgecolor="none"))

    pdf.savefig(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 1: Title
# ---------------------------------------------------------------------------

def page_title(pdf: PdfPages):
    fig = plt.figure(figsize=(8.5, 11))
    fig.text(0.5, 0.65, "ONC Data Wrangler Plugin",
             fontsize=24, fontweight="bold", ha="center", va="center",
             family="sans-serif")
    fig.text(0.5, 0.58, "Extraction Data Flow Report",
             fontsize=18, ha="center", va="center",
             family="sans-serif", color="#333333")
    fig.text(0.5, 0.50, "How clinical notes flow through LLM calls\n"
             "for structured data extraction by ontology",
             fontsize=12, ha="center", va="center",
             family="sans-serif", color="#666666")
    fig.text(0.5, 0.38, "Generated from codebase analysis",
             fontsize=10, ha="center", va="center",
             family="sans-serif", color="#999999")
    fig.text(0.5, 0.08,
             "Key source files:\n"
             "  extraction/extractor.py    extraction/domain_groups.py\n"
             "  extraction/chunker.py      extraction/diagnosis_discovery.py\n"
             "  extraction/result.py       extraction/schema_builder.py\n"
             "  ontologies/registry.py     extraction/consolidate.py",
             fontsize=8, ha="center", va="bottom",
             family="monospace", color="#888888")
    pdf.savefig(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 2: Data Loading & Chunking
# ---------------------------------------------------------------------------

PAGE2_BODY = textwrap.dedent("""\
STEP 1: LOAD NOTES
  Source files: CSV or Parquet with columns:
    - patient_id  (configurable, default "record_id")
    - text        (note content)
    - date        (optional, note date)
    - note_type   (optional, e.g. "progress note", "pathology report")

STEP 2: CONCATENATE PER PATIENT  (chunker.py :: concatenate_patient_notes)
  All notes for one patient are sorted chronologically and joined:
    --- progress_note | 2024-01-15 ---
    <note text>

    --- pathology_report | 2024-01-20 ---
    <note text>
  Boundary markers ("--- note_type | date ---") enable smart chunking.

STEP 3: CHUNK  (chunker.py :: chunk_text)

  Token-based (preferred, requires HuggingFace tokenizer):
    Default chunk size: 40,000 tokens
    Default overlap:    200 tokens
    Boundary window:    500 tokens (searches for "\\n--- " markers)

  Character-based (fallback):
    Default chunk size: 160,000 chars  (~40K tokens x 4 chars/token)
    Default overlap:    800 chars
    Boundary window:    2,000 chars

  Boundary-aware splitting:
    When a chunk boundary falls within the boundary window of a
    document separator ("\\n--- "), the split is moved to that
    separator. This prevents notes from being split mid-sentence.

STEP 4: ROUND-BASED PROCESSING  (chunker.py :: ChunkedExtractor)

  Processing is organized into rounds:
    Round 0: Process chunk 0 for ALL patients (up to 8 in parallel)
    Round 1: Process chunk 1 for ALL patients
    ...
    Round N: Process chunk N for patients with N+ chunks

  Each round produces a checkpoint file (round_0000.jsonl) for
  crash-safe resume. Results from round N-1 feed into round N
  as "prior extraction state" for higher-confidence-wins merging.
""")


# ---------------------------------------------------------------------------
# Page 3: Pipeline Flowchart
# ---------------------------------------------------------------------------

def page_flowchart(pdf: PdfPages):
    """Render the end-to-end pipeline flowchart."""
    fig, ax = plt.subplots(figsize=(8.5, 11))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14)
    ax.axis("off")

    fig.text(0.5, 0.96, "End-to-End Extraction Pipeline",
             fontsize=16, fontweight="bold", ha="center", family="sans-serif")

    # Box definitions: (x_center, y_center, width, height, label, color)
    boxes = [
        (5, 13.0, 6, 0.6, "Notes (CSV / Parquet)", "#E3F2FD"),
        (5, 12.0, 6, 0.6, "Concatenate per patient\n(chronological, with boundaries)", "#E8F5E9"),
        (5, 11.0, 6, 0.6, "Chunk text\n(40K tokens, 200 overlap, boundary-aware)", "#E8F5E9"),
        (5, 9.8, 6, 0.7, "DIAGNOSIS DISCOVERY\n1 LLM call: identify all primary cancers", "#FFF3E0"),
        (5, 8.6, 6, 0.7, "PATIENT-LEVEL EXTRACTION\n1 call per patient domain group\n(demographics: sex, race, DOB)", "#FFF3E0"),
        (5, 7.2, 6, 0.9, "PER-DIAGNOSIS EXTRACTION\nFor each diagnosis (0..N-1):\n  demographics → staging → surgery →\n  radiation → systemic → follow-up → narratives", "#FFF3E0"),
        (5, 5.8, 6, 0.7, "MERGE RESULTS\nHigher-confidence-wins across chunks\n(per field_id, per tumor_index)", "#F3E5F5"),
        (5, 4.6, 6, 0.7, "CHECKPOINT\nPer-round JSONL files\n(crash-safe resume)", "#F3E5F5"),
        (5, 3.4, 6, 0.6, "FINAL OUTPUT\nextractions.parquet + per-patient JSON", "#E3F2FD"),
    ]

    for x, y, w, h, label, color in boxes:
        box = FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle="round,pad=0.1",
            facecolor=color, edgecolor="#333333", linewidth=1.2,
        )
        ax.add_patch(box)
        ax.text(x, y, label, ha="center", va="center",
                fontsize=7.5, family="sans-serif", fontweight="normal")

    # Arrows between boxes
    arrow_ys = [
        (12.7, 12.3), (11.7, 11.3), (10.7, 10.15),
        (9.45, 8.95), (8.25, 7.65),
        (6.75, 6.15), (5.45, 4.95), (4.25, 3.7),
    ]
    for y_start, y_end in arrow_ys:
        ax.annotate("", xy=(5, y_end), xytext=(5, y_start),
                     arrowprops=dict(arrowstyle="->", color="#555555", lw=1.5))

    # Side annotations
    ax.text(8.5, 9.8, "System prompt:\nDISCOVERY_SYSTEM_PROMPT\n+ patient text",
            fontsize=6.5, ha="left", va="center", color="#BF360C",
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#FBE9E7",
                      edgecolor="#FFCCBC"))

    ax.text(8.5, 7.2, "Per domain group:\nSystem prompt template\n+ JSON format instructions\n"
            "+ chunk text\n+ tumor_context\n+ prior_state_block",
            fontsize=6.5, ha="left", va="center", color="#1B5E20",
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#E8F5E9",
                      edgecolor="#C8E6C9"))

    # Repeat indicator
    ax.annotate("", xy=(1.5, 11.0), xytext=(1.5, 3.4),
                arrowprops=dict(arrowstyle="->", color="#1565C0", lw=1.0,
                                linestyle="dashed",
                                connectionstyle="arc3,rad=0.3"))
    ax.text(0.5, 7.2, "Repeat\nper\nchunk\n(rounds)",
            fontsize=7, ha="center", va="center", color="#1565C0",
            fontweight="bold", family="sans-serif")

    pdf.savefig(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 4: LLM Call Sequence
# ---------------------------------------------------------------------------

PAGE4_BODY = textwrap.dedent("""\
LLM CALL SEQUENCE PER CHUNK
============================

For each chunk of a patient's notes, the following LLM calls are made
in strict sequence. Results from earlier calls feed into later calls.

 #  CALL                         PROMPT SOURCE                    SCOPE
--- ----------------------------- -------------------------------- -----------
 1  Diagnosis Discovery           DISCOVERY_SYSTEM_PROMPT          Once per
    (identify all primary          + DISCOVERY_USER_TEMPLATE        chunk 0
    cancers)

 2  Patient Demographics          PATIENT_DEMOGRAPHICS_PROMPT      Once
    (sex, race, DOB, etc.)         + CHUNK_USER_TEMPLATE

 --- For EACH diagnosis (tumor_index 0..N-1): ---

 3  Diagnosis Identification      DIAGNOSIS_DEMOGRAPHICS_PROMPT    Per diag
    (primary site, histology,      + CHUNK_USER_TEMPLATE
    date of diagnosis, grade)       + tumor_context

 4  Staging & Prognostic           STAGING_SYSTEM_PROMPT            Per diag
    Factors (TNM, summary           + CHUNK_USER_TEMPLATE           (dynamic
    stage, EOD, biomarkers,         + tumor_context                 field list
    mets at DX)                     + site_context                  from schema
                                                                    registry)

 5  Surgical Treatment             SURGERY_SYSTEM_PROMPT            Per diag
    (procedure, margins, LN         + CHUNK_USER_TEMPLATE
    surgery, dates)                 + tumor_context

 6  Radiation Treatment            RADIATION_SYSTEM_PROMPT          Per diag
    (dose, fractions, phases,       + CHUNK_USER_TEMPLATE
    modality, technique)            + tumor_context

 7  Systemic Therapy               SYSTEMIC_SYSTEM_PROMPT           Per diag
    (chemo, hormone, immuno,        + CHUNK_USER_TEMPLATE
    dates, regimens)                + tumor_context

 8  Follow-up & Outcomes           FOLLOWUP_SYSTEM_PROMPT           Per diag
    (vital status, cancer            + CHUNK_USER_TEMPLATE
    status, date of last             + tumor_context
    contact)

 9  Narrative Summaries            NARRATIVE_SYSTEM_PROMPT          Per diag
    (free-text registry              + NARRATIVE_USER_TEMPLATE
    text fields)

BATCHING: Within each call, items are batched at 50 items per LLM call.
If a domain group has 80 items, it produces 2 sequential LLM calls.

TOTAL CALLS PER CHUNK (single diagnosis, NAACCR):
  1 discovery + 1 patient demographics + 7 diagnosis groups
  = ~9 calls minimum (more with batching)

TOTAL CALLS PER CHUNK (N diagnoses):
  1 discovery + 1 patient demographics + N * 7 diagnosis groups
""")


# ---------------------------------------------------------------------------
# Page 5: Prompt Composition
# ---------------------------------------------------------------------------

PAGE5_BODY = textwrap.dedent("""\
PROMPT COMPOSITION ANATOMY
============================

Each LLM call is composed from multiple parts. Here is the anatomy
of a single extraction call:

FULL PROMPT = system_prompt + "\\n\\n" + user_prompt

SYSTEM PROMPT (built by Extractor._build_system_prompt):
  ┌─────────────────────────────────────────────────────────┐
  │  Domain-specific system prompt template                 │
  │  (e.g. STAGING_SYSTEM_PROMPT from domain_groups.py)     │
  │                                                         │
  │  Template variables substituted:                        │
  │    {json_format_instructions} ← SchemaBuilder output    │
  │    {primary_site}             ← from diagnosis state    │
  │    {histology}                ← from diagnosis state    │
  │    {primary_site_desc}        ← from schema registry    │
  │    {site_context}             ← site-specific guidance  │
  │    {tumor_context}            ← multi-diag identifier   │
  │    {domain_name}              ← for generic ontologies  │
  │    {domain_context}           ← for generic ontologies  │
  └─────────────────────────────────────────────────────────┘

USER PROMPT (CHUNK_USER_TEMPLATE from domain_groups.py):
  ┌─────────────────────────────────────────────────────────┐
  │  Clinical text (dates: ... to ...):                     │
  │  ---                                                    │
  │  {chunk_text}          ← the actual clinical notes      │
  │  ---                                                    │
  │                                                         │
  │  {tumor_context}       ← which diagnosis to extract for │
  │                          (empty for single-diagnosis)    │
  │                                                         │
  │  {prior_state_block}   ← previously extracted values    │
  │                          with confidence scores         │
  │                                                         │
  │  EXTRACTION GUARD RULES                                 │
  │    - Multi-diagnosis isolation                          │
  │    - Staging temporal scope                             │
  │                                                         │
  │  {json_field_descriptions}  ← field names, valid codes, │
  │                               extraction hints          │
  └─────────────────────────────────────────────────────────┘

JSON FORMAT INSTRUCTIONS (SchemaBuilder.build_json_format_instructions):
  For each field in the batch, generates:
    - "fieldName": ItemName (Item 400). Description. Valid codes: ...

  Instructs the LLM to return:
    {"fieldName": {"value": "...", "confidence": 0.95, "evidence": "..."}}

TUMOR CONTEXT (Extractor._build_tumor_context):
  Only generated when patient has multiple diagnoses:
    EXTRACTING FOR DIAGNOSIS 1 OF 2:
    Primary Site: C50.9 (breast)
    Histology: 8500 (infiltrating duct carcinoma)
    Date of Diagnosis: 20190315
    Laterality: left
    Extract ONLY information pertaining to THIS specific cancer.
    Do NOT include data from the patient's other cancer(s).
    For staging fields: use ONLY staging data from initial diagnosis.

PRIOR STATE BLOCK (build_prior_state_block):
  Shows fields already extracted with their confidence:
    PRIOR EXTRACTION STATE (update only with higher-confidence evidence):
    - primarySite: C50.9 (confidence: 0.95)
    - dateOfDiagnosis: 20190315 (confidence: 0.90)
""")


# ---------------------------------------------------------------------------
# Page 6: Ontology Control Flow
# ---------------------------------------------------------------------------

PAGE6_BODY = textwrap.dedent("""\
ONTOLOGY CONTROL FLOW
======================

Ontologies determine WHAT gets extracted. The extraction engine is
ontology-agnostic; all field definitions come from YAML.

ONTOLOGY REGISTRY (ontologies/registry.py):
  - Discovers all data/ontologies/*/ontology.yaml files
  - Each ontology defines: id, name, categories, items, valid_values
  - Available: naaccr, generic_cancer, prissmm, pan_top, clinical_summary,
    omop, msk_chord, matchminer_ai, treatment_response

CATEGORY TYPES:
  per_diagnosis: false  →  Patient-level (extracted once, shared)
    Example: demographics (sex, race, DOB)

  per_diagnosis: true   →  Diagnosis-level (extracted per cancer)
    Example: cancer_diagnosis, staging, treatment

DOMAIN GROUPS (how items are batched for extraction):

  NAACCR (hand-curated, domain_groups.py):
    demographics_patient  → items: 150,160,161,190,220,240,252,254
    demographics_diagnosis→ items: 380,390,400,410,440-450,470-523
    staging               → items: DYNAMIC (from schema registry)
    surgery               → items: 1200-1350,1640,3170-3190
    radiation             → items: 1210,1360-1527,1550,1570,3220
    systemic              → items: 1220-1420,1632-1639,3230-3270
    followup              → items: 1750-1910
    narratives            → items: 2520-2680

  Generic ontologies (auto-generated from DataCategory objects):
    Each DataCategory → one DomainGroup
    System prompt: GENERIC_DOMAIN_SYSTEM_PROMPT
    per_diagnosis flag controls patient vs diagnosis grouping

SCHEMA RESOLUTION (NAACCR only):

  After demographics extraction identifies primary_site + histology:
    SchemaRegistry.get_schema_for_site_histology(site, hist)
      → Returns schema name (e.g., "Breast", "Lung", "Prostate")

    SchemaRegistry.get_all_staging_items(schema)
      → Returns site-specific item numbers for staging group
      → Different sites have different staging fields
         (e.g., Prostate: PSA, Gleason; Breast: ER/PR/HER2)

    SchemaRegistry.get_site_context(schema)
      → Returns site-specific extraction guidance text

CODE RESOLUTION (extraction/code_resolver.py):
  After LLM extraction, each value is resolved against code tables:
    GenericCodeResolver.resolve(field_id, raw_value) → (code, confidence)
    - Exact match: confidence 1.0
    - Fuzzy match: confidence based on similarity
    - No match: (raw_value, 0.0)

  Final confidence = min(llm_confidence, resolution_confidence)
  If no code match: confidence = llm_confidence * 0.5
""")


# ---------------------------------------------------------------------------
# Page 7: Result Merging & Output
# ---------------------------------------------------------------------------

PAGE7_BODY = textwrap.dedent("""\
RESULT MERGING & OUTPUT
========================

EXTRACTION RESULT (extraction/result.py :: ExtractionResult):
  field_id          str      Ontology field identifier
  field_name        str      Human-readable name
  extracted_value   str      Raw LLM output
  resolved_code     str      After code resolution
  confidence        float    0.0 - 1.0
  evidence_text     str      Supporting quote (max 300 chars)
  source_chunk_id   str      Which chunk produced this
  pass_number       int      Chunk index (round number)
  ontology_id       str      Which ontology this belongs to
  tumor_index       int      Which diagnosis (0-based)

MERGING ALGORITHM (extraction/result.py :: merge_results):
  Higher-confidence-wins per field_id:
    for each new result:
      if field_id not in existing:  → add it
      elif new.confidence > existing.confidence:  → replace
      else:  → keep existing

  Multi-diagnosis merging keyed by (tumor_index, field_id):
    Same algorithm but scoped per diagnosis

  This means:
    - First chunk seeds all fields
    - Later chunks can only UPGRADE a field (never downgrade)
    - High-confidence fields (>=0.9) are skipped in later chunks

CHECKPOINT SYSTEM (extraction/chunker.py :: CheckpointManager):
  Per-round JSONL files: round_0000.jsonl, round_0001.jsonl, ...
  Each line: {"patient_id", "round", "extraction", "num_chunks"}

  Resume logic:
    1. Scan existing round files
    2. A round is "complete" if all expected patients have results
    3. Reconstruct running state by replaying completed rounds
    4. Resume from first incomplete round

OUTPUT FORMATS:

  Structured extraction → extractions.parquet
    Columns: patient_id, tumor_index, category, field1, field2, ...
    Multi-diagnosis: separate rows per tumor_index
    Patient-level: tumor_index = -1 (sentinel)

  Clinical summaries → summaries.parquet
    Columns: patient_id, summary

  QA answers → qa_results.parquet
    Columns: patient_id, question, value, confidence, evidence

  Claude Code native mode → per-patient JSON files:
    patient_*.json with {patient_id, ontology, categories, review_items}
    Consolidated via consolidate_extractions() → extractions.parquet

MULTI-DIAGNOSIS OUTPUT FORMAT (internal list[dict]):
  [
    {ontology_id: {patient_field: value, ...}},       ← patient-level
    {"_diagnoses": [                                   ← per-diagnosis
      {"tumor_index": 0, ontology_id: {field: value}},
      {"tumor_index": 1, ontology_id: {field: value}},
    ]},
    {"_extraction_results": {                          ← metadata
      "patient": {field_id: ExtractionResult, ...},
      "diagnosis_0": {field_id: ExtractionResult, ...},
    }},
    {"_discovered_diagnoses": [DiagnosisInfo, ...]},   ← discovery
  ]
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with PdfPages(str(OUTPUT_PATH)) as pdf:
        # Page 1: Title
        page_title(pdf)

        # Page 2: Data Loading & Chunking
        _text_page(pdf, "Data Loading & Chunking", PAGE2_BODY)

        # Page 3: Pipeline Flowchart
        page_flowchart(pdf)

        # Page 4: LLM Call Sequence
        _text_page(pdf, "LLM Call Sequence Per Chunk", PAGE4_BODY)

        # Page 5: Prompt Composition
        _text_page(pdf, "Prompt Composition Anatomy", PAGE5_BODY)

        # Page 6: Ontology Control Flow
        _text_page(pdf, "Ontology Control Flow", PAGE6_BODY)

        # Page 7: Result Merging & Output
        _text_page(pdf, "Result Merging & Output", PAGE7_BODY)

    print(f"Report generated: {OUTPUT_PATH}")
    print(f"  Pages: 7")
    print(f"  Size: {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
