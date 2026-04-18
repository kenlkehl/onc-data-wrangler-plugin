"""Audit trail, review queue, and confidence scoring for extraction results.

Ported from the registry extraction pipeline's ``audit_trail.py``,
``review_queue.py``, and ``confidence.py``.  Generalized to work with
any ontology via string-based ``field_id`` (not NAACCR-specific
integer item numbers).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional

from .result import ExtractionResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
}

VALID_PRIORITIES = frozenset(_PRIORITY_ORDER)


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """A single provenance record for one extracted field."""

    patient_id: str
    tumor_index: int
    field_id: str
    field_name: str
    extracted_value: str
    resolved_code: str
    confidence: float
    evidence_text: str
    source_chunk_id: str
    pass_number: int
    ontology_id: str


class AuditTrail:
    """Collects per-item provenance records from :class:`ExtractionResult`
    objects and exports them to CSV.

    Usage::

        trail = AuditTrail()
        for fid, result in results.items():
            trail.add_result(result, patient_id="P001", tumor_index=0)
        trail.export_csv(Path("audit.csv"))
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []

    # -- recording ---------------------------------------------------------

    def add_result(
        self,
        result: ExtractionResult,
        patient_id: str,
        tumor_index: int = 0,
    ) -> None:
        """Create an audit entry from an :class:`ExtractionResult`."""
        self._entries.append({
            "patient_id": patient_id,
            "tumor_index": tumor_index,
            "field_id": result.field_id,
            "field_name": result.field_name,
            "extracted_value": result.extracted_value,
            "resolved_code": result.resolved_code,
            "confidence": result.confidence,
            "evidence_text": (result.evidence_text or "")[:500],
            "source_chunk_id": result.source_chunk_id,
            "pass_number": result.pass_number,
            "ontology_id": result.ontology_id,
        })

    # -- export ------------------------------------------------------------

    _CSV_COLUMNS = [
        "patient_id",
        "tumor_index",
        "field_id",
        "field_name",
        "extracted_value",
        "resolved_code",
        "confidence",
        "evidence_text",
        "source_chunk_id",
        "pass_number",
        "ontology_id",
    ]

    def export_csv(self, path: Path) -> None:
        """Write all audit entries to *path* as CSV."""
        if not self._entries:
            logger.info("No audit entries to write.")
            return

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self._CSV_COLUMNS)
            writer.writeheader()
            for entry in self._entries:
                writer.writerow(entry)

        logger.info(
            "Audit trail written to %s (%d entries)", path, len(self._entries)
        )

    # -- accessors ---------------------------------------------------------

    @property
    def entries(self) -> list[dict]:
        """Return a shallow copy of all entries."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Review item
# ---------------------------------------------------------------------------

@dataclass
class ReviewItem:
    """A single item flagged for human review."""

    patient_id: str
    field_id: str
    field_name: str
    extracted_value: str
    resolved_code: str
    confidence: float
    priority: str           # CRITICAL / HIGH / MEDIUM / LOW
    reason: str
    evidence_text: str
    source_chunk_id: str
    ontology_id: str


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

class ReviewQueue:
    """Collects :class:`ReviewItem` instances flagged for human review
    and exports a sorted worklist.

    Usage::

        queue = ReviewQueue()
        queue.flag_for_review(result, "HIGH", "Low confidence", "P001")
        queue.export_csv(Path("review.csv"))
    """

    def __init__(self) -> None:
        self._items: list[ReviewItem] = []

    # -- flagging ----------------------------------------------------------

    def flag_for_review(
        self,
        result: ExtractionResult,
        priority: str,
        reason: str,
        patient_id: str,
    ) -> None:
        """Flag an :class:`ExtractionResult` for human review.

        Parameters
        ----------
        result:
            The extraction result to flag.
        priority:
            One of ``CRITICAL``, ``HIGH``, ``MEDIUM``, ``LOW``.
        reason:
            Human-readable reason for flagging.
        patient_id:
            Patient identifier.
        """
        priority = priority.upper()
        if priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority {priority!r}; "
                f"expected one of {sorted(VALID_PRIORITIES)}"
            )

        self._items.append(ReviewItem(
            patient_id=patient_id,
            field_id=result.field_id,
            field_name=result.field_name,
            extracted_value=result.extracted_value,
            resolved_code=result.resolved_code,
            confidence=result.confidence,
            priority=priority,
            reason=reason,
            evidence_text=(result.evidence_text or "")[:500],
            source_chunk_id=result.source_chunk_id,
            ontology_id=result.ontology_id,
        ))

    def add_items(self, items: list[ReviewItem]) -> None:
        """Append pre-built review items (e.g. from :class:`ConfidenceScorer`)."""
        self._items.extend(items)

    # -- querying ----------------------------------------------------------

    def get_flagged(self, priority: str | None = None) -> list[ReviewItem]:
        """Return flagged items, optionally filtered by *priority*.

        Results are sorted by priority (CRITICAL first) then confidence
        ascending (least confident first).
        """
        if priority is not None:
            priority = priority.upper()
            items = [i for i in self._items if i.priority == priority]
        else:
            items = list(self._items)

        items.sort(
            key=lambda ri: (
                _PRIORITY_ORDER.get(ri.priority, 99),
                ri.confidence,
            )
        )
        return items

    # -- export ------------------------------------------------------------

    _CSV_COLUMNS = [f.name for f in fields(ReviewItem)]

    def export_csv(self, path: Path) -> None:
        """Write the review queue to *path*, sorted by priority."""
        if not self._items:
            logger.info("No review items to write.")
            return

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        sorted_items = self.get_flagged()

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self._CSV_COLUMNS)
            writer.writeheader()
            for item in sorted_items:
                writer.writerow({
                    f.name: getattr(item, f.name) for f in fields(item)
                })

        logger.info(
            "Review queue written to %s (%d items)", path, len(self._items)
        )

    # -- accessors ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self._items)


# ---------------------------------------------------------------------------
# Confidence scorer
# ---------------------------------------------------------------------------

class ConfidenceScorer:
    """Score extraction results by confidence and flag items for review.

    Ported from the registry pipeline's NAACCR-specific scorer.  This
    version uses string ``field_id`` values and configurable field sets
    rather than hard-coded NAACCR item numbers.

    Default field sets use NAACCR item numbers as strings for backward
    compatibility, but any ontology's field identifiers can be used via
    the constructor.
    """

    # Default critical fields (primary site, histology, sex)
    DEFAULT_CRITICAL_FIELDS: set[str] = {"400", "522", "220"}

    # Default required fields (broader set -- demographics, staging, treatment)
    DEFAULT_REQUIRED_FIELDS: set[str] = {
        "400",   # Primary Site
        "522",   # Histologic Type ICD-O-3
        "523",   # Behavior Code ICD-O-3
        "220",   # Sex
        "230",   # Age at Diagnosis
        "390",   # Date of Diagnosis
        "410",   # Laterality
        "490",   # Diagnostic Confirmation
        "764",   # Summary Stage 2018
        "1290",  # RX Summ--Surg Prim Site
        "1360",  # RX Summ--Radiation
        "1390",  # RX Summ--Chemo
        "1760",  # Vital Status
    }

    # Thresholds
    CRITICAL_THRESHOLD = 0.9
    HIGH_THRESHOLD = 0.7
    LOW_THRESHOLD = 0.5

    def __init__(
        self,
        critical_fields: set[str] | None = None,
        required_fields: set[str] | None = None,
    ) -> None:
        self._critical = (
            critical_fields
            if critical_fields is not None
            else self.DEFAULT_CRITICAL_FIELDS
        )
        self._required = (
            required_fields
            if required_fields is not None
            else self.DEFAULT_REQUIRED_FIELDS
        )

    def score_extraction(
        self,
        results: dict[str, ExtractionResult],
        patient_id: str = "",
    ) -> list[ReviewItem]:
        """Score all results and return items that need review.

        Parameters
        ----------
        results:
            Mapping of ``field_id`` -> :class:`ExtractionResult`.
        patient_id:
            Patient identifier attached to each :class:`ReviewItem`.

        Returns
        -------
        list[ReviewItem]
            Items needing review, sorted by priority then confidence.

        Flagging rules
        --------------
        - **CRITICAL**: Fields in ``critical_fields`` (primary site,
          histology, sex by default) with confidence < 0.9.
        - **HIGH**: Fields in ``required_fields`` with confidence < 0.7.
        - **LOW**: Any field with confidence < 0.5.
        """
        review_items: list[ReviewItem] = []

        for field_id, result in results.items():
            conf = result.confidence if result.confidence is not None else 0.0

            priority: Optional[str] = None
            reason: Optional[str] = None

            # CRITICAL: key variables below threshold
            if field_id in self._critical and conf < self.CRITICAL_THRESHOLD:
                priority = "CRITICAL"
                reason = (
                    f"Critical field with confidence {conf:.2f} "
                    f"< {self.CRITICAL_THRESHOLD} threshold"
                )

            # HIGH: required fields below threshold
            elif field_id in self._required and conf < self.HIGH_THRESHOLD:
                priority = "HIGH"
                reason = (
                    f"Required field with confidence {conf:.2f} "
                    f"< {self.HIGH_THRESHOLD} threshold"
                )

            # LOW: any field with very low confidence
            elif conf < self.LOW_THRESHOLD:
                priority = "LOW"
                reason = (
                    f"Low confidence {conf:.2f} "
                    f"< {self.LOW_THRESHOLD} threshold"
                )

            if priority is not None and reason is not None:
                review_items.append(ReviewItem(
                    patient_id=patient_id,
                    field_id=result.field_id,
                    field_name=result.field_name,
                    extracted_value=result.extracted_value,
                    resolved_code=result.resolved_code,
                    confidence=conf,
                    priority=priority,
                    reason=reason,
                    evidence_text=(result.evidence_text or "")[:500],
                    source_chunk_id=result.source_chunk_id,
                    ontology_id=result.ontology_id,
                ))

        # Sort: priority order first, then confidence ascending
        review_items.sort(
            key=lambda ri: (
                _PRIORITY_ORDER.get(ri.priority, 99),
                ri.confidence,
            )
        )

        return review_items
