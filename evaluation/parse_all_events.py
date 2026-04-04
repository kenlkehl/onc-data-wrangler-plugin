"""Parse raw event text files from all scenarios and write per-patient event JSONs.

Usage:
    uv run python3 evaluation/parse_all_events.py

Reads raw_events_scenario_*.txt from evaluation/, parses them using
onc_wrangler.synthetic.pipeline.parse_events, and writes per-patient
JSONs to evaluation/synthetic_output/events/.
"""
import json
import sys
from pathlib import Path

# Add plugin root to path
plugin_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(plugin_root / "src"))

from onc_wrangler.synthetic.pipeline import parse_events, write_events

eval_dir = plugin_root / "evaluation"
output_dir = eval_dir / "synthetic_output"
scenarios_path = eval_dir / "scenarios.json"

with open(scenarios_path) as f:
    scenarios = json.load(f)

all_patients = []
for i, scenario in enumerate(scenarios):
    raw_path = eval_dir / f"raw_events_scenario_{i}.txt"
    if not raw_path.exists():
        print(f"WARNING: Missing {raw_path.name}, skipping scenario {i} ({scenario.get('label', '')})")
        continue

    with open(raw_path) as f:
        raw_text = f.read()

    patients = parse_events(
        raw_text,
        scenario_index=i,
        scenario_blurb=scenario["blurb"],
        scenario_label=scenario.get("label"),
    )
    write_events(patients, output_dir)
    all_patients.extend(patients)

    expected = scenario["n_patients"]
    actual = len(patients)
    status = "OK" if actual == expected else f"MISMATCH (expected {expected})"
    print(f"Scenario {i} ({scenario.get('label', '')}): {actual} patients parsed [{status}]")

print(f"\nTotal: {len(all_patients)} patients written to {output_dir / 'events'}")

# Write summary
summary = {
    "total_patients": len(all_patients),
    "patients_by_scenario": {},
}
for p in all_patients:
    sc = p.get("scenario_label", "unknown")
    summary["patients_by_scenario"].setdefault(sc, 0)
    summary["patients_by_scenario"][sc] += 1

with open(output_dir / "events_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
