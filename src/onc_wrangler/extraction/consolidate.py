"""Consolidate per-patient extraction JSON files into a single parquet.

Handles multiple JSON output formats produced by extraction workers:

- Format A: ``{categories: {cat_name: data, ...}}``
- Format B: ``{results: {field: {value, confidence}, ...}}`` (flat, needs ontology)
- Format C: category keys at top level (``patient``, ``cancer_diagnosis``, etc.)
- Format D: ``{cat_name_records: [...], ...}`` (``_records`` suffix)
- Format E: ``{records: {cat_name: data, ...}}``
- Various naming variants (``patient_level``, ``cancer_diagnoses``, ``treatment_regimens``, etc.)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Keys that are metadata, not category data
_META_KEYS = frozenset({
    "patient_id", "ontology", "ontology_id", "extraction_date",
    "extraction_timestamp", "extraction_status", "n_fields_extracted",
    "mean_confidence", "review_items", "notes", "data_quality_notes",
    "summary", "summary_statistics", "extraction_notes",
})

# Map variant category key names back to canonical names
_CATEGORY_ALIASES: dict[str, str] = {
    # patient variants
    "patient": "patient",
    "patient_level": "patient",
    "patient_level_data": "patient",
    "patient_data": "patient",
    "patient_records": "patient",
    # cancer_diagnosis variants
    "cancer_diagnosis": "cancer_diagnosis",
    "cancer_diagnoses": "cancer_diagnosis",
    "cancer_diagnosis_records": "cancer_diagnosis",
    "diagnosis": "cancer_diagnosis",
    "diagnoses": "cancer_diagnosis",
    # regimen variants
    "regimen": "regimen",
    "regimens": "regimen",
    "regimen_records": "regimen",
    "treatment_regimens": "regimen",
    "treatment_regimen": "regimen",
    # medical_oncologist_assessment variants
    "medical_oncologist_assessment": "medical_oncologist_assessment",
    "medical_oncologist_assessments": "medical_oncologist_assessment",
    "medical_oncologist_assessment_records": "medical_oncologist_assessment",
}


def _resolve_category_key(key: str) -> str | None:
    """Return canonical category name for *key*, or None if not a category."""
    return _CATEGORY_ALIASES.get(key)


def _extract_value(val: Any) -> Any:
    """Unwrap ``{value: X, confidence: ...}`` dicts to just X."""
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


def _flatten_dict_category(
    patient_id: str,
    ontology: str,
    category: str,
    data: dict,
) -> list[dict]:
    """Flatten a dict-valued category (e.g. patient-level fields)."""
    row: dict[str, Any] = {
        "patient_id": patient_id,
        "ontology": ontology,
        "tumor_index": -1,
        "category": category,
    }
    for field, val in data.items():
        extracted = _extract_value(val)
        if isinstance(extracted, list):
            row[field] = "; ".join(str(x) for x in extracted)
        else:
            row[field] = extracted
    return [row]


def _flatten_list_category(
    patient_id: str,
    ontology: str,
    category: str,
    items: list,
) -> list[dict]:
    """Flatten a list-valued category (e.g. cancer_diagnosis, regimen)."""
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row: dict[str, Any] = {
            "patient_id": patient_id,
            "ontology": ontology,
            "category": category,
            "tumor_index": item.get("ca_seq", item.get("tumor_index", 0)),
        }
        for k, v in item.items():
            extracted = _extract_value(v)
            if isinstance(extracted, list):
                row[k] = "; ".join(str(x) for x in extracted)
            else:
                row[k] = extracted
        rows.append(row)
    return rows


def _flatten_category(
    patient_id: str,
    ontology: str,
    category: str,
    data: Any,
) -> list[dict]:
    """Flatten a single category's data regardless of dict/list type."""
    if isinstance(data, dict):
        return _flatten_dict_category(patient_id, ontology, category, data)
    elif isinstance(data, list):
        # A list with a single dict element that has {value, confidence} fields
        # is likely a wrapped patient-level dict — unwrap it
        if (
            len(data) == 1
            and isinstance(data[0], dict)
            and not any(isinstance(v, (dict, list)) for v in data[0].values()
                        if not (isinstance(v, dict) and "value" in v))
        ):
            return _flatten_dict_category(patient_id, ontology, category, data[0])
        return _flatten_list_category(patient_id, ontology, category, data)
    return []


def _load_ontology_field_map(ontology_dir: Path) -> dict[str, str]:
    """Load field-id → category-id mapping from an ontology YAML."""
    import yaml

    ontology_path = ontology_dir / "ontology.yaml"
    if not ontology_path.exists():
        return {}
    with open(ontology_path) as f:
        ont = yaml.safe_load(f)

    field_to_cat: dict[str, str] = {}
    for cat in ont.get("categories", []):
        cat_id = cat.get("id", "")
        for item in cat.get("items", []):
            field_to_cat[item["id"]] = cat_id
    return field_to_cat


def _flatten_flat_results(
    patient_id: str,
    ontology: str,
    results: dict,
    field_to_cat: dict[str, str],
) -> list[dict]:
    """Flatten a flat results dict by grouping fields into categories."""
    # Group fields by category
    cat_fields: dict[str, dict[str, Any]] = {}
    uncategorized: dict[str, Any] = {}

    for field, val in results.items():
        extracted = _extract_value(val)
        category = field_to_cat.get(field)
        if category:
            cat_fields.setdefault(category, {})[field] = extracted
        else:
            uncategorized[field] = extracted

    rows = []
    for category, fields in cat_fields.items():
        row: dict[str, Any] = {
            "patient_id": patient_id,
            "ontology": ontology,
            "category": category,
            "tumor_index": fields.get("ca_seq", -1 if category == "patient" else 0),
        }
        for k, v in fields.items():
            if isinstance(v, list):
                row[k] = "; ".join(str(x) for x in v)
            else:
                row[k] = v
        rows.append(row)

    if uncategorized:
        row = {
            "patient_id": patient_id,
            "ontology": ontology,
            "category": "other",
            "tumor_index": -1,
        }
        row.update(uncategorized)
        rows.append(row)

    return rows


def _process_one_json(
    path: Path,
    field_to_cat: dict[str, str],
) -> list[dict]:
    """Parse one per-patient JSON file and return flattened rows."""
    with open(path) as f:
        data = json.load(f)

    patient_id = data.get("patient_id", path.stem)
    ontology = data.get("ontology", data.get("ontology_id", "unknown"))
    rows: list[dict] = []

    # Format A: explicit "categories" key
    if "categories" in data and isinstance(data["categories"], dict):
        for cat_name, cat_data in data["categories"].items():
            rows.extend(_flatten_category(patient_id, ontology, cat_name, cat_data))
        return rows

    # Format E: explicit "records" key
    if "records" in data and isinstance(data["records"], dict):
        for cat_name, cat_data in data["records"].items():
            canonical = _resolve_category_key(cat_name) or cat_name
            rows.extend(_flatten_category(patient_id, ontology, canonical, cat_data))
        return rows

    # Format B: flat "results" dict — needs ontology field mapping
    if "results" in data and isinstance(data["results"], dict):
        rows.extend(
            _flatten_flat_results(patient_id, ontology, data["results"], field_to_cat)
        )
        return rows

    # Formats C, D, F: category keys at top level (with possible aliases)
    found_categories = False
    for key, val in data.items():
        if key in _META_KEYS:
            continue
        canonical = _resolve_category_key(key)
        if canonical is not None:
            found_categories = True
            rows.extend(_flatten_category(patient_id, ontology, canonical, val))

    if found_categories:
        return rows

    logger.warning("Unrecognized JSON format in %s, keys: %s", path.name, list(data.keys()))
    return rows


def consolidate_extractions(
    extractions_dir: Path,
    ontologies_dir: Path | None = None,
) -> pd.DataFrame:
    """Consolidate per-patient extraction JSONs into a single DataFrame.

    Parameters
    ----------
    extractions_dir:
        Directory containing ``patient_*.json`` files.
    ontologies_dir:
        Root ontologies directory (e.g. ``plugin/data/ontologies/``).
        Used to resolve flat-format results to categories via field mapping.

    Returns
    -------
    DataFrame with columns: patient_id, ontology, tumor_index, category, plus
    field-specific columns. Also saved as ``extractions_dir / extractions.parquet``.
    """
    json_files = sorted(extractions_dir.glob("patient_*.json"))
    if not json_files:
        logger.warning("No patient_*.json files found in %s", extractions_dir)
        return pd.DataFrame()

    # Build field→category mapping from all ontologies referenced
    field_to_cat: dict[str, str] = {}
    if ontologies_dir and ontologies_dir.exists():
        for ont_dir in ontologies_dir.iterdir():
            if ont_dir.is_dir():
                field_to_cat.update(_load_ontology_field_map(ont_dir))

    rows: list[dict] = []
    for jf in json_files:
        try:
            rows.extend(_process_one_json(jf, field_to_cat))
        except Exception:
            logger.exception("Failed to process %s", jf.name)

    if not rows:
        logger.warning("No rows extracted from %d JSON files", len(json_files))
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # Coerce mixed-type object columns for PyArrow
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda x: str(x) if x is not None and not isinstance(x, str) else x
            )

    out_path = extractions_dir / "extractions.parquet"
    df.to_parquet(out_path, index=False)
    logger.info(
        "Consolidated %d rows from %d patients into %s — categories: %s",
        len(df),
        df["patient_id"].nunique(),
        out_path,
        sorted(df["category"].unique().tolist()),
    )
    return df
