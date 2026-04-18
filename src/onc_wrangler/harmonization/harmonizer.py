"""Structured data harmonization.

Maps existing structured dataset columns to ontology fields.
All mappings are discovered through agent interaction or configured manually.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FieldMapping:
    """Mapping from a source column to an ontology field."""
    source_column: str
    target_field: str
    target_category: str
    transform: Optional[str] = None
    value_map: Optional[dict] = None


class Harmonizer:
    """Map existing structured dataset columns to ontology fields.

    Mappings can be:
    - Discovered through agent-driven field exploration
    - Configured manually in the project YAML
    - Provided programmatically via FieldMapping objects
    """

    def __init__(self, mappings: Optional[list[FieldMapping]] = None):
        self.mappings = mappings or []

    @classmethod
    def from_config(cls, field_mappings: dict[str, Any]) -> "Harmonizer":
        """Create Harmonizer from project config field_mappings section.

        Expected format:
        ```yaml
        field_mappings:
          diagnosis:
            - source: SITE_CD
              target: primary_site
            - source: HISTOLOGY_DESC
              target: histology
          biomarker:
            - source: BIOMARKER_NAME
              target: biomarker_tested
              value_map:
                PDL1: PD-L1
        ```
        """
        mappings = []
        for category, items in field_mappings.items():
            if not isinstance(items, list):
                continue
            for item in items:
                mappings.append(FieldMapping(
                    source_column=item["source"],
                    target_field=item["target"],
                    target_category=category,
                    transform=item.get("transform"),
                    value_map=item.get("value_map"),
                ))
        return cls(mappings)

    def add_mapping(self, mapping: FieldMapping):
        """Add a field mapping."""
        self.mappings.append(mapping)

    def harmonize(self, df: pd.DataFrame, patient_id_column: str = "record_id") -> dict[str, pd.DataFrame]:
        """Apply all mappings to produce harmonized DataFrames.

        Args:
            df: Source DataFrame with original column names.
            patient_id_column: Column containing patient identifiers.

        Returns:
            Dictionary mapping category names to harmonized DataFrames.
        """
        # Group mappings by category
        by_category = {}
        for m in self.mappings:
            by_category.setdefault(m.target_category, []).append(m)

        results = {}
        for category, category_mappings in by_category.items():
            available = set(df.columns)
            valid_mappings = [m for m in category_mappings if m.source_column in available]
            if not valid_mappings:
                logger.warning("Category '%s': no valid source columns found, skipping", category)
                continue

            harmonized = pd.DataFrame()
            harmonized[patient_id_column] = df[patient_id_column].copy()
            harmonized["source"] = "structured"

            for m in valid_mappings:
                col_data = df[m.source_column].copy()
                if m.value_map:
                    col_data = col_data.map(m.value_map).fillna(col_data)
                if m.transform:
                    col_data = _apply_transform(col_data, m.transform)
                harmonized[m.target_field] = col_data

            results[category] = harmonized
            logger.info("Category '%s': harmonized %d columns, %d rows", category, len(valid_mappings), len(harmonized))

        return results

    def harmonize_file(self, filepath: str, patient_id_column: str = "record_id") -> dict[str, pd.DataFrame]:
        """Harmonize a CSV or parquet file."""
        path = Path(filepath)
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, low_memory=False)
        return self.harmonize(df, patient_id_column)

    def describe_mappings(self) -> str:
        """Return human-readable description of all mappings."""
        lines = ["Field Mappings:"]
        by_cat = {}
        for m in self.mappings:
            by_cat.setdefault(m.target_category, []).append(m)
        for cat, maps in sorted(by_cat.items()):
            lines.append("\n  " + cat + ":")
            for m in maps:
                line = "    " + m.source_column + " -> " + m.target_field
                if m.transform:
                    line += " (transform: " + m.transform + ")"
                if m.value_map:
                    line += " (value_map: " + str(len(m.value_map)) + " entries)"
                lines.append(line)
        return "\n".join(lines)


def _apply_transform(series: pd.Series, transform: str) -> pd.Series:
    """Apply a named transform to a pandas Series."""
    if transform == "lowercase":
        return series.astype(str).str.lower()
    elif transform == "uppercase":
        return series.astype(str).str.upper()
    elif transform == "strip":
        return series.astype(str).str.strip()
    elif transform == "date_to_yyyy_mm_dd":
        return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")
    elif transform == "to_string":
        return series.astype(str)
    elif transform == "to_numeric":
        return pd.to_numeric(series, errors="coerce")
    else:
        logger.warning("Unknown transform: %s", transform)
        return series
