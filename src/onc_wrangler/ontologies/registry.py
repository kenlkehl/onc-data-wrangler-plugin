"""
Ontology Registry

Discovers and loads ontologies from ``data/ontologies/*/ontology.yaml``.
Each subdirectory that contains an ``ontology.yaml`` file is treated as a
registered ontology.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .base import (
    DataCategory,
    DataItem,
    OntologyBase,
    ValidValue,
    _parse_category,
)

logger = logging.getLogger(__name__)

# Resolve data directory relative to the plugin root:
#   src/onc_wrangler/ontologies/registry.py -> ../../../../data/ontologies
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "ontologies"


# ---------------------------------------------------------------------------
# Concrete YAML-backed ontology
# ---------------------------------------------------------------------------

class YAMLOntology(OntologyBase):
    """An ontology loaded entirely from a YAML data file."""

    def __init__(self, yaml_path: Path) -> None:
        self._yaml_path = yaml_path
        self._load_from_yaml(yaml_path)

    @property
    def ontology_id(self) -> str:
        return self._meta.get("id", self._yaml_path.parent.name)

    @property
    def data_dir(self) -> Path:
        """Directory containing this ontology's data files."""
        return self._yaml_path.parent


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class OntologyRegistry:
    """Discovers and provides access to all available ontologies.

    Usage::

        registry = OntologyRegistry()
        registry.discover()

        naaccr = registry.get("naaccr")
        for ont in registry.list_ontologies():
            print(ont.ontology_id, ont.display_name)
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or DATA_DIR
        self._ontologies: Dict[str, YAMLOntology] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> int:
        """Scan the data directory for ontology YAML files.

        Returns the number of ontologies discovered.
        """
        if not self._data_dir.is_dir():
            logger.warning("Ontology data directory not found: %s", self._data_dir)
            return 0

        count = 0
        for subdir in sorted(self._data_dir.iterdir()):
            if not subdir.is_dir():
                continue
            yaml_path = subdir / "ontology.yaml"
            if not yaml_path.exists():
                continue

            try:
                ont = YAMLOntology(yaml_path)
                self._ontologies[ont.ontology_id] = ont
                count += 1
                logger.debug("Discovered ontology: %s", ont.ontology_id)
            except Exception:
                logger.exception("Failed to load ontology from %s", yaml_path)

        logger.info(
            "Ontology registry: discovered %d ontologies in %s",
            count,
            self._data_dir,
        )
        return count

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get(self, ontology_id: str) -> Optional[YAMLOntology]:
        """Get an ontology by its id, or None if not found."""
        return self._ontologies.get(ontology_id)

    def __getitem__(self, ontology_id: str) -> YAMLOntology:
        """Get an ontology by id, raising KeyError if not found."""
        return self._ontologies[ontology_id]

    def __contains__(self, ontology_id: str) -> bool:
        return ontology_id in self._ontologies

    def list_ontologies(self) -> List[YAMLOntology]:
        """Return all discovered ontologies, sorted by id."""
        return sorted(self._ontologies.values(), key=lambda o: o.ontology_id)

    def list_ids(self) -> List[str]:
        """Return sorted list of ontology ids."""
        return sorted(self._ontologies.keys())

    @property
    def count(self) -> int:
        return len(self._ontologies)

    def __repr__(self) -> str:
        return f"OntologyRegistry(count={self.count}, dir='{self._data_dir}')"
