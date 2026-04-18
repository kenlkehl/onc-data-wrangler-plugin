"""Core data types and merge logic for ontology-driven extraction.

Provides :class:`ExtractionResult` (the unit of extracted data) and
:func:`merge_results` (higher-confidence-wins merging used across chunks).

Generalized from the NAACCR registry pipeline to work with any ontology.
Field identification uses string ``field_id`` (NAACCR uses ``str(item_number)``,
other ontologies use their own string identifiers).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Protocol, runtime_checkable
import json
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chunk protocol -- satisfied by any chunker implementation
# ---------------------------------------------------------------------------

@runtime_checkable
class Chunk(Protocol):
    """Minimal interface expected from a document chunk."""

    @property
    def chunk_id(self) -> str: ...

    @property
    def chunk_type(self) -> str: ...

    @property
    def text(self) -> str: ...

    @property
    def document_date(self) -> str: ...


# ---------------------------------------------------------------------------
# Extraction result
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """The outcome of extracting a single data item from a chunk.

    Works with any ontology -- ``field_id`` is a string identifier.
    For NAACCR, ``field_id`` is ``str(item_number)`` (e.g. ``"400"``).
    For other ontologies, it is the ontology-specific field identifier.
    """

    field_id: str              # ontology-specific field identifier
    field_name: str            # human-readable field name
    extracted_value: str       # raw LLM output
    resolved_code: str         # after code resolution
    confidence: float          # 0.0-1.0
    evidence_text: str         # quoted text supporting the extraction
    source_chunk_id: str       # which chunk this came from
    source_chunk_type: str     # chunk type
    pass_number: int           # chunk index (round number) that produced this
    ontology_id: str = ""      # which ontology this field belongs to
    tumor_index: int = 0       # which diagnosis this belongs to (0-based)

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON checkpointing."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExtractionResult":
        """Deserialize from a plain dict."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HIGH_CONFIDENCE_THRESHOLD = 0.9


# ---------------------------------------------------------------------------
# Result merging
# ---------------------------------------------------------------------------

def merge_results(
    existing: dict[str, ExtractionResult],
    new_results: list[ExtractionResult],
) -> dict[str, ExtractionResult]:
    """Merge *new_results* into *existing*.  Higher confidence wins."""
    merged = dict(existing)

    for result in new_results:
        fid = result.field_id
        current = merged.get(fid)

        if current is None:
            merged[fid] = result
            continue

        if result.confidence > current.confidence:
            merged[fid] = result

    return merged


# Type alias for multi-diagnosis state: (tumor_index, field_id) -> result
MultiDiagnosisState = dict[tuple[int, str], ExtractionResult]


def merge_results_multi(
    existing: MultiDiagnosisState,
    new_results: list[ExtractionResult],
) -> MultiDiagnosisState:
    """Merge *new_results* into *existing* keyed by ``(tumor_index, field_id)``.

    Higher confidence wins per ``(tumor_index, field_id)`` pair.
    """
    merged = dict(existing)

    for result in new_results:
        key = (result.tumor_index, result.field_id)
        current = merged.get(key)

        if current is None or result.confidence > current.confidence:
            merged[key] = result

    return merged


# ---------------------------------------------------------------------------
# Batching helper
# ---------------------------------------------------------------------------

def split_items_into_batches(
    items: list[Any], items_per_call: int
) -> list[list[Any]]:
    """Partition *items* into sub-lists of at most *items_per_call*."""
    if items_per_call <= 0:
        return [items]
    return [
        items[i : i + items_per_call]
        for i in range(0, len(items), items_per_call)
    ]


# ---------------------------------------------------------------------------
# Serialization helpers for checkpointing
# ---------------------------------------------------------------------------

def serialize_extraction_state(
    state: dict[str, ExtractionResult],
) -> str:
    """Serialize extraction state to JSON string."""
    return json.dumps(
        {k: v.to_dict() for k, v in state.items()},
        indent=2,
    )


def deserialize_extraction_state(
    data: str,
) -> dict[str, ExtractionResult]:
    """Deserialize extraction state from JSON string."""
    raw = json.loads(data)
    return {
        k: ExtractionResult.from_dict(v)
        for k, v in raw.items()
    }
