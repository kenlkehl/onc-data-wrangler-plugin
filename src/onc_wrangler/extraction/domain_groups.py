"""Domain group definitions for phased extraction.

NAACCR domain groups are hand-curated with expert prompts ported from the
onc-registry-extraction pipeline.  Non-NAACCR ontologies get auto-generated
domain groups from their ``DataCategory`` objects.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..ontologies.protocols import DomainGroup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NAACCR item number lists (from the registry extraction pipeline)
# ---------------------------------------------------------------------------

DEMOGRAPHICS_ITEMS = [
    380, 390, 400, 410, 440, 441, 442, 449, 450, 470, 490, 500, 522, 523,
    150, 160, 161, 190, 220, 230, 240, 252, 254,
]

# Patient-level items: extracted once, shared across all diagnoses
PATIENT_LEVEL_ITEMS = [
    150, 160, 161, 190,   # Race 1-3, Spanish/Hispanic Origin
    220,                   # Sex
    240,                   # Date of Birth
    252, 254,             # Birthplace Country, State
]

# Diagnosis-level items from demographics: extracted per diagnosis
DIAGNOSIS_IDENTITY_ITEMS = [
    380,                   # Sequence Number--Central
    390,                   # Date of Diagnosis
    400,                   # Primary Site
    410,                   # Laterality
    440, 441, 442, 449, 450,  # Grade fields
    470, 490,             # Diagnostic Confirmation
    500,                   # Date of Diagnosis Flag
    522, 523,             # Histologic Type, Behavior Code
    230,                   # Age at Diagnosis (may differ per diagnosis)
]

SURGERY_ITEMS = [
    1200, 1290, 1291, 1292, 1294, 1296, 1310, 1320, 1330, 1340, 1350,
    1640, 3170, 3180, 3190,
]

RADIATION_ITEMS = [
    1210, 1360, 1370, 1380, 1430,
    1501, 1502, 1503, 1504, 1505, 1506, 1507,
    1511, 1512, 1513, 1514, 1515, 1516, 1517,
    1521, 1522, 1523, 1524, 1525, 1526, 1527,
    1531, 1532, 1533, 1550, 1570, 3220,
]

SYSTEMIC_ITEMS = [
    1220, 1230, 1240, 1250, 1285, 1390, 1400, 1410, 1420,
    1632, 1633, 1634, 1639, 3230, 3250, 3270,
]

FOLLOWUP_ITEMS = [1750, 1760, 1770, 1772, 1790, 1910]

TEXT_ITEMS = [
    2520, 2530, 2540, 2550, 2560, 2570, 2580, 2590,
    2600, 2610, 2620, 2630, 2640, 2650, 2660, 2670, 2680,
]


# ---------------------------------------------------------------------------
# NAACCR domain-specific system prompts
# ---------------------------------------------------------------------------

DEMOGRAPHICS_SYSTEM_PROMPT = """\
You are an expert cancer registrar certified by the NCRA. You extract NAACCR v26 \
cancer registry data items from clinical text with registry-grade precision.

TASK: Extract demographics and cancer identification data. Identify the PRIMARY \
CANCER being reported (not metastases, not secondary conditions).

CRITICAL RULES:
1. Primary Site: ICD-O-3 topography code (C##.#). Do NOT confuse metastatic sites with primary.
2. Histologic Type: ICD-O-3 morphology code (4 digits, 8000-9989).
3. Behavior Code: 0=benign, 1=uncertain, 2=in situ, 3=malignant primary.
4. Date of Diagnosis: EARLIEST date cancer was first suspected/confirmed (YYYYMMDD).
5. Extract ONLY what is explicitly stated. Do not infer.
6. For each item, rate confidence 0.0-1.0 and quote supporting evidence (max 200 chars).

{json_format_instructions}"""

STAGING_SYSTEM_PROMPT = """\
You are an expert cancer registrar performing staging extraction for a \
{primary_site_desc} cancer case (Primary Site: {primary_site}, Histology: {histology}).

{site_context}

TASK: Extract staging, tumor characteristics, and prognostic factors.

CRITICAL RULES:
1. TNM: Distinguish clinical (c) from pathological (p) staging. Do not mix components.
2. Tumor Size: Record in millimeters. Pathological preferred over clinical.
3. Summary Stage 2018: 0=in situ, 1=localized, 2=regional direct extension, \
3=regional LN only, 4=regional both, 7=distant, 9=unknown.
4. EOD: Record primary tumor extent, regional nodes, and mets using valid codes.
5. Biomarkers: Extract exact values (e.g., ER 95%, PSA 4.2, Gleason 3+4=7).
6. Regional Nodes: 00=none examined, 01-89=exact count, 90=90+, 99=unknown.
7. Mets at DX: For each site (bone, brain, distant LN, liver, lung, other): \
0=none, 1=yes, 8=N/A, 9=unknown.
8. Provide confidence 0.0-1.0 and evidence for each item.

{json_format_instructions}"""

SURGERY_SYSTEM_PROMPT = """\
You are an expert cancer registrar extracting first course surgical treatment data \
for a {primary_site} cancer case.

TASK: Extract surgical treatment. First course = initial treatment plan only.

CRITICAL RULES:
1. Surgery Date: YYYYMMDD of most definitive procedure.
2. Distinguish diagnostic procedures (biopsies) from definitive surgery.
3. LN Surgery Scope: 0=none, 1=biopsy, 2=sentinel, 3=unknown count, \
5=1-3 removed, 6=4+ removed, 7=sentinel+complete, 9=unknown.
4. Surgical Margins: 0=R0, 1=residual NOS, 2=R1, 3=R2, 8=no surgery, 9=unknown.
5. Provide confidence and evidence for each item.

{json_format_instructions}"""

RADIATION_SYSTEM_PROMPT = """\
You are an expert cancer registrar extracting first course radiation treatment data.

TASK: Extract radiation therapy information. First course only.

CRITICAL RULES:
1. Radiation Date: YYYYMMDD when radiation started.
2. RX Summ--Radiation: 0=none, 1=beam, 2=implants, 3=radioisotopes, 4=combo, 5=NOS, 9=unknown.
3. Up to 3 phases, each with: dose per fraction, fractions, total dose, modality, technique, volume.
4. Dose in cGy. Total = dose/fraction x fractions.
5. Provide confidence and evidence for each item.

{json_format_instructions}"""

SYSTEMIC_SYSTEM_PROMPT = """\
You are an expert cancer registrar extracting first course systemic therapy data.

TASK: Extract chemotherapy, hormone therapy, immunotherapy (BRM), and other systemic treatment.

CRITICAL RULES:
1. Chemo Date: YYYYMMDD when started.
2. Chemo: 00=none, 01=NOS, 02=single, 03=multi-agent, 85=not recommended, 87=refused, 99=unknown.
3. Hormone: 00=none, 01=hormone therapy, 85=not recommended, 87=refused, 99=unknown.
4. BRM/Immunotherapy: 00=none, 01=BRM, 85=not recommended, 87=refused, 99=unknown.
5. Treatment Status: 0=none given, 1=completed, 2=incomplete, 9=unknown.
6. Neoadjuvant: 0=no, 1=yes, 9=unknown.
7. Provide confidence and evidence for each item.

{json_format_instructions}"""

FOLLOWUP_SYSTEM_PROMPT = """\
You are an expert cancer registrar extracting follow-up and outcome data.

TASK: Extract follow-up and vital status information.

CRITICAL RULES:
1. Date of Last Contact: Most recent date patient known alive or date of death (YYYYMMDD).
2. Vital Status: 0=Dead, 1=Alive.
3. Cancer Status: 1=no evidence of disease, 2=evidence of disease, 9=unknown.
4. Provide confidence and evidence for each item.

{json_format_instructions}"""

NARRATIVE_SYSTEM_PROMPT = """\
You are an expert cancer registrar writing narrative summaries for registry reporting.

TASK: Compose concise, factual summaries for cancer registry text fields.

RULES:
1. Only include information found in the text.
2. Each summary under 4000 characters.
3. Use standard medical terminology.
4. Include dates, measurements, specific findings.
5. Do not include patient identifiers.

{json_format_instructions}"""


# ---------------------------------------------------------------------------
# User prompt templates
# ---------------------------------------------------------------------------

CHUNK_USER_TEMPLATE = """\
Clinical text (dates: {first_date} to {last_date}):
---
{chunk_text}
---

{tumor_context}

{prior_state_block}

Extract the following data items. For coded items, use ONLY the valid codes listed.
If an item was previously extracted with high confidence and this text provides no better
evidence, you may output the same value. Only update if this text provides STRONGER
evidence or a MORE SPECIFIC value.

{json_field_descriptions}"""


NARRATIVE_USER_TEMPLATE = """\
Clinical text (dates: {first_date} to {last_date}):
---
{chunk_text}
---

{prior_narratives_block}

Update each narrative summary to incorporate any new relevant information.
If no new information is relevant for a field, reproduce the prior text exactly.

{json_field_descriptions}"""


# ---------------------------------------------------------------------------
# Generic system prompt for non-NAACCR ontologies
# ---------------------------------------------------------------------------

GENERIC_DOMAIN_SYSTEM_PROMPT = """\
You are a clinical data extraction system specializing in structured data extraction \
from clinical notes. Extract information for the {domain_name} domain.

{domain_context}

RULES:
1. Extract ONLY what is explicitly stated in the text. Do not infer.
2. For each item, rate your confidence 0.0-1.0.
3. Provide a short evidence quote (max 200 chars) from the text.
4. Use valid codes when provided. If not found, use "unknown" and confidence 0.0.

{json_format_instructions}"""


# ---------------------------------------------------------------------------
# Helper: build prior state block from generalized ExtractionResult
# ---------------------------------------------------------------------------

def build_prior_state_block(
    prior: dict[str, Any],
    field_ids: list[str] | None = None,
) -> str:
    """Format prior extraction state for prompts.

    Works with both NAACCR (int-keyed) and generic (string-keyed) results.
    """
    if not prior:
        return "No prior extraction state -- this is the first chunk."

    lines = ["PRIOR EXTRACTION STATE (update only with higher-confidence evidence):"]
    items_to_show = field_ids if field_ids else sorted(prior.keys())

    for fid in items_to_show:
        result = prior.get(fid) if isinstance(fid, str) else prior.get(str(fid))
        if result is None:
            continue
        confidence = getattr(result, "confidence", 0.0)
        if confidence <= 0.0:
            continue
        value = getattr(result, "resolved_code", "") or getattr(result, "extracted_value", "")
        if not value:
            continue
        name = getattr(result, "field_name", fid)
        lines.append(f"- {name}: {value} (confidence: {confidence:.2f})")

    if len(lines) == 1:
        return "No prior extraction state -- this is the first chunk."

    return "\n".join(lines)


def build_prior_narratives_block(
    prior: dict[str, Any],
    text_field_ids: list[str],
) -> str:
    """Format prior narrative summaries for prompts."""
    if not prior:
        return "No prior narrative summaries -- this is the first chunk."

    lines = ["PRIOR NARRATIVE SUMMARIES:"]
    for fid in text_field_ids:
        result = prior.get(fid)
        if result is None:
            continue
        value = getattr(result, "resolved_code", "") or getattr(result, "extracted_value", "")
        if not value:
            continue
        name = getattr(result, "field_name", fid)
        lines.append(f"- {name}: {value}")

    if len(lines) == 1:
        return "No prior narrative summaries -- this is the first chunk."

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Domain group builders
# ---------------------------------------------------------------------------

def build_naaccr_domain_groups() -> list[DomainGroup]:
    """Return the hand-curated NAACCR domain groups."""
    return [
        DomainGroup(
            group_id="demographics",
            name="Demographics & Cancer ID",
            field_ids=[str(n) for n in DEMOGRAPHICS_ITEMS],
            system_prompt_template=DEMOGRAPHICS_SYSTEM_PROMPT,
            depends_on=[],
            context_keys=[],
        ),
        DomainGroup(
            group_id="staging",
            name="Staging & Prognostic Factors",
            field_ids=[],  # Populated dynamically after schema resolution
            system_prompt_template=STAGING_SYSTEM_PROMPT,
            depends_on=["demographics"],
            context_keys=["primary_site", "histology", "schema"],
            dynamic=True,
        ),
        DomainGroup(
            group_id="surgery",
            name="Surgical Treatment",
            field_ids=[str(n) for n in SURGERY_ITEMS],
            system_prompt_template=SURGERY_SYSTEM_PROMPT,
            depends_on=["demographics"],
            context_keys=["primary_site"],
        ),
        DomainGroup(
            group_id="radiation",
            name="Radiation Treatment",
            field_ids=[str(n) for n in RADIATION_ITEMS],
            system_prompt_template=RADIATION_SYSTEM_PROMPT,
            depends_on=["demographics"],
        ),
        DomainGroup(
            group_id="systemic",
            name="Systemic Therapy",
            field_ids=[str(n) for n in SYSTEMIC_ITEMS],
            system_prompt_template=SYSTEMIC_SYSTEM_PROMPT,
            depends_on=["demographics"],
        ),
        DomainGroup(
            group_id="followup",
            name="Follow-up & Outcomes",
            field_ids=[str(n) for n in FOLLOWUP_ITEMS],
            system_prompt_template=FOLLOWUP_SYSTEM_PROMPT,
            depends_on=[],
        ),
        DomainGroup(
            group_id="narratives",
            name="Narrative Summaries",
            field_ids=[str(n) for n in TEXT_ITEMS],
            system_prompt_template=NARRATIVE_SYSTEM_PROMPT,
            depends_on=[],
            is_narrative=True,
        ),
    ]


def build_generic_domain_groups(ontology: Any) -> list[DomainGroup]:
    """Auto-generate domain groups from an ontology's DataCategories.

    Each DataCategory becomes one DomainGroup with a generic system prompt.
    Deduplicates by category id to avoid duplicates from base + site_specific.
    """
    groups: list[DomainGroup] = []
    seen_ids: set[str] = set()

    categories = ontology.get_base_items()
    try:
        site_categories = ontology.get_site_specific_items("generic")
        categories = categories + site_categories
    except Exception:
        pass

    for cat in categories:
        if cat.id in seen_ids:
            continue
        seen_ids.add(cat.id)

        field_ids = []
        for item in cat.items:
            fid = getattr(item, "json_field", None) or getattr(item, "id", None) or item.name
            field_ids.append(fid)

        groups.append(DomainGroup(
            group_id=cat.id,
            name=cat.name,
            field_ids=field_ids,
            system_prompt_template=GENERIC_DOMAIN_SYSTEM_PROMPT,
            depends_on=[],
            context_keys=[],
        ))

    return groups


# ---------------------------------------------------------------------------
# Multi-diagnosis domain group builders
# ---------------------------------------------------------------------------

PATIENT_DEMOGRAPHICS_PROMPT = """\
You are an expert cancer registrar certified by the NCRA. You extract NAACCR v26 \
cancer registry data items from clinical text with registry-grade precision.

TASK: Extract PATIENT-LEVEL demographics that apply to the person regardless \
of how many cancers they have (sex, race, birthplace, date of birth).

CRITICAL RULES:
1. These items describe the PATIENT, not any specific cancer diagnosis.
2. Extract ONLY what is explicitly stated. Do not infer.
3. For each item, rate confidence 0.0-1.0 and quote supporting evidence (max 200 chars).

{json_format_instructions}"""

DIAGNOSIS_DEMOGRAPHICS_PROMPT = """\
You are an expert cancer registrar certified by the NCRA. You extract NAACCR v26 \
cancer registry data items from clinical text with registry-grade precision.

TASK: Extract diagnosis identification data for ONE SPECIFIC cancer diagnosis.

{tumor_context}

CRITICAL RULES:
1. Primary Site: ICD-O-3 topography code (C##.#). Extract ONLY for the specified diagnosis.
2. Histologic Type: ICD-O-3 morphology code (4 digits, 8000-9989).
3. Behavior Code: 0=benign, 1=uncertain, 2=in situ, 3=malignant primary.
4. Date of Diagnosis: EARLIEST date THIS cancer was first suspected/confirmed (YYYYMMDD).
5. Do NOT confuse this diagnosis with other cancers the patient may have.
6. For each item, rate confidence 0.0-1.0 and quote supporting evidence (max 200 chars).

{json_format_instructions}"""


def build_naaccr_domain_groups_multi() -> tuple[list[DomainGroup], list[DomainGroup]]:
    """Return ``(patient_groups, diagnosis_groups)`` for multi-diagnosis extraction.

    Splits the demographics group into patient-level (sex, race, etc.) and
    diagnosis-level (primary site, histology, etc.).  All other groups are
    diagnosis-level.
    """
    patient_groups = [
        DomainGroup(
            group_id="demographics_patient",
            name="Patient Demographics",
            field_ids=[str(n) for n in PATIENT_LEVEL_ITEMS],
            system_prompt_template=PATIENT_DEMOGRAPHICS_PROMPT,
            depends_on=[],
            context_keys=[],
        ),
    ]

    diagnosis_groups = [
        DomainGroup(
            group_id="demographics_diagnosis",
            name="Diagnosis Identification",
            field_ids=[str(n) for n in DIAGNOSIS_IDENTITY_ITEMS],
            system_prompt_template=DIAGNOSIS_DEMOGRAPHICS_PROMPT,
            depends_on=[],
            context_keys=[],
        ),
        DomainGroup(
            group_id="staging",
            name="Staging & Prognostic Factors",
            field_ids=[],
            system_prompt_template=STAGING_SYSTEM_PROMPT,
            depends_on=["demographics_diagnosis"],
            context_keys=["primary_site", "histology", "schema"],
            dynamic=True,
        ),
        DomainGroup(
            group_id="surgery",
            name="Surgical Treatment",
            field_ids=[str(n) for n in SURGERY_ITEMS],
            system_prompt_template=SURGERY_SYSTEM_PROMPT,
            depends_on=["demographics_diagnosis"],
            context_keys=["primary_site"],
        ),
        DomainGroup(
            group_id="radiation",
            name="Radiation Treatment",
            field_ids=[str(n) for n in RADIATION_ITEMS],
            system_prompt_template=RADIATION_SYSTEM_PROMPT,
            depends_on=["demographics_diagnosis"],
        ),
        DomainGroup(
            group_id="systemic",
            name="Systemic Therapy",
            field_ids=[str(n) for n in SYSTEMIC_ITEMS],
            system_prompt_template=SYSTEMIC_SYSTEM_PROMPT,
            depends_on=["demographics_diagnosis"],
        ),
        DomainGroup(
            group_id="followup",
            name="Follow-up & Outcomes",
            field_ids=[str(n) for n in FOLLOWUP_ITEMS],
            system_prompt_template=FOLLOWUP_SYSTEM_PROMPT,
            depends_on=[],
        ),
        DomainGroup(
            group_id="narratives",
            name="Narrative Summaries",
            field_ids=[str(n) for n in TEXT_ITEMS],
            system_prompt_template=NARRATIVE_SYSTEM_PROMPT,
            depends_on=[],
            is_narrative=True,
        ),
    ]

    return patient_groups, diagnosis_groups


def build_generic_domain_groups_multi(ontology: Any) -> tuple[list[DomainGroup], list[DomainGroup]]:
    """Split generic ontology groups into patient-level and diagnosis-level.

    Uses ``DataCategory.per_diagnosis`` to classify each category.
    """
    patient_groups: list[DomainGroup] = []
    diagnosis_groups: list[DomainGroup] = []
    seen_ids: set[str] = set()

    categories = ontology.get_base_items()
    try:
        site_categories = ontology.get_site_specific_items("generic")
        categories = categories + site_categories
    except Exception:
        pass

    for cat in categories:
        if cat.id in seen_ids:
            continue
        seen_ids.add(cat.id)

        field_ids = []
        for item in cat.items:
            fid = getattr(item, "json_field", None) or getattr(item, "id", None) or item.name
            field_ids.append(fid)

        group = DomainGroup(
            group_id=cat.id,
            name=cat.name,
            field_ids=field_ids,
            system_prompt_template=GENERIC_DOMAIN_SYSTEM_PROMPT,
            depends_on=[],
            context_keys=[],
        )

        if getattr(cat, "per_diagnosis", False):
            diagnosis_groups.append(group)
        else:
            patient_groups.append(group)

    # If no categories are marked per_diagnosis, treat everything as diagnosis-level
    # (backward compatible: all groups run per-diagnosis, which for a single
    # diagnosis is equivalent to the old behaviour)
    if not diagnosis_groups:
        diagnosis_groups = patient_groups
        patient_groups = []

    return patient_groups, diagnosis_groups
