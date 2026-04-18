"""
Ontology subsystem for onc-data-wrangler-plugin.

Provides YAML-driven ontology definitions and a registry for discovery.
"""

from .base import DataCategory, DataItem, OntologyBase, ValidValue
from .registry import OntologyRegistry, YAMLOntology

__all__ = [
    "DataCategory",
    "DataItem",
    "OntologyBase",
    "OntologyRegistry",
    "ValidValue",
    "YAMLOntology",
]
