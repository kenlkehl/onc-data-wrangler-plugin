"""Convert all_documents.json to a notes CSV for extraction.

Usage:
    uv run python3 evaluation/prepare_notes_csv.py

Creates evaluation/synthetic_output/notes.csv with columns:
patient_id, text, date, note_type
"""
import json
import sys
from pathlib import Path

plugin_root = Path(__file__).resolve().parent.parent
eval_dir = plugin_root / "evaluation"
docs_path = eval_dir / "synthetic_output" / "all_documents.json"
notes_path = eval_dir / "synthetic_output" / "notes.csv"

with open(docs_path) as f:
    documents = json.load(f)

print(f"Loaded {len(documents)} documents")

# Build CSV rows
import csv
with open(notes_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["patient_id", "text", "date", "note_type"])
    for doc in documents:
        writer.writerow([
            doc["patient_id"],
            doc["text"],
            "",  # date will be empty for synthetic notes
            doc.get("event_type", "clinical_note"),
        ])

print(f"Notes CSV written to {notes_path} ({len(documents)} rows)")
