"""Extract ground truth from synthetic event lists.

Parses the event text for each patient to build a structured ground truth
mapping used for evaluating extraction accuracy.

Usage:
    uv run python3 evaluation/extract_ground_truth.py
"""
import json
import re
import sys
from pathlib import Path

plugin_root = Path(__file__).resolve().parent.parent
eval_dir = plugin_root / "evaluation"
events_dir = eval_dir / "synthetic_output" / "events"

ground_truth = {}

for event_file in sorted(events_dir.glob("*.json")):
    with open(event_file) as f:
        patient = json.load(f)

    pid = patient["patient_id"]
    events = patient.get("events", [])
    scenario_label = patient.get("scenario_label", "unknown")
    scenario_index = patient.get("scenario_index", -1)

    gt = {
        "patient_id": pid,
        "scenario_label": scenario_label,
        "scenario_index": scenario_index,
        "cancer_category": None,
        "primary_site": None,
        "histology": None,
        "overall_stage": None,
        "t_stage": None,
        "n_stage": None,
        "m_stage": None,
        "heme_staging_system": None,
        "heme_stage": None,
        "biomarkers": [],
        "treatments": [],
        "surgeries": [],
        "radiation": [],
        "adverse_events": [],
    }

    # Determine cancer category from scenario label
    heme_labels = {"dlbcl", "aml_flt3", "myeloma"}
    if scenario_label in heme_labels:
        if scenario_label == "dlbcl":
            gt["cancer_category"] = "lymphoma"
        elif scenario_label == "aml_flt3":
            gt["cancer_category"] = "leukemia"
        elif scenario_label == "myeloma":
            gt["cancer_category"] = "myeloma"
    else:
        gt["cancer_category"] = "solid_tumor"

    for event in events:
        etype = event["type"]
        text = event["text"].lower()

        if etype == "demographics":
            # Try to extract age, sex
            age_match = re.search(r'(\d+)\s*-?\s*year\s*-?\s*old', text)
            sex_match = re.search(r'\b(male|female|man|woman)\b', text)
            if age_match:
                gt.setdefault("age_at_event", int(age_match.group(1)))
            if sex_match:
                sex = sex_match.group(1)
                gt["sex"] = "male" if sex in ("male", "man") else "female"

        elif etype == "diagnosis":
            # Extract staging info from diagnosis events
            stage_match = re.search(r'stage\s+(i{1,3}v?|iv|[0-4])[abc]?\b', text, re.IGNORECASE)
            if stage_match and not gt["overall_stage"]:
                gt["overall_stage"] = stage_match.group(0).replace("stage ", "Stage ").strip()

            t_match = re.search(r'\b(t[0-4][abc]?)\b', text, re.IGNORECASE)
            n_match = re.search(r'\b(n[0-3][abc]?)\b', text, re.IGNORECASE)
            m_match = re.search(r'\b(m[0-1][abc]?)\b', text, re.IGNORECASE)
            if t_match and not gt["t_stage"]:
                gt["t_stage"] = t_match.group(1).upper()
            if n_match and not gt["n_stage"]:
                gt["n_stage"] = n_match.group(1).upper()
            if m_match and not gt["m_stage"]:
                gt["m_stage"] = m_match.group(1).upper()

            # Extract site codes
            site_match = re.search(r'(c\d{2}\.?\d?)', text, re.IGNORECASE)
            if site_match and not gt["primary_site"]:
                gt["primary_site"] = site_match.group(1).upper()

            # Extract histology codes
            hist_match = re.search(r'(\d{4})', text)
            if hist_match:
                code = hist_match.group(1)
                if 8000 <= int(code) <= 9999 and not gt["histology"]:
                    gt["histology"] = code

            # Ann Arbor staging for lymphoma
            ann_arbor_match = re.search(r'ann arbor\s+(?:stage\s+)?([iv]+[abse]*)', text, re.IGNORECASE)
            if ann_arbor_match:
                gt["heme_staging_system"] = "Ann Arbor"
                gt["heme_stage"] = ann_arbor_match.group(1).upper()

            # ISS for myeloma
            iss_match = re.search(r'iss\s+(?:stage\s+)?([iv]+|[0-3])', text, re.IGNORECASE)
            if iss_match:
                gt["heme_staging_system"] = "ISS"
                gt["heme_stage"] = "ISS " + iss_match.group(1).upper()

            # ELN for AML
            eln_match = re.search(r'eln\s+(?:risk\s+)?(?:category\s+)?(favorable|intermediate|adverse)', text, re.IGNORECASE)
            if eln_match:
                gt["heme_staging_system"] = "ELN"
                gt["heme_stage"] = eln_match.group(1).lower()

        elif etype == "systemic":
            gt["treatments"].append(text)

        elif etype == "surgery":
            gt["surgeries"].append(text)

        elif etype == "radiation":
            gt["radiation"].append(text)

        elif etype == "adverse_event":
            gt["adverse_events"].append(text)

        elif etype == "ngs_report":
            # Extract biomarker mentions
            biomarker_patterns = [
                r'egfr\s+[\w\s]*(?:l858r|exon\s*19|t790m)',
                r'kras\s+[\w\s]*g12[dvc]',
                r'braf\s+[\w\s]*v600[ek]',
                r'her2[\s/]+(?:positive|negative|amplified|3\+|2\+)',
                r'pd-?l1\s+[\w\s]*(?:tps|cps)?\s*[\d><%]+',
                r'alk[\s/-]+(?:positive|negative|rearrangement)',
                r'ros1[\s/-]+(?:positive|negative)',
                r'brca[12][\s/-]+(?:positive|negative|mutated|wild)',
                r'flt3[\s/-]+(?:itd|tkd)',
                r'npm1[\s/-]+(?:positive|negative|mutated)',
                r'msi[\s/-]+(?:high|low|stable)',
                r'mmr[\s/-]+(?:deficient|proficient)',
            ]
            for pattern in biomarker_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for m in matches:
                    if m not in gt["biomarkers"]:
                        gt["biomarkers"].append(m)

    ground_truth[pid] = gt

# Save
gt_path = eval_dir / "ground_truth.json"
with open(gt_path, "w") as f:
    json.dump(ground_truth, f, indent=2)

print(f"Ground truth extracted for {len(ground_truth)} patients")
print(f"Saved to {gt_path}")

# Print summary
for label in sorted(set(g["scenario_label"] for g in ground_truth.values())):
    patients = [g for g in ground_truth.values() if g["scenario_label"] == label]
    n_with_stage = sum(1 for g in patients if g["overall_stage"] or g["heme_stage"])
    n_with_site = sum(1 for g in patients if g["primary_site"])
    n_with_biomarkers = sum(1 for g in patients if g["biomarkers"])
    print(f"  {label}: {len(patients)} patients, "
          f"{n_with_stage} with stage, {n_with_site} with site, "
          f"{n_with_biomarkers} with biomarkers")
