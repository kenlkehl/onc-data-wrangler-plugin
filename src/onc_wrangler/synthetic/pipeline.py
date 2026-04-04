"""Synthetic clinical data generation pipeline for external LLM providers.

This module is used by MODE A (external LLM) of the generate-synthetic-data skill.
MODE B (claude-code) uses agents instead and only needs parse_events + assemble.
"""

from __future__ import annotations

import csv
import json
import re
import uuid
from pathlib import Path
from typing import Optional

from onc_wrangler.llm.base import LLMClient

from .prompts import build_stage1_prompt, build_stage2_prompt, build_stage3_prompt
from .schemas import TableSchema, load_table_schemas


# ---------------------------------------------------------------------------
# Scenario loading
# ---------------------------------------------------------------------------

def load_scenarios(path: str | Path) -> list[dict]:
    """Load scenarios from a JSON or CSV file.

    JSON format: list of objects with 'blurb' and 'n_patients' keys,
    plus optional 'label'.
        [{"blurb": "Stage III NSCLC...", "n_patients": 5, "label": "nsclc_egfr"}]

    CSV format: columns 'blurb' and 'n_patients', plus optional 'label'.

    Args:
        path: Path to a JSON or CSV file containing scenarios.

    Returns:
        List of scenario dicts, each with 'blurb', 'n_patients', and
        optional 'label'.
    """
    path = Path(path)
    if path.suffix.lower() == ".json":
        with open(path) as f:
            scenarios = json.load(f)
    elif path.suffix.lower() == ".csv":
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            scenarios = []
            for row in reader:
                scenario = {
                    "blurb": row["blurb"],
                    "n_patients": int(row.get("n_patients", 5)),
                }
                if row.get("label"):
                    scenario["label"] = row["label"]
                scenarios.append(scenario)
    else:
        raise ValueError(f"Unsupported scenario file format: {path.suffix}. Use .json or .csv")

    # Validate and normalize
    for i, s in enumerate(scenarios):
        if "blurb" not in s:
            raise ValueError(f"Scenario {i} missing 'blurb' field")
        s.setdefault("n_patients", 5)
        s["n_patients"] = int(s["n_patients"])

    return scenarios


# ---------------------------------------------------------------------------
# Event parsing (shared between Mode A and Mode B)
# ---------------------------------------------------------------------------

EVENT_PATTERN = re.compile(r"<(\w+)>(.*?)(?=<|\Z)", re.DOTALL)
DOCUMENT_EVENT_TYPES = {"clinical_note", "imaging_report", "pathology_report", "ngs_report"}


def parse_events(
    raw_text: str,
    scenario_index: Optional[int] = None,
    scenario_blurb: Optional[str] = None,
    scenario_label: Optional[str] = None,
) -> list[dict]:
    """Parse Stage 1 output into per-patient event structures.

    Args:
        raw_text: Raw LLM output with <event_type>text lines
                  separated by <new_patient> tags.
        scenario_index: If provided, tag each patient with this scenario index.
        scenario_blurb: If provided, tag each patient with the originating blurb.
        scenario_label: If provided, tag each patient with this label.

    Returns:
        List of patient dicts, each with 'patient_id', 'events', and
        optionally 'scenario_index', 'scenario_blurb', 'scenario_label'.
    """
    patient_blocks = raw_text.split("<new_patient>")
    patients = []

    for block in patient_blocks:
        block = block.strip()
        if not block:
            continue

        patient_id = f"patient_{uuid.uuid4().hex[:12]}"
        events = []
        for match in EVENT_PATTERN.finditer(block):
            event_type = match.group(1).strip()
            event_text = match.group(2).strip().replace("\n", " ")
            if event_type and event_text:
                events.append({"type": event_type, "text": event_text})

        if events:
            patient = {"patient_id": patient_id, "events": events}
            if scenario_index is not None:
                patient["scenario_index"] = scenario_index
            if scenario_blurb is not None:
                patient["scenario_blurb"] = scenario_blurb
            if scenario_label is not None:
                patient["scenario_label"] = scenario_label
            patients.append(patient)

    return patients


def write_events(patients: list[dict], output_dir: Path) -> None:
    """Write per-patient event JSONs to output_dir/events/."""
    events_dir = output_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    for patient in patients:
        path = events_dir / f"{patient['patient_id']}.json"
        with open(path, "w") as f:
            json.dump(patient, f, indent=2)


# ---------------------------------------------------------------------------
# Stage 1: Generate event lists
# ---------------------------------------------------------------------------

def run_stage1(
    client: LLMClient,
    blurb: str,
    n_patients: int,
    output_dir: Path,
    scenario_index: Optional[int] = None,
    scenario_label: Optional[str] = None,
) -> list[dict]:
    """Generate patient event lists from a clinical context blurb.

    Args:
        client: LLM client for inference.
        blurb: Clinical context description.
        n_patients: Number of patients to generate.
        output_dir: Base output directory.
        scenario_index: If provided, tag patients with this scenario index.
        scenario_label: If provided, tag patients with this label.

    Returns:
        List of patient dicts with events.
    """
    system_prompt, user_prompt = build_stage1_prompt(blurb, n_patients)
    response = client.generate(
        user_prompt,
        system=system_prompt,
        max_tokens=16384,
        temperature=0.8,
    )

    patients = parse_events(
        response.text,
        scenario_index=scenario_index,
        scenario_blurb=blurb,
        scenario_label=scenario_label,
    )
    write_events(patients, output_dir)
    label_str = f" (scenario {scenario_index}: {scenario_label or blurb[:50]})" if scenario_index is not None else ""
    print(f"Stage 1 complete: {len(patients)} patients generated{label_str}")
    return patients


def run_stage1_multi(
    client: LLMClient,
    scenarios: list[dict],
    output_dir: Path,
) -> list[dict]:
    """Generate patient event lists for multiple scenarios.

    Each scenario is a dict with 'blurb', 'n_patients', and optional 'label'.
    Patients are tagged with their originating scenario for traceability.

    Args:
        client: LLM client for inference.
        scenarios: List of scenario dicts.
        output_dir: Base output directory.

    Returns:
        Combined list of patient dicts from all scenarios.
    """
    all_patients = []
    for i, scenario in enumerate(scenarios):
        blurb = scenario["blurb"]
        n_patients = scenario.get("n_patients", 5)
        label = scenario.get("label")
        print(f"--- Scenario {i}/{len(scenarios)}: {label or blurb[:60]} ({n_patients} patients) ---")
        patients = run_stage1(
            client, blurb, n_patients, output_dir,
            scenario_index=i, scenario_label=label,
        )
        all_patients.extend(patients)

    print(f"Stage 1 complete: {len(all_patients)} total patients across {len(scenarios)} scenarios")
    return all_patients


# ---------------------------------------------------------------------------
# Stages 2 + 3: Documents and structured data
# ---------------------------------------------------------------------------

def _generate_documents(
    client: LLMClient,
    patient_id: str,
    events: list[dict],
) -> list[dict]:
    """Generate clinical documents for document-type events (Stage 2)."""
    documents = []
    for i, event in enumerate(events):
        if event["type"] not in DOCUMENT_EVENT_TYPES:
            continue

        system_prompt, user_prompt = build_stage2_prompt(events, i)
        response = client.generate(
            user_prompt,
            system=system_prompt,
            max_tokens=8000,
            temperature=0.5,
        )

        documents.append({
            "event_index": i,
            "event_type": event["type"],
            "text": response.text,
        })

    return documents


def _generate_structured_data(
    client: LLMClient,
    patient_id: str,
    events: list[dict],
    documents: list[dict],
    schemas: list[TableSchema],
) -> dict[str, list[dict]]:
    """Generate structured tabular rows for all table schemas (Stage 3)."""
    system_prompt, user_prompt = build_stage3_prompt(
        patient_id, events, documents, schemas,
    )
    response = client.generate_structured(
        user_prompt,
        system=system_prompt,
        max_tokens=16384,
        temperature=0.3,
    )

    # Parse JSON response, handling common LLM output wrapping
    text = response.text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)

    try:
        tables = json.loads(text)
    except json.JSONDecodeError:
        print(f"  WARNING: Failed to parse structured data JSON for {patient_id}. "
              "Attempting repair...")
        # Try to extract JSON object from the response
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                tables = json.loads(match.group())
            except json.JSONDecodeError:
                print(f"  ERROR: Could not parse structured data for {patient_id}")
                tables = {}
        else:
            tables = {}

    return tables


def run_stages_2_and_3(
    client: LLMClient,
    patients: list[dict],
    schema_dir: Path,
    output_dir: Path,
) -> None:
    """Run Stages 2 and 3 for all patients.

    Args:
        client: LLM client for inference.
        patients: List of patient dicts from Stage 1.
        schema_dir: Path to directory containing table schema YAMLs.
        output_dir: Base output directory.
    """
    schemas = load_table_schemas(schema_dir)
    patients_dir = output_dir / "patients"
    patients_dir.mkdir(parents=True, exist_ok=True)

    for idx, patient in enumerate(patients):
        pid = patient["patient_id"]
        events = patient["events"]
        print(f"Processing patient {idx + 1}/{len(patients)}: {pid}")

        # Stage 2: generate documents
        documents = _generate_documents(client, pid, events)
        print(f"  Stage 2: {len(documents)} documents generated")

        # Stage 3: generate structured data
        tables = _generate_structured_data(client, pid, events, documents, schemas)
        table_summary = {k: len(v) for k, v in tables.items() if isinstance(v, list)}
        print(f"  Stage 3: {table_summary}")

        # Write combined output
        result = {
            "patient_id": pid,
            "events": events,
            "documents": documents,
            "tables": tables,
        }
        # Propagate scenario metadata if present
        for key in ("scenario_index", "scenario_blurb", "scenario_label"):
            if key in patient:
                result[key] = patient[key]
        out_path = patients_dir / f"{pid}.json"
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

    print(f"Stages 2+3 complete: {len(patients)} patients processed")


# ---------------------------------------------------------------------------
# Full pipeline (convenience wrapper)
# ---------------------------------------------------------------------------

def run_full_pipeline(
    client: LLMClient,
    blurb: Optional[str] = None,
    n_patients: int = 5,
    schema_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    scenarios: Optional[list[dict]] = None,
) -> dict:
    """Run the complete synthetic data pipeline (Stages 1-3 + assembly).

    Supports either a single blurb or a list of scenarios. If both are
    provided, scenarios takes precedence.

    Args:
        client: LLM client for inference.
        blurb: Clinical context description (single-scenario mode).
        n_patients: Number of patients (single-scenario mode).
        schema_dir: Path to table schema YAML directory.
        output_dir: Base output directory.
        scenarios: List of scenario dicts, each with 'blurb', 'n_patients',
                   and optional 'label'. Overrides blurb/n_patients.

    Returns:
        Summary dict from assembly.
    """
    from .assembler import assemble_outputs

    if output_dir is None:
        raise ValueError("output_dir is required")
    if schema_dir is None:
        raise ValueError("schema_dir is required")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if scenarios:
        patients = run_stage1_multi(client, scenarios, output_dir)
    elif blurb:
        patients = run_stage1(client, blurb, n_patients, output_dir)
    else:
        raise ValueError("Either 'blurb' or 'scenarios' must be provided")

    run_stages_2_and_3(client, patients, schema_dir, output_dir)
    summary = assemble_outputs(output_dir, schema_dir)
    return summary
