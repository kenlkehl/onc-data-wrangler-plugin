"""Get the next batch of patients needing Stage 2+3 processing.

Usage:
    uv run python3 evaluation/get_next_batch.py [batch_size]

Prints JSON list of patient info for the next batch.
"""
import json
import sys
from pathlib import Path

batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 5

events_dir = Path("evaluation/synthetic_output/events")
patients_dir = Path("evaluation/synthetic_output/patients")

existing = set(f.stem for f in patients_dir.glob("*.json")) if patients_dir.exists() else set()
all_events = sorted(events_dir.glob("*.json"))
remaining = [f for f in all_events if f.stem not in existing]

print(f"Completed: {len(existing)}/{len(all_events)}")
print(f"Remaining: {len(remaining)}")

batch = []
for f in remaining[:batch_size]:
    with open(f) as fh:
        p = json.load(fh)
    batch.append({
        "patient_id": p["patient_id"],
        "scenario_index": p.get("scenario_index", 0),
        "scenario_label": p.get("scenario_label", ""),
        "scenario_blurb": p.get("scenario_blurb", "")[:120],
        "n_events": len(p["events"]),
        "events_path": str(f.resolve()),
    })

for b in batch:
    print(f"  {b['patient_id']} ({b['scenario_label']}, {b['n_events']} events)")
