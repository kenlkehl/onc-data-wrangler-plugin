"""Generate simplified clinical documents from event lists.

Creates a combined clinical note per patient from their events,
plus minimal encounter and lab rows. This is faster than full
synthetic-data-worker generation while still testing extraction.

Usage:
    uv run python3 evaluation/generate_simple_docs.py
"""
import json
import random
import sys
from pathlib import Path

random.seed(42)

plugin_root = Path(__file__).resolve().parent.parent
eval_dir = plugin_root / "evaluation"
events_dir = eval_dir / "synthetic_output" / "events"
patients_dir = eval_dir / "synthetic_output" / "patients"
patients_dir.mkdir(parents=True, exist_ok=True)

# Check which patients already have full output from workers
existing = set(f.stem for f in patients_dir.glob("*.json"))

DOCUMENT_TYPES = {"clinical_note", "imaging_report", "pathology_report", "ngs_report"}
YEAR_BASE = 2022

processed = 0
skipped = 0

for event_file in sorted(events_dir.glob("*.json")):
    pid = event_file.stem
    if pid in existing:
        skipped += 1
        continue

    with open(event_file) as f:
        patient = json.load(f)

    events = patient["events"]

    # Build documents from document-type events
    documents = []
    encounters = []
    labs = []

    # Track age for date generation
    base_age = None
    for e in events:
        if e["type"] == "demographics":
            import re
            age_match = re.search(r"(\d+)-?\s*year", e["text"])
            if age_match:
                base_age = int(age_match.group(1))
                break
    if base_age is None:
        base_age = 60

    current_age = base_age
    date_offset = 0  # months from diagnosis

    for i, event in enumerate(events):
        etype = event["type"]
        text = event["text"]

        # Extract age from event text
        age_match = re.search(r"[Aa]t age (\d+)", text)
        if age_match:
            new_age = int(age_match.group(1))
            if new_age > current_age:
                date_offset += (new_age - current_age) * 12
                current_age = new_age

        # Generate date from offset
        year = YEAR_BASE + date_offset // 12
        month = 1 + (date_offset % 12)
        day = min(28, random.randint(1, 28))
        date_str = f"{year}-{month:02d}-{day:02d}"
        date_offset += random.randint(1, 3)  # 1-3 months between events

        if etype in DOCUMENT_TYPES:
            # Create a document from the event text
            if etype == "clinical_note":
                doc_text = f"CLINICAL PROGRESS NOTE\n\n"
                doc_text += f"ASSESSMENT AND PLAN:\n{text}\n\n"
                doc_text += "The patient was seen in clinic today for ongoing oncologic management."
            elif etype == "imaging_report":
                doc_text = f"RADIOLOGY REPORT\n\n"
                doc_text += f"FINDINGS:\n{text}\n\n"
                doc_text += "Please correlate clinically."
            elif etype == "pathology_report":
                doc_text = f"PATHOLOGY REPORT\n\n"
                doc_text += f"DIAGNOSIS AND FINDINGS:\n{text}"
            elif etype == "ngs_report":
                doc_text = f"GENOMIC PROFILING REPORT\n\n"
                doc_text += f"RESULTS:\n{text}"
            else:
                doc_text = text

            documents.append({
                "event_index": i,
                "event_type": etype,
                "text": doc_text,
            })

        # Generate encounters for clinical interactions
        dept_map = {
            "clinical_note": "Medical Oncology",
            "imaging_report": "Radiology",
            "pathology_report": "Pathology",
            "ngs_report": "Pathology",
            "systemic": "Medical Oncology",
            "radiation": "Radiation Oncology",
            "surgery": "Surgery",
            "adverse_event": "Medical Oncology",
        }
        visit_map = {
            "clinical_note": "Follow-up",
            "imaging_report": "Imaging",
            "pathology_report": "Procedure",
            "ngs_report": "Procedure",
            "systemic": "Infusion",
            "radiation": "Follow-up",
            "surgery": "Procedure",
            "adverse_event": "Follow-up",
        }

        if etype in dept_map:
            # Determine ICD-10 code from scenario
            scenario = patient.get("scenario_label", "")
            icd_map = {
                "nsclc_egfr": "C34.1", "nsclc_wild": "C34.1",
                "breast_her2": "C50.9", "crc_kras": "C18.9",
                "prostate_mcrpc": "C61", "melanoma_braf": "C43.9",
                "dlbcl": "C83.3", "aml_flt3": "C92.0",
                "myeloma": "C90.0", "pancreatic": "C25.0",
            }
            encounters.append({
                "patient_id": pid,
                "date": date_str,
                "diagnosis_code": icd_map.get(scenario, "C80.1"),
                "department": dept_map[etype],
                "visit_type": visit_map.get(etype, "Follow-up"),
            })

        # Generate labs for chemo visits and some follow-ups
        if etype in ("systemic", "clinical_note") and random.random() < 0.7:
            base_wbc = random.uniform(3.5, 11.0)
            base_hgb = random.uniform(10.0, 15.5)
            base_plt = random.uniform(120, 350)
            base_cr = random.uniform(0.6, 1.2)

            labs.extend([
                {"patient_id": pid, "date": date_str, "test_name": "WBC",
                 "value": f"{base_wbc:.1f}", "unit": "10^9/L",
                 "reference_range": "4.0-11.0",
                 "abnormal_flag": "L" if base_wbc < 4.0 else ("H" if base_wbc > 11.0 else "N")},
                {"patient_id": pid, "date": date_str, "test_name": "Hemoglobin",
                 "value": f"{base_hgb:.1f}", "unit": "g/dL",
                 "reference_range": "12.0-16.0",
                 "abnormal_flag": "L" if base_hgb < 12.0 else "N"},
                {"patient_id": pid, "date": date_str, "test_name": "Platelets",
                 "value": f"{base_plt:.0f}", "unit": "10^9/L",
                 "reference_range": "150-400",
                 "abnormal_flag": "L" if base_plt < 150 else "N"},
                {"patient_id": pid, "date": date_str, "test_name": "Creatinine",
                 "value": f"{base_cr:.2f}", "unit": "mg/dL",
                 "reference_range": "0.6-1.2",
                 "abnormal_flag": "H" if base_cr > 1.2 else "N"},
            ])

    # Build output
    result = {
        "patient_id": pid,
        "events": events,
        "documents": documents,
        "tables": {
            "encounters": encounters,
            "labs": labs,
        },
    }
    # Propagate scenario metadata
    for key in ("scenario_index", "scenario_blurb", "scenario_label"):
        if key in patient:
            result[key] = patient[key]

    out_path = patients_dir / f"{pid}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    processed += 1

print(f"Processed: {processed} patients (simplified docs)")
print(f"Skipped (already have full output): {skipped}")
print(f"Total in patients dir: {len(list(patients_dir.glob('*.json')))}")
