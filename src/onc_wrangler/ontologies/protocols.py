"""Protocol interfaces for dictionary-driven extraction.

These protocols generalize the NAACCR registry pipeline's dictionary, code
resolver, and schema resolver patterns so they work with any ontology.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Dictionary item protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class DictionaryItemLike(Protocol):
    """Minimal interface expected from a data dictionary item."""

    @property
    def field_id(self) -> str:
        """Unique identifier for this item within its ontology."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name."""
        ...

    @property
    def prompt_field_name(self) -> str:
        """Field name to use in LLM prompts and JSON output."""
        ...

    @property
    def length(self) -> int:
        """Maximum character length (0 = unlimited)."""
        ...

    @property
    def data_type(self) -> str:
        """Data type: string, integer, date, digits, text, etc."""
        ...

    @property
    def description(self) -> str:
        """Description of this item for LLM context."""
        ...

    @property
    def allowable_values(self) -> str:
        """Free-text description of allowable values, if any."""
        ...


# ---------------------------------------------------------------------------
# Code resolver protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class CodeResolverLike(Protocol):
    """Interface for resolving LLM free-text output to valid codes."""

    def resolve(self, field_id: str, llm_output: str) -> tuple[str, float]:
        """Resolve LLM output to a valid code.

        Returns (resolved_code, confidence) where confidence is 0.0-1.0.
        If no valid code is found, returns (llm_output, 0.0).
        """
        ...

    def get_valid_codes_prompt(self, field_id: str) -> str:
        """Return a human-readable string of valid codes for prompt injection."""
        ...

    def has_codes(self, field_id: str) -> bool:
        """Whether a code table exists for this field."""
        ...


# ---------------------------------------------------------------------------
# Schema resolver protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class SchemaResolverLike(Protocol):
    """Interface for resolving extracted context to a cancer schema."""

    def resolve_schema(self, context: dict[str, str]) -> str:
        """Determine schema from extraction context (e.g. site + histology)."""
        ...

    def get_schema_items(self, schema: str) -> list[str]:
        """Return field_ids that are relevant for the given schema."""
        ...

    def get_schema_context(self, schema: str) -> str:
        """Return site-specific extraction guidance for prompts."""
        ...


# ---------------------------------------------------------------------------
# Domain group dataclass
# ---------------------------------------------------------------------------

@dataclass
class DomainGroup:
    """A group of fields to extract together in a single LLM phase.

    Domain groups are processed sequentially to respect data dependencies
    (e.g., demographics before staging, since staging items depend on
    primary site and histology).
    """

    group_id: str
    name: str
    field_ids: list[str]
    system_prompt_template: str
    depends_on: list[str] = field(default_factory=list)
    context_keys: list[str] = field(default_factory=list)
    is_narrative: bool = False
    dynamic: bool = False  # True if field_ids are determined at runtime (e.g. staging)
    multi_instance: bool = False  # True for categories with multiple rows (e.g. regimens)
