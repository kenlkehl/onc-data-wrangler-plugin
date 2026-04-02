"""
Ontology Base Classes (YAML-driven)

Provides dataclasses and an abstract base class for loading ontology
definitions from YAML data files instead of hand-coded Python classes.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ValidValue:
    """A single allowed code/value for a data item."""

    code: str
    description: str


@dataclass
class DataItem:
    """Represents a single extractable data element."""

    id: str
    name: str
    description: str
    data_type: str  # string, integer, date, float, code, text
    length: Optional[int] = None
    valid_values: Optional[List[ValidValue]] = None

    # Extended attributes (populated when loading from Python ontologies)
    extraction_hints: List[str] = field(default_factory=list)
    repeatable: bool = False
    required: bool = False
    json_field: Optional[str] = None
    naaccr_item: Optional[str] = None
    human_readable_field: Optional[str] = None
    clinical_significance: Optional[str] = None
    required_for_staging: bool = False


@dataclass
class DataCategory:
    """A group of related data items."""

    id: str
    name: str
    description: str
    items: List[DataItem]
    context: str = ""
    per_diagnosis: bool = False


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------

def _parse_valid_values(raw: list | None) -> list[ValidValue] | None:
    """Parse a list of {code, description} dicts into ValidValue objects."""
    if not raw:
        return None
    return [ValidValue(code=str(v["code"]), description=v.get("description", "")) for v in raw]


def _parse_item(raw: dict) -> DataItem:
    """Parse a single item dict from YAML into a DataItem."""
    return DataItem(
        id=raw["id"],
        name=raw.get("name", raw["id"]),
        description=raw.get("description", ""),
        data_type=raw.get("data_type", "string"),
        length=raw.get("length"),
        valid_values=_parse_valid_values(raw.get("valid_values")),
    )


def _parse_category(raw: dict) -> DataCategory:
    """Parse a single category dict from YAML into a DataCategory."""
    items = [_parse_item(i) for i in raw.get("items", [])]
    return DataCategory(
        id=raw["id"],
        name=raw.get("name", raw["id"]),
        description=raw.get("description", ""),
        items=items,
        per_diagnosis=raw.get("per_diagnosis", False),
    )


# ---------------------------------------------------------------------------
# OntologyBase ABC
# ---------------------------------------------------------------------------

class OntologyBase(ABC):
    """Abstract base class for ontologies.

    Concrete subclasses typically call ``_load_from_yaml()`` in their
    ``__init__`` to populate ``_meta`` and ``_categories`` from the YAML
    data file located at ``data/ontologies/<id>/ontology.yaml``.
    """

    _meta: dict
    _categories: List[DataCategory]

    # ------------------------------------------------------------------
    # Required properties
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def ontology_id(self) -> str:
        ...

    @property
    def display_name(self) -> str:
        return self._meta.get("name", self.ontology_id)

    @property
    def version(self) -> str:
        return self._meta.get("version", "0.0.0")

    @property
    def is_free_text(self) -> bool:
        return self._meta.get("is_free_text", False)

    @property
    def description(self) -> str:
        return self._meta.get("description", self.display_name)

    # ------------------------------------------------------------------
    # Category access
    # ------------------------------------------------------------------

    def get_categories(self) -> List[DataCategory]:
        """Return all categories loaded from the YAML file."""
        return list(self._categories)

    def get_base_items(self) -> List[DataCategory]:
        """Return categories that are NOT per-diagnosis."""
        return [c for c in self._categories if not c.per_diagnosis]

    def get_site_specific_items(self, cancer_type: str) -> List[DataCategory]:
        """Return per-diagnosis categories."""
        return [c for c in self._categories if c.per_diagnosis]

    # ------------------------------------------------------------------
    # YAML loading
    # ------------------------------------------------------------------

    def _load_from_yaml(self, yaml_path: Path) -> None:
        """Load ontology metadata and categories from a YAML file."""
        with open(yaml_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        self._meta = {k: v for k, v in data.items() if k != "categories"}
        self._categories = [_parse_category(c) for c in data.get("categories", [])]
        logger.debug(
            "Loaded ontology %s: %d categories, %d total items",
            self._meta.get("id", "?"),
            len(self._categories),
            sum(len(c.items) for c in self._categories),
        )

    # ------------------------------------------------------------------
    # Template helpers (lightweight defaults)
    # ------------------------------------------------------------------

    def get_empty_summary_template(self) -> Dict[str, Any]:
        return {}

    def get_empty_diagnosis_template(self, cancer_type: str) -> Dict[str, Any]:
        return {}

    def get_supported_cancer_types(self) -> List[str]:
        return []

    def detect_cancer_type(
        self,
        primary_site: str | None = None,
        histology: str | None = None,
        diagnosis_year: int | None = None,
    ) -> str:
        return "generic"

    def get_extraction_context(self) -> str:
        return ""

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        return []

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id='{self.ontology_id}', version='{self.version}')"
