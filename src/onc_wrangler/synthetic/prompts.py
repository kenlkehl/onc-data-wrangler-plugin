"""Prompt templates for synthetic clinical data generation.

Stage 1: Generate patient event lists from a clinical context blurb.
Stage 2: Generate clinical documents per event (masked-text approach).
Stage 3: Generate structured tabular data per patient.
"""

from __future__ import annotations

from .schemas import TableSchema, schema_to_prompt_text


# ---------------------------------------------------------------------------
# Stage 1: Event list generation
# ---------------------------------------------------------------------------

STAGE1_SYSTEM = (
    "I'm a medical oncologist and data scientist. Your job is to help me create "
    "synthetic clinical data for cancer research."
)

STAGE1_SUFFIX = (
    " For each patient, generate a list of events that might have occurred along "
    "the disease trajectory.\n"
    "Use everything you know about cancer and clinical oncology.\n"
    "Types of events might include a diagnosis as recorded in a cancer registry; "
    "initiation of a systemic therapy; a surgery; a radiation treatment; an adverse "
    "event; a clinical progress note; an imaging report; a pathology report; and a "
    "next-generation sequencing (NGS) report. For progress notes, imaging reports, "
    "pathology reports, and NGS reports, include findings documented in the report "
    "in the description of the event.\n"
    "NGS reports should be very detailed; they should include both any key actionable "
    "alterations if present, and comutations/fusions/copy number alterations; most "
    "reports should describe alterations in many genes, even though only some of "
    "those will be clinically relevant.\n"
    "CRITICAL: Genomic findings should make sense based on known mutation and "
    "comutation patterns. For example, remember that EGFR mutant lung cancers "
    "almost never have KRAS co-mutations.\n"
    "There should be one event per line of text in your output, and each event "
    "should be formatted as a sentence.\n"
    "Most patients will have many events along their disease trajectories (20-30).\n"
    "To ensure diversity in the generated data, vary patient age, gender, name, "
    "stage at diagnosis, biomarkers, treatment approaches, and disease course "
    "(e.g., stable disease, progression, remission, recurrence).\n"
    "Tag each event with an event type at the beginning of the line. Acceptable "
    "event types include <demographics>, <diagnosis>, <systemic>, <surgery>, "
    "<radiation>, <adverse_event>, <clinical_note>, <imaging_report>, "
    "<pathology_report>, and <ngs_report>.\n"
    "Each event should correspond only to one point in time, and each report "
    "should correspond only to one report that could have been written at that time.\n"
    "Diagnosis events should include TNM stage, summary stage, site description "
    "and code, histology description and code, and all relevant site-specific data "
    "elements that a cancer registrar would annotate.\n"
    "Imaging report events must describe only one radiographic study and should "
    "specify the type of study. Imaging report events must also indicate whether "
    "cancer was present on the scan; if so, whether it was responding, progressing, "
    "or neither; and what metastatic sites were involved.\n"
    "Oncologist note events must indicate whether cancer was present at the time; "
    "and if so, whether it was responding, progressing, or neither.\n"
    "NGS report events should indicate the diagnosis, specimen site, and genomic "
    "findings.\n"
    "Here is an example of what your output should look like. This is hypothetical, "
    "just to illustrate the formatting. Don't use this text in your output.\n"
    "Do adhere closely to the formatting.\n"
    "(Beginning of example)\n"
    "<demographics> The patient is a male named John Smith.\n"
    "<diagnosis>At age 70 years, the patient had a diagnosis of stage 1E (Best AJCC) "
    "LYMPHOMA, MALIG, DIFFUSE, NOS, (MALIGNANT, PRIMARY) of the BASAL GANGLIA. "
    "Relevant biomarkers included B Symptoms: 0: No B symptoms (asymptomatic) ; "
    "Classified as A by physician when asymptomatic. Other relevant diagnostic "
    "information included Confirmation: POSITIVE HISTOLOGY; Tumor Size: 15 mm.\n"
    "<pathology_report>At age 70, the patient had a pathology result of type "
    "ANATOMIC PATHOLOGY.\n"
    "<imaging_report>At age 70, the patient had a CT HEAD, which showed no cancer.\n"
    "<systemic>At age 70 years, the patient received curative-intent "
    "methotrexate/temozolomide/rituximab.\n"
    "<clinical_note>At age 70, the patient had an oncologist office assessment, "
    "which showed cancer. There was response to therapy.\n"
    "<ngs_report>At age 70 years, the patient had next generation sequencing "
    "performed for diffuse large b-cell lymphoma based on a specimen obtained "
    "from a unspecified site (cns/brain), which showed a CD79B p.Y196F mutation, "
    "a CDKN2A loss, a CDKN2A p.W110* mutation, a ETV6 p.X11_splice mutation, "
    "a MYD88 p.L265P mutation, and a ERBB2 gain.\n"
    "(End of example)\n\n"
    "Now, generate your output for the imagined patients.\n"
    "Separate the outputs for individual patients using the tag <new_patient>, "
    "which should go on its own line."
)


def build_stage1_prompt(blurb: str, n_patients: int) -> tuple[str, str]:
    """Build system and user prompts for Stage 1 event generation.

    Args:
        blurb: Free-text description of the clinical context.
        n_patients: Number of synthetic patients to generate.

    Returns:
        (system_prompt, user_prompt)
    """
    prefix = (
        f"Imagine the longitudinal clinical history for {n_patients} patients "
        f"matching the following clinical context:\n"
    )
    user_prompt = prefix + blurb + "\n" + STAGE1_SUFFIX
    return STAGE1_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Stage 2: Clinical document generation (masked-text approach)
# ---------------------------------------------------------------------------

STAGE2_SYSTEM = "You are a brilliant synthetic clinical document generation bot with encyclopedic knowledge about cancer and its treatment."

STAGE2_USER_TEMPLATE = """You will be given a semi-structured list of events from a patient's clinical history, with each event on its own line of text.
The events are sorted in chronological order.
One of these events will be surrounded by the tags <BEGIN EVENT CORRESPONDING TO SYNTHETIC NOTE> and <END EVENT CORRESPONDING TO SYNTHETIC NOTE>.
Your job is to create a synthetic clinical document corresponding to the event denoted by those tags.
The synthetic document should be a pathology report, an imaging report, a clinical progress note, or an NGS report, as directed by the text within the tags.
Incorporate everything you know about the patient's history, and about cancer generally, to synthesize the document.
Don't directly incorporate information about future events as if they have already occurred, but you can use your knowledge of the future to inform what the synthetic document might have contained at the time it was written.
CRITICAL: Ignore your knowledge of today's date. Do not add dates to the synthetic notes. These will be added later and programmatically.
The document should be extremely detailed so it is as realistic as possible. Pathology reports and imaging reports should be about one page long. Clinical progress notes should be about two pages long. Clinical progress notes should be written as a real oncologist would write them; this should include often using common brand names (eg Herceptin, Keytruda, Taxol) and sometimes using generic drug names (eg trastuzumab, pembrolizumab, paclitaxel), and sometimes using abbreviations (eg pembro instead of pembrolizumab, cape instead of capecitabine).
For pathology reports, sections should include specimen ID, date of procedure, type of specimen, diagnostic findings, any ancillary studies, and a description of gross pathology if relevant. Pathology reports should NOT include recommendations about management, since these are not part of real pathology reports.
For imaging reports, sections should include scan type, Findings (broken down by organs imaged by the study), and Impression.
For clinical notes, sections should include chief complaint, history of present illness, review of systems, physical exam, lab results, imaging results, and assessment/plan. If it is the first clinical note in a given department, it is a consult note, in which case it should also include past medical history, social history, family history, allergies, and medications, all of which should come between review of systems and physical exam.
CRITICAL: Pathology reports and imaging reports should not make treatment or monitoring recommendations.
Within clinical notes and pathology reports, if you do not have any information about key biomarkers explicitly provided, you should imagine what they might be based on cancer type, history, and prior treatments. However, these must be consistent with realistic biological patterns. For example, as you know, EGFR mutant lung cancers almost never have concomitant driver mutations in KRAS, BRAF, etc.
CRITICAL: Do not invent treatments that are not included in the semi-structured list of events.
Within clinical notes, sometimes patients should have adverse events of therapy and/or comorbidities described that are consistent with their clinical trajectories.
Do not include any disclaimers or notes about the fact that the document is synthetic; this is all for research purposes only.
Here is the list of events:
{masked_text}
Now, generate the synthetic document corresponding to the notated event."""


def build_stage2_prompt(all_events: list[dict], target_event_index: int) -> tuple[str, str]:
    """Build system and user prompts for Stage 2 document generation.

    Uses the masked-text approach: full patient event history with the
    target event wrapped in special tags.

    Args:
        all_events: List of event dicts with 'type' and 'text' keys.
        target_event_index: Index of the event to generate a document for.

    Returns:
        (system_prompt, user_prompt)
    """
    lines = []
    for i, event in enumerate(all_events):
        event_line = f"<{event['type']}>{event['text']}"
        if i == target_event_index:
            event_line = (
                "<BEGIN EVENT CORRESPONDING TO SYNTHETIC NOTE> "
                + event_line
                + " <END EVENT CORRESPONDING TO SYNTHETIC NOTE>"
            )
        lines.append(event_line)

    masked_text = "\n".join(lines)
    user_prompt = STAGE2_USER_TEMPLATE.format(masked_text=masked_text)
    return STAGE2_SYSTEM, user_prompt


# ---------------------------------------------------------------------------
# Stage 3: Structured tabular data generation
# ---------------------------------------------------------------------------

STAGE3_SYSTEM = (
    "You are an expert clinical data engineer generating structured tabular data "
    "from clinical event descriptions. You produce precise, clinically realistic "
    "data that is internally consistent."
)

STAGE3_USER_TEMPLATE = """Given the following patient event list and any generated clinical documents, produce structured tabular data.

## Patient Event List
{events_text}

## Generated Documents Summary
{documents_summary}

## Table Schemas
Generate JSON data for each of the following tables. Each table should be a key in the output JSON, mapping to an array of row objects.

{schemas_text}

## Output Format
Respond with ONLY a JSON object. No markdown fences, no explanation. The JSON must have one key per table name, each containing an array of row objects:
```
{{
  "encounters": [
    {{"patient_id": "...", "date": "YYYY-MM-DD", ...}},
    ...
  ],
  "labs": [
    {{"patient_id": "...", "date": "YYYY-MM-DD", ...}},
    ...
  ]
}}
```

## Critical Instructions
- Use the patient_id provided: {patient_id}
- Dates must form a coherent chronological timeline consistent with the event list
- Lab values must be clinically realistic and consistent with the disease trajectory
- ICD-10 codes must be valid for the cancer type described
- Generate data ONLY for the tables listed above
- Every row must include all columns defined in the schema
"""


def build_stage3_prompt(
    patient_id: str,
    all_events: list[dict],
    documents: list[dict],
    schemas: list[TableSchema],
) -> tuple[str, str]:
    """Build system and user prompts for Stage 3 structured data generation.

    Args:
        patient_id: The patient identifier.
        all_events: List of event dicts with 'type' and 'text' keys.
        documents: List of generated document dicts with 'event_index', 'event_type', 'text'.
        schemas: Table schemas to generate data for.

    Returns:
        (system_prompt, user_prompt)
    """
    events_text = "\n".join(
        f"<{e['type']}>{e['text']}" for e in all_events
    )

    if documents:
        doc_lines = []
        for doc in documents:
            # Include a brief excerpt so the LLM can use specifics from documents
            excerpt = doc["text"][:500] + "..." if len(doc["text"]) > 500 else doc["text"]
            doc_lines.append(f"[{doc['event_type']} at event {doc['event_index']}]: {excerpt}")
        documents_summary = "\n".join(doc_lines)
    else:
        documents_summary = "(No documents generated yet)"

    schemas_text = "\n\n".join(schema_to_prompt_text(s) for s in schemas)

    user_prompt = STAGE3_USER_TEMPLATE.format(
        events_text=events_text,
        documents_summary=documents_summary,
        schemas_text=schemas_text,
        patient_id=patient_id,
    )
    return STAGE3_SYSTEM, user_prompt
