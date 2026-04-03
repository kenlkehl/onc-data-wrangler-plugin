"""Output assembly for synthetic clinical data.

Collects per-patient JSON outputs and combines them into:
  - all_documents.json: combined documents from all patients
  - tables/<table_name>.csv: one CSV per table schema
  - summary.json: generation metadata
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .schemas import load_table_schemas


def assemble_outputs(output_dir: str | Path, schema_dir: str | Path) -> dict:
    """Assemble per-patient outputs into combined files.

    Args:
        output_dir: Base output directory containing patients/ subdirectory.
        schema_dir: Path to table schema YAML directory.

    Returns:
        Summary dict with counts and file paths.
    """
    output_dir = Path(output_dir)
    patients_dir = output_dir / "patients"
    schemas = load_table_schemas(Path(schema_dir))

    all_documents = []
    table_rows: dict[str, list[dict]] = {s.name: [] for s in schemas}
    patient_count = 0
    total_events = 0
    scenario_counts: dict[int, dict] = {}  # scenario_index -> {label, blurb, patients, events}

    # Collect from per-patient JSON files
    for patient_file in sorted(patients_dir.glob("*.json")):
        with open(patient_file) as f:
            patient_data = json.load(f)

        patient_count += 1
        events = patient_data.get("events", [])
        total_events += len(events)

        # Track per-scenario stats
        sc_idx = patient_data.get("scenario_index")
        if sc_idx is not None:
            if sc_idx not in scenario_counts:
                scenario_counts[sc_idx] = {
                    "label": patient_data.get("scenario_label", ""),
                    "blurb": (patient_data.get("scenario_blurb", "") or "")[:100],
                    "patients": 0,
                    "events": 0,
                }
            scenario_counts[sc_idx]["patients"] += 1
            scenario_counts[sc_idx]["events"] += len(events)

        # Scenario metadata to propagate into rows
        scenario_meta = {}
        if "scenario_index" in patient_data:
            scenario_meta["scenario_index"] = patient_data["scenario_index"]
        if "scenario_label" in patient_data:
            scenario_meta["scenario_label"] = patient_data["scenario_label"]

        # Documents
        for doc in patient_data.get("documents", []):
            all_documents.append({
                "patient_id": patient_data["patient_id"],
                **scenario_meta,
                **doc,
            })

        # Structured tables
        tables = patient_data.get("tables", {})
        for schema in schemas:
            rows = tables.get(schema.name, [])
            if isinstance(rows, list):
                if scenario_meta:
                    rows = [{**row, **scenario_meta} for row in rows]
                table_rows[schema.name].extend(rows)

    # Write combined documents
    docs_path = output_dir / "all_documents.json"
    with open(docs_path, "w") as f:
        json.dump(all_documents, f, indent=2)

    # Write combined tables as CSVs
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    table_counts = {}
    for schema in schemas:
        rows = table_rows[schema.name]
        if rows:
            df = pd.DataFrame(rows)
            # Ensure all schema columns are present
            for col in schema.columns:
                if col.name not in df.columns:
                    df[col.name] = ""
            # Reorder to match schema column order
            col_order = [c.name for c in schema.columns if c.name in df.columns]
            extra_cols = [c for c in df.columns if c not in col_order]
            df = df[col_order + extra_cols]
        else:
            # Write empty CSV with headers
            df = pd.DataFrame(columns=[c.name for c in schema.columns])

        csv_path = tables_dir / f"{schema.name}.csv"
        df.to_csv(csv_path, index=False)
        table_counts[schema.name] = len(rows)

    # Write summary
    summary = {
        "patient_count": patient_count,
        "total_events": total_events,
        "avg_events_per_patient": round(total_events / max(patient_count, 1), 1),
        "document_count": len(all_documents),
        "table_row_counts": table_counts,
        "output_files": {
            "documents": str(docs_path),
            "tables": {name: str(tables_dir / f"{name}.csv") for name in table_counts},
            "summary": str(output_dir / "summary.json"),
        },
    }
    if scenario_counts:
        summary["scenarios"] = {
            str(k): v for k, v in sorted(scenario_counts.items())
        }
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Assembly complete: {patient_count} patients, "
          f"{len(all_documents)} documents, "
          f"tables: {table_counts}")
    return summary
