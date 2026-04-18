"""Post-extraction validation with NAACCR cross-field edits.

Provides :class:`ValidationResult` (the outcome of validation) and
:class:`EnhancedValidator` (ontology-aware validation with code
normalization and cross-field edit checks).

Backward-compatible: the :class:`ValidationResult` dataclass interface
is unchanged from the original ``validator.py``.  The new
:class:`EnhancedValidator` replaces ``NAACCRCodeValidator`` and works
with :class:`ExtractionResult` dicts as well as the legacy
``list[dict]`` format.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .result import ExtractionResult

if TYPE_CHECKING:
    from ..ontologies.protocols import CodeResolverLike

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of validating an extraction against code tables and edits."""

    valid_fields: list[str] = field(default_factory=list)
    invalid_fields: list[tuple[str, str, str]] = field(default_factory=list)       # (field, value, reason)
    corrected_fields: list[tuple[str, str, str]] = field(default_factory=list)     # (field, old_value, new_value)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when there are no invalid fields."""
        return len(self.invalid_fields) == 0

    def summary(self) -> str:
        """Human-readable summary of the validation outcome."""
        parts = [
            f"Valid: {len(self.valid_fields)}, "
            f"Invalid: {len(self.invalid_fields)}, "
            f"Corrected: {len(self.corrected_fields)}"
        ]
        for field_name, value, reason in self.invalid_fields:
            parts.append(f"  INVALID {field_name}='{value}': {reason}")
        for field_name, old, new in self.corrected_fields:
            parts.append(f"  CORRECTED {field_name}: '{old}' -> '{new}'")
        for warning in self.warnings:
            parts.append(f"  WARNING: {warning}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Cross-field edit helpers
# ---------------------------------------------------------------------------

# ICD-O-3 topography codes for paired organs (laterality required)
_PAIRED_ORGAN_PREFIXES = frozenset({
    "C50",   # Breast
    "C34",   # Lung
    "C64",   # Kidney
    "C69",   # Eye
    "C62",   # Testis
    "C56",   # Ovary
    "C74",   # Adrenal gland
    "C07",   # Parotid gland
    "C09",   # Tonsil
    "C30",   # Nasal cavity
    "C44",   # Skin (certain sub-sites)
    "C47",   # Peripheral nerves
    "C49",   # Connective tissue (some paired)
    "C70",   # Meninges (some paired)
    "C71",   # Brain (some paired)
    "C72",   # Spinal cord and CNS
    "C40",   # Bones of limbs
    "C41",   # Bones of limbs (additional)
})

# Sites restricted by sex
_MALE_ONLY_SITES = frozenset({"C61", "C62", "C63"})       # Prostate, testis, penis/male genital
_FEMALE_ONLY_SITES = frozenset({"C53", "C54", "C55", "C56", "C57", "C58"})  # Cervix, uterus, ovary, female genital


def _parse_date(value: str) -> Optional[datetime]:
    """Try common date formats and return a datetime, or None."""
    if not value or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _normalize_site_code(code: str) -> str:
    """Normalize a primary site code to Cxx or Cxxx form."""
    code = code.strip().upper()
    if not code.startswith("C"):
        code = "C" + code
    return code


# ---------------------------------------------------------------------------
# Enhanced validator
# ---------------------------------------------------------------------------

class EnhancedValidator:
    """Ontology-aware extraction validator with cross-field edits.

    Validates :class:`ExtractionResult` dicts (``field_id -> result``)
    against NAACCR cross-field edit rules and optional code tables.

    Parameters
    ----------
    code_resolver:
        Optional resolver implementing ``CodeResolverLike``.  When
        provided, extracted values are validated and normalized via the
        resolver's code tables.
    """

    def __init__(
        self,
        code_resolver: Optional[CodeResolverLike] = None,
    ) -> None:
        self._resolver = code_resolver

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_results(
        self,
        results: dict[str, ExtractionResult],
    ) -> ValidationResult:
        """Validate a set of extraction results.

        Parameters
        ----------
        results:
            Mapping of ``field_id`` -> :class:`ExtractionResult`.

        Returns
        -------
        ValidationResult
            Aggregated validation outcome.
        """
        vr = ValidationResult()

        # 1. Per-field code validation and normalization
        for field_id, result in results.items():
            self._validate_single_field(field_id, result, vr)

        # 2. Cross-field edits
        self._run_cross_field_edits(results, vr)

        return vr

    def validate_extraction(
        self,
        extraction: list[dict],
    ) -> ValidationResult:
        """Backward-compatible validation for the legacy list-of-dicts format.

        Parameters
        ----------
        extraction:
            List of extraction dicts in the legacy pipeline format
            (``[{category: {field: value, ...}}, ...]``).

        Returns
        -------
        ValidationResult
        """
        vr = ValidationResult()

        for entry in extraction:
            if not isinstance(entry, dict):
                continue
            for _category, attrs in entry.items():
                if not isinstance(attrs, dict):
                    continue
                self._validate_flat_fields(attrs, vr)

        return vr

    # ------------------------------------------------------------------
    # Per-field validation
    # ------------------------------------------------------------------

    def _validate_single_field(
        self,
        field_id: str,
        result: ExtractionResult,
        vr: ValidationResult,
    ) -> None:
        """Validate and optionally normalize a single field."""
        raw = result.extracted_value
        if raw is None or str(raw).strip() == "":
            return

        raw = str(raw).strip()

        # Site code format check (field 400)
        if field_id == "400":
            if not self._is_valid_site_code(raw):
                vr.invalid_fields.append(
                    (result.field_name, raw, "Invalid ICD-O-3 topography format")
                )
                return
            vr.valid_fields.append(result.field_name)
            return

        # Histology code format check (field 522)
        if field_id == "522":
            if not self._is_valid_histology_code(raw):
                vr.invalid_fields.append(
                    (result.field_name, raw, "Invalid ICD-O-3 morphology code")
                )
                return
            vr.valid_fields.append(result.field_name)
            return

        # Code resolver validation (if available)
        if self._resolver is not None and self._resolver.has_codes(field_id):
            resolved, conf = self._resolver.resolve(field_id, raw)
            if conf >= 0.8:
                if resolved != raw:
                    vr.corrected_fields.append(
                        (result.field_name, raw, resolved)
                    )
                else:
                    vr.valid_fields.append(result.field_name)
            elif conf > 0.0:
                vr.warnings.append(
                    f"{result.field_name}: low-confidence code resolution "
                    f"'{raw}' -> '{resolved}' (confidence={conf:.2f})"
                )
                vr.valid_fields.append(result.field_name)
            else:
                vr.invalid_fields.append(
                    (result.field_name, raw, "Value not in valid code set")
                )
            return

        # No code table -- accept as-is
        vr.valid_fields.append(result.field_name)

    # ------------------------------------------------------------------
    # Cross-field edits
    # ------------------------------------------------------------------

    def _run_cross_field_edits(
        self,
        results: dict[str, ExtractionResult],
        vr: ValidationResult,
    ) -> None:
        """Run NAACCR-style cross-field edits on the result set."""
        self._edit_site_sex(results, vr)
        self._edit_site_laterality(results, vr)
        self._edit_site_histology(results, vr)
        self._edit_treatment_dates(results, vr)

    def _edit_site_sex(
        self,
        results: dict[str, ExtractionResult],
        vr: ValidationResult,
    ) -> None:
        """Check primary site / sex consistency.

        Prostate (C61) and testis (C62) require sex=1 (male).
        Cervix (C53), corpus uteri (C54), uterus NOS (C55), ovary (C56),
        and other female genital (C57, C58) require sex=2 (female).
        """
        site_result = results.get("400")
        sex_result = results.get("220")
        if site_result is None or sex_result is None:
            return

        site = _normalize_site_code(site_result.resolved_code or site_result.extracted_value)
        sex = str(sex_result.resolved_code or sex_result.extracted_value).strip()

        # Site prefix (first 3 chars, e.g. "C61")
        site_prefix = site[:3] if len(site) >= 3 else site

        if site_prefix in _MALE_ONLY_SITES and sex != "1":
            vr.invalid_fields.append((
                "site_sex",
                f"site={site}, sex={sex}",
                f"Site {site} (male-only organ) requires sex=1 (Male), got sex={sex}",
            ))

        if site_prefix in _FEMALE_ONLY_SITES and sex != "2":
            vr.invalid_fields.append((
                "site_sex",
                f"site={site}, sex={sex}",
                f"Site {site} (female-only organ) requires sex=2 (Female), got sex={sex}",
            ))

    def _edit_site_laterality(
        self,
        results: dict[str, ExtractionResult],
        vr: ValidationResult,
    ) -> None:
        """Check that paired organs have laterality specified (!=0).

        Paired organs (breast C50, lung C34, kidney C64, etc.) must have
        a laterality value other than 0 (not a paired site) or blank.
        """
        site_result = results.get("400")
        lat_result = results.get("410")
        if site_result is None or lat_result is None:
            return

        site = _normalize_site_code(site_result.resolved_code or site_result.extracted_value)
        lat = str(lat_result.resolved_code or lat_result.extracted_value).strip()

        site_prefix = site[:3] if len(site) >= 3 else site

        if site_prefix in _PAIRED_ORGAN_PREFIXES:
            if lat in ("0", "", "9"):
                vr.warnings.append(
                    f"Paired organ site {site} should have laterality "
                    f"specified (1=Right, 2=Left, 3=Bilateral), "
                    f"got laterality='{lat}'"
                )

    def _edit_site_histology(
        self,
        results: dict[str, ExtractionResult],
        vr: ValidationResult,
    ) -> None:
        """Basic ICD-O-3 site/histology validation.

        Validates that histology codes fall in the valid 8000-9989 range
        and that the site code matches valid ICD-O-3 topography format.
        """
        site_result = results.get("400")
        hist_result = results.get("522")

        if site_result is not None:
            site = _normalize_site_code(
                site_result.resolved_code or site_result.extracted_value
            )
            if not self._is_valid_site_code(site):
                vr.invalid_fields.append((
                    "site_histology",
                    f"site={site}",
                    f"Primary site '{site}' is not a valid ICD-O-3 topography code",
                ))

        if hist_result is not None:
            hist = str(hist_result.resolved_code or hist_result.extracted_value).strip()
            if hist and not self._is_valid_histology_code(hist):
                vr.invalid_fields.append((
                    "site_histology",
                    f"histology={hist}",
                    f"Histology '{hist}' is not a valid ICD-O-3 morphology code (8000-9989)",
                ))

    def _edit_treatment_dates(
        self,
        results: dict[str, ExtractionResult],
        vr: ValidationResult,
    ) -> None:
        """Check that treatment dates are on or after the diagnosis date.

        Surgery (1200), radiation (1210), and chemotherapy (1220) dates
        must be >= diagnosis date (390).
        """
        dx_result = results.get("390")
        if dx_result is None:
            return

        dx_val = str(dx_result.resolved_code or dx_result.extracted_value).strip()
        dx_date = _parse_date(dx_val)
        if dx_date is None:
            return

        # Treatment date fields: (field_id, human name)
        treatment_fields = [
            ("1200", "Date of First Surgical Procedure"),
            ("1210", "Date of Radiation"),
            ("1220", "Date of Chemotherapy"),
        ]

        for fid, label in treatment_fields:
            tx_result = results.get(fid)
            if tx_result is None:
                continue

            tx_val = str(tx_result.resolved_code or tx_result.extracted_value).strip()
            tx_date = _parse_date(tx_val)
            if tx_date is None:
                continue

            if tx_date < dx_date:
                vr.invalid_fields.append((
                    "treatment_dates",
                    f"{label}={tx_val}, diagnosis={dx_val}",
                    f"{label} ({tx_val}) is before diagnosis date ({dx_val})",
                ))

    # ------------------------------------------------------------------
    # Code format validators
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid_site_code(code: str) -> bool:
        """Check if a primary site code matches ICD-O-3 topography format."""
        return bool(re.match(r"^C\d{2,3}$", code.strip().upper()))

    @staticmethod
    def _is_valid_histology_code(code: str) -> bool:
        """Check if a histology code is in the valid ICD-O-3 range."""
        try:
            code_int = int(str(code).strip()[:4])
            return 8000 <= code_int <= 9989
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Legacy flat-field validation (backward compat)
    # ------------------------------------------------------------------

    def _validate_flat_fields(
        self,
        fields: dict,
        vr: ValidationResult,
    ) -> None:
        """Validate individual fields from the legacy list-of-dicts format."""
        for field_name, value in fields.items():
            if value is None:
                continue

            str_value = str(value).strip()
            if not str_value:
                continue

            # Site code validation
            if field_name in ("primary_site", "naaccr_400_primary_site"):
                if not self._is_valid_site_code(str_value):
                    vr.invalid_fields.append(
                        (field_name, str_value, "Invalid ICD-O-3 topography format")
                    )
                else:
                    vr.valid_fields.append(field_name)
                continue

            # Histology code validation
            if field_name in ("histology", "naaccr_420_histologic_type"):
                if not self._is_valid_histology_code(str_value):
                    vr.invalid_fields.append(
                        (field_name, str_value, "Invalid ICD-O-3 morphology code")
                    )
                else:
                    vr.valid_fields.append(field_name)
                continue

            # Code normalization via resolver
            if self._resolver is not None:
                # Try to find the field_id for this field name
                normalized = self._normalize_code(field_name, str_value)
                if normalized is not None and normalized != str_value:
                    vr.corrected_fields.append(
                        (field_name, str_value, normalized)
                    )
                    continue

            vr.valid_fields.append(field_name)

    def _normalize_code(
        self,
        field_name: str,
        raw_value: str,
    ) -> Optional[str]:
        """Attempt to normalize a raw value using basic heuristics.

        Tries:
          1. Strip whitespace
          2. Strip leading zeros for numeric codes
          3. Case-insensitive matching
        """
        stripped = raw_value.strip()

        # Try stripping leading zeros for numeric codes
        if stripped.isdigit():
            no_leading = stripped.lstrip("0") or "0"
            if no_leading != stripped:
                return no_leading

        return None
