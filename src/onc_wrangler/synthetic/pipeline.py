"""Synthetic clinical data generation pipeline.

Generates patient event timelines, clinical documents, and structured
tabular data from clinical scenario blurbs using an LLM backend.

Supports parallel patient processing via ThreadPoolExecutor with
per-patient checkpoint/resume and optional drug-name perturbation.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import numpy as np
from tqdm import tqdm

from onc_wrangler.llm.base import LLMClient

from .drug_perturbation import (
    DEFAULT_DRUG_MAP,
    apply_drug_perturbation,
    compile_replacement_patterns,
)
from .prompts import build_stage1_prompt, build_stage2_prompt, build_stage3_prompt
from .schemas import TableSchema, load_table_schemas

logger = logging.getLogger(__name__)


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
# Event parsing
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
# Atomic file writes
# ---------------------------------------------------------------------------

def _write_json_atomic(path: Path, data: dict) -> None:
    """Write JSON to *path* via a temp file to prevent partial writes."""
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


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
        logger.warning("Failed to parse structured data JSON for %s. Attempting repair...", patient_id)
        # Try to extract JSON object from the response
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                tables = json.loads(match.group())
            except json.JSONDecodeError:
                logger.error("Could not parse structured data for %s", patient_id)
                tables = {}
        else:
            tables = {}

    return tables


def _process_single_patient(
    client: LLMClient,
    patient: dict,
    schemas: list[TableSchema],
    patients_dir: Path,
    drug_patterns: list | None,
    drug_perturbation_prob: float,
) -> tuple[str, int, dict[str, int]]:
    """Process stages 2+3 for one patient and write output atomically.

    Returns:
        Tuple of (patient_id, n_documents, table_row_counts).
    """
    pid = patient["patient_id"]
    events = patient["events"]

    # Stage 2: generate documents
    documents = _generate_documents(client, pid, events)

    # Apply drug perturbation to document text
    if drug_patterns and drug_perturbation_prob > 0:
        rng = np.random.default_rng(hash(pid) & 0xFFFFFFFF)
        for doc in documents:
            if rng.random() < drug_perturbation_prob:
                doc["text"] = apply_drug_perturbation(doc["text"], drug_patterns, rng)

    # Stage 3: generate structured data
    tables = _generate_structured_data(client, pid, events, documents, schemas)
    table_counts = {k: len(v) for k, v in tables.items() if isinstance(v, list)}

    # Build result and write atomically
    result: dict = {
        "patient_id": pid,
        "events": events,
        "documents": documents,
        "tables": tables,
    }
    for key in ("scenario_index", "scenario_blurb", "scenario_label"):
        if key in patient:
            result[key] = patient[key]

    _write_json_atomic(patients_dir / f"{pid}.json", result)
    return pid, len(documents), table_counts


def run_stages_2_and_3(
    client: LLMClient,
    patients: list[dict],
    schema_dir: Path,
    output_dir: Path,
    num_workers: int = 4,
    drug_perturbation_prob: float = 0.3,
    show_progress: bool = True,
) -> None:
    """Run Stages 2 and 3 for all patients with parallel workers.

    Uses ThreadPoolExecutor for concurrent patient processing and
    per-patient file checkpoints so interrupted runs can resume.

    Args:
        client: LLM client for inference.
        patients: List of patient dicts from Stage 1.
        schema_dir: Path to directory containing table schema YAMLs.
        output_dir: Base output directory.
        num_workers: Number of parallel threads (default 4).
        drug_perturbation_prob: Probability of applying drug-name
            perturbation to each generated document (default 0.3).
        show_progress: Show a tqdm progress bar (default True).
    """
    schemas = load_table_schemas(schema_dir)
    patients_dir = output_dir / "patients"
    patients_dir.mkdir(parents=True, exist_ok=True)

    # Checkpoint: skip patients whose output files already exist
    remaining = []
    skipped = 0
    for patient in patients:
        out_path = patients_dir / f"{patient['patient_id']}.json"
        if out_path.exists():
            skipped += 1
        else:
            remaining.append(patient)

    if skipped:
        print(f"Checkpoint: skipping {skipped} already-completed patients")
    print(f"Stage 2+3: {len(remaining)} patients to process")

    if not remaining:
        print("All patients already processed.")
        return

    # Prepare drug perturbation patterns (compiled once, shared across threads)
    drug_patterns = compile_replacement_patterns(DEFAULT_DRUG_MAP) if drug_perturbation_prob > 0 else None

    if num_workers <= 1:
        # Sequential mode (e.g. for claude-code provider with no external LLM)
        iterator = enumerate(remaining)
        if show_progress:
            iterator = tqdm(iterator, total=len(remaining), desc="Generating patients")
        for _idx, patient in iterator:
            pid, n_docs, table_counts = _process_single_patient(
                client, patient, schemas, patients_dir,
                drug_patterns, drug_perturbation_prob,
            )
            if not show_progress:
                print(f"  {pid}: {n_docs} docs, tables: {table_counts}")
    else:
        # Parallel mode
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(
                    _process_single_patient,
                    client, patient, schemas, patients_dir,
                    drug_patterns, drug_perturbation_prob,
                ): patient["patient_id"]
                for patient in remaining
            }

            iterator = as_completed(futures)
            if show_progress:
                iterator = tqdm(iterator, total=len(remaining), desc="Generating patients")

            for future in iterator:
                try:
                    pid, n_docs, table_counts = future.result()
                    if not show_progress:
                        print(f"  {pid}: {n_docs} docs, tables: {table_counts}")
                except Exception:
                    failed_pid = futures[future]
                    logger.exception("Failed to process patient %s", failed_pid)

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
    num_workers: int = 4,
    drug_perturbation_prob: float = 0.3,
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
        num_workers: Number of parallel threads for stages 2+3.
        drug_perturbation_prob: Probability of drug-name perturbation per
            document (0.0 to disable, default 0.3).

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

    run_stages_2_and_3(
        client, patients, schema_dir, output_dir,
        num_workers=num_workers,
        drug_perturbation_prob=drug_perturbation_prob,
    )
    summary = assemble_outputs(output_dir, schema_dir)
    return summary
