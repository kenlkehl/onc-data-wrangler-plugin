"""Evaluate extraction accuracy against ground truth.

Computes per-field and per-cancer-type metrics:
- Exact match accuracy for categorical fields
- Fuzzy match for free-text fields
- Coverage (% of ground truth fields with any extraction)
- Confidence calibration

Usage:
    uv run python3 evaluation/evaluate_accuracy.py
    uv run python3 evaluation/evaluate_accuracy.py --extractions-dir evaluation/vllm_output/extractions
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

plugin_root = Path(__file__).resolve().parent.parent
eval_dir = plugin_root / "evaluation"

# Field aliases: ground truth name -> possible extraction name(s)
FIELD_ALIASES = {
    "overall_stage": ["overall_stage", "overall_stage_at_diagnosis"],
    "t_stage": ["t_stage", "t_stage_at_diagnosis"],
    "n_stage": ["n_stage", "n_stage_at_diagnosis"],
    "m_stage": ["m_stage", "m_stage_at_diagnosis"],
    "cancer_category": ["cancer_category"],
    "heme_staging_system": ["heme_staging_system"],
    "heme_stage": ["heme_stage"],
    "primary_site": ["primary_site"],
    "histology": ["histology"],
}


def normalize(val):
    """Normalize a value for comparison."""
    if val is None:
        return ""
    s = str(val).strip().lower()
    # Normalize stage prefixes
    s = s.replace("stage ", "")
    return s


def fuzzy_match(a, b):
    """Token overlap F1 between two strings."""
    tokens_a = set(normalize(a).split())
    tokens_b = set(normalize(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    precision = len(intersection) / len(tokens_b) if tokens_b else 0
    recall = len(intersection) / len(tokens_a) if tokens_a else 0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def get_extracted_value(results: dict, gt_field: str) -> dict:
    """Look up an extracted field using aliases."""
    aliases = FIELD_ALIASES.get(gt_field, [gt_field])
    for alias in aliases:
        if alias in results and isinstance(results[alias], dict):
            return results[alias]
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--extractions-dir", type=str, default=None,
                        help="Path to extractions directory (default: evaluation/extraction_output/extractions)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output report path (default: auto)")
    args = parser.parse_args()

    # Load ground truth
    gt_path = eval_dir / "ground_truth.json"
    if not gt_path.exists():
        print("ERROR: ground_truth.json not found. Run extract_ground_truth.py first.")
        sys.exit(1)

    with open(gt_path) as f:
        ground_truth = json.load(f)

    # Load extraction results
    if args.extractions_dir:
        extractions_dir = Path(args.extractions_dir)
    else:
        extractions_dir = eval_dir / "extraction_output" / "extractions"

    if not extractions_dir.exists():
        print(f"ERROR: {extractions_dir} not found. Run extraction first.")
        sys.exit(1)

    extraction_results = {}
    for ext_file in sorted(extractions_dir.glob("*.json")):
        with open(ext_file) as f:
            data = json.load(f)
        pid = data.get("patient_id", ext_file.stem)
        extraction_results[pid] = data

    provider_info = ""
    if extraction_results:
        sample = next(iter(extraction_results.values()))
        provider = sample.get("provider", "unknown")
        model = sample.get("model", "unknown")
        if provider != "unknown":
            provider_info = f" (provider: {provider}, model: {model})"

    # Define fields to evaluate
    EXACT_FIELDS = ["cancer_category", "overall_stage", "t_stage", "n_stage", "m_stage",
                    "heme_staging_system", "heme_stage"]
    FUZZY_FIELDS = ["primary_site", "histology"]

    # Metrics accumulators
    field_metrics = defaultdict(lambda: {"correct": 0, "total": 0, "extracted": 0, "gt_present": 0})
    cancer_metrics = defaultdict(lambda: defaultdict(lambda: {"correct": 0, "total": 0}))
    confidence_bins = defaultdict(lambda: {"correct": 0, "total": 0})

    matched_patients = 0
    unmatched_gt = []

    for pid, gt in ground_truth.items():
        ext = extraction_results.get(pid)
        if ext is None:
            unmatched_gt.append(pid)
            continue

        matched_patients += 1
        scenario = gt.get("scenario_label", "unknown")
        results = ext.get("results", {})

        # Evaluate exact match fields
        for field in EXACT_FIELDS:
            gt_val = normalize(gt.get(field, ""))
            if not gt_val:
                continue
            field_metrics[field]["gt_present"] += 1
            field_metrics[field]["total"] += 1

            ext_data = get_extracted_value(results, field)
            ext_val = normalize(ext_data.get("value", ""))
            if ext_val and ext_val not in ("unknown", "not applicable", "n/a"):
                field_metrics[field]["extracted"] += 1
            if gt_val == ext_val or (gt_val in ext_val) or (ext_val in gt_val):
                field_metrics[field]["correct"] += 1
                cancer_metrics[scenario][field]["correct"] += 1

            cancer_metrics[scenario][field]["total"] += 1

            # Confidence calibration
            conf = ext_data.get("confidence", 0)
            if conf > 0:
                bin_key = round(conf, 1)
                confidence_bins[bin_key]["total"] += 1
                if gt_val == ext_val or (gt_val in ext_val) or (ext_val in gt_val):
                    confidence_bins[bin_key]["correct"] += 1

        # Evaluate fuzzy match fields
        for field in FUZZY_FIELDS:
            gt_val = gt.get(field, "")
            if not gt_val:
                continue
            field_metrics[field]["gt_present"] += 1
            field_metrics[field]["total"] += 1

            ext_data = get_extracted_value(results, field)
            ext_val = ext_data.get("value", "")
            if ext_val and ext_val not in ("unknown",):
                field_metrics[field]["extracted"] += 1
            score = fuzzy_match(gt_val, ext_val)
            if score >= 0.5:
                field_metrics[field]["correct"] += 1
                cancer_metrics[scenario][field]["correct"] += 1
            cancer_metrics[scenario][field]["total"] += 1

    # Generate report
    report_lines = []
    report_lines.append(f"# Extraction Accuracy Report{provider_info}\n")
    report_lines.append(f"Extractions dir: {extractions_dir}")
    report_lines.append(f"Patients in ground truth: {len(ground_truth)}")
    report_lines.append(f"Patients with extractions: {len(extraction_results)}")
    report_lines.append(f"Matched patients: {matched_patients}")
    report_lines.append(f"Unmatched: {len(unmatched_gt)}\n")

    report_lines.append("## Per-Field Metrics\n")
    report_lines.append("| Field | GT Present | Extracted | Correct | Accuracy | Coverage |")
    report_lines.append("|-------|-----------|-----------|---------|----------|----------|")

    for field in EXACT_FIELDS + FUZZY_FIELDS:
        m = field_metrics[field]
        acc = m["correct"] / m["total"] * 100 if m["total"] > 0 else 0
        cov = m["extracted"] / m["gt_present"] * 100 if m["gt_present"] > 0 else 0
        report_lines.append(
            f"| {field} | {m['gt_present']} | {m['extracted']} | {m['correct']} | "
            f"{acc:.1f}% | {cov:.1f}% |"
        )

    report_lines.append("\n## Per-Cancer-Type Metrics\n")
    report_lines.append("| Cancer Type | Field | Correct | Total | Accuracy |")
    report_lines.append("|------------|-------|---------|-------|----------|")

    for scenario in sorted(cancer_metrics.keys()):
        for field in EXACT_FIELDS + FUZZY_FIELDS:
            cm = cancer_metrics[scenario].get(field, {"correct": 0, "total": 0})
            if cm["total"] == 0:
                continue
            acc = cm["correct"] / cm["total"] * 100
            report_lines.append(
                f"| {scenario} | {field} | {cm['correct']} | {cm['total']} | {acc:.1f}% |"
            )

    report_lines.append("\n## Confidence Calibration\n")
    report_lines.append("| Confidence Bin | Correct | Total | Actual Accuracy |")
    report_lines.append("|---------------|---------|-------|----------------|")
    for conf_bin in sorted(confidence_bins.keys()):
        cb = confidence_bins[conf_bin]
        if cb["total"] > 0:
            actual = cb["correct"] / cb["total"] * 100
            report_lines.append(
                f"| {conf_bin:.1f} | {cb['correct']} | {cb['total']} | {actual:.1f}% |"
            )

    report = "\n".join(report_lines)

    # Save report
    if args.output:
        report_path = Path(args.output)
    else:
        report_path = extractions_dir.parent / "accuracy_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)

    print(report)
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
