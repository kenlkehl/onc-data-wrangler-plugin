"""ICD-O-3 reference lookup for diagnosis discovery code resolution.

Loads topography and morphology reference data from icdo3_reference.yaml
and provides keyword-based narrowing to inject relevant code subsets into
LLM prompts.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_REFERENCE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "ontologies"
    / "naaccr"
    / "icdo3_reference.yaml"
)

# Suffixes to strip when normalizing plain-language descriptions
_STRIP_SUFFIXES = re.compile(
    r"\b(cancer|carcinoma|tumor|tumour|neoplasm|malignancy|malignant)\b",
    re.IGNORECASE,
)

# Generic fallback codes when no keyword match is found
_GENERIC_TOPOGRAPHY = [
    ("C76.0", "Head, face or neck, NOS"),
    ("C76.1", "Thorax, NOS"),
    ("C76.2", "Abdomen, NOS"),
    ("C76.3", "Pelvis, NOS"),
    ("C80.9", "Unknown primary site"),
]

_GENERIC_MORPHOLOGY = [
    ("8000", "Neoplasm, malignant"),
    ("8010", "Carcinoma, NOS"),
    ("8140", "Adenocarcinoma, NOS"),
    ("8070", "Squamous cell carcinoma, NOS"),
    ("8046", "Non-small cell carcinoma"),
    ("8041", "Small cell carcinoma, NOS"),
    ("8800", "Sarcoma, NOS"),
    ("9590", "Malignant lymphoma, NOS"),
]


class ICDO3Reference:
    """Loads and queries ICD-O-3 reference data for code resolution prompts."""

    def __init__(self, reference_path: Optional[Path] = None) -> None:
        self._path = reference_path or _DEFAULT_REFERENCE_PATH
        self._topography_groups: dict[str, dict] = {}
        self._morphology_groups: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("ICD-O-3 reference file not found: %s", self._path)
            return
        with open(self._path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self._topography_groups = data.get("topography", {})
        self._morphology_groups = data.get("morphology", {})
        logger.info(
            "ICDO3Reference loaded: %d topography groups, %d morphology groups",
            len(self._topography_groups),
            len(self._morphology_groups),
        )

    def get_topography_for_site(
        self, site_description: str
    ) -> list[tuple[str, str]]:
        """Return (code, description) pairs for topography codes matching a
        plain-language site description like 'lung' or 'left breast'.

        Uses keyword matching against each group's keywords list. Falls back
        to rapidfuzz partial matching, then generic codes.
        """
        normalized = _normalize(site_description)
        matched = self._match_topography_groups(normalized)
        if not matched:
            matched = self._fuzzy_match_topography(normalized)
        if not matched:
            return list(_GENERIC_TOPOGRAPHY)
        return matched

    def get_morphology_for_histology(
        self, histology_description: str
    ) -> list[tuple[str, str]]:
        """Return (code, description) pairs for morphology codes matching a
        plain-language histology description like 'adenocarcinoma'.

        Uses keyword matching, then rapidfuzz fallback, then generic codes.
        """
        normalized = _normalize(histology_description)
        matched = self._match_morphology_groups(normalized)
        if not matched:
            matched = self._fuzzy_match_morphology(normalized)
        if not matched:
            return list(_GENERIC_MORPHOLOGY)
        return matched

    def format_reference_block(
        self, site_description: str, histology_description: str
    ) -> tuple[str, str]:
        """Return formatted (topography_block, morphology_block) strings
        ready for prompt injection.
        """
        topo = self.get_topography_for_site(site_description)
        morph = self.get_morphology_for_histology(histology_description)
        return (
            _format_code_list(topo),
            _format_code_list(morph),
        )

    def get_all_topography_for_descriptions(
        self, site_descriptions: list[str]
    ) -> list[tuple[str, str]]:
        """Combine topography codes for multiple site descriptions,
        deduplicated and sorted."""
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for desc in site_descriptions:
            for code, label in self.get_topography_for_site(desc):
                if code not in seen:
                    seen.add(code)
                    result.append((code, label))
        return sorted(result, key=lambda x: x[0])

    def get_all_morphology_for_descriptions(
        self, histology_descriptions: list[str]
    ) -> list[tuple[str, str]]:
        """Combine morphology codes for multiple histology descriptions,
        deduplicated and sorted."""
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for desc in histology_descriptions:
            for code, label in self.get_morphology_for_histology(desc):
                if code not in seen:
                    seen.add(code)
                    result.append((code, label))
        return sorted(result, key=lambda x: x[0])

    # ------------------------------------------------------------------
    # Internal matching
    # ------------------------------------------------------------------

    def _match_topography_groups(
        self, normalized: str
    ) -> list[tuple[str, str]]:
        """Keyword-based matching against topography groups."""
        results: list[tuple[str, str]] = []
        for _group_id, group in self._topography_groups.items():
            keywords = group.get("keywords", [])
            if any(kw in normalized for kw in keywords):
                results.extend(_extract_topography_codes(group))
        return results

    def _match_morphology_groups(
        self, normalized: str
    ) -> list[tuple[str, str]]:
        """Keyword-based matching against morphology groups."""
        results: list[tuple[str, str]] = []
        for _group_id, group in self._morphology_groups.items():
            keywords = group.get("keywords", [])
            if any(kw in normalized for kw in keywords):
                results.extend(_extract_morphology_codes(group))
        return results

    def _fuzzy_match_topography(
        self, normalized: str
    ) -> list[tuple[str, str]]:
        """Fallback fuzzy matching using rapidfuzz."""
        try:
            from rapidfuzz import fuzz
        except ImportError:
            return []

        best_score = 0.0
        best_group = None
        for _group_id, group in self._topography_groups.items():
            for kw in group.get("keywords", []):
                score = fuzz.partial_ratio(normalized, kw)
                if score > best_score:
                    best_score = score
                    best_group = group
        if best_group and best_score >= 60:
            return _extract_topography_codes(best_group)
        return []

    def _fuzzy_match_morphology(
        self, normalized: str
    ) -> list[tuple[str, str]]:
        """Fallback fuzzy matching using rapidfuzz."""
        try:
            from rapidfuzz import fuzz
        except ImportError:
            return []

        best_score = 0.0
        best_group = None
        for _group_id, group in self._morphology_groups.items():
            for kw in group.get("keywords", []):
                score = fuzz.partial_ratio(normalized, kw)
                if score > best_score:
                    best_score = score
                    best_group = group
        if best_group and best_score >= 60:
            return _extract_morphology_codes(best_group)
        return []


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Normalize a plain-language description for keyword matching."""
    text = text.lower().strip()
    text = _STRIP_SUFFIXES.sub("", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_topography_codes(group: dict) -> list[tuple[str, str]]:
    """Extract all (code, description) pairs from a topography group."""
    results: list[tuple[str, str]] = []
    for _site_code, site_data in group.get("sites", {}).items():
        for code, desc in site_data.get("subsites", {}).items():
            results.append((str(code), str(desc)))
    return results


def _extract_morphology_codes(group: dict) -> list[tuple[str, str]]:
    """Extract all (code, description) pairs from a morphology group."""
    results: list[tuple[str, str]] = []
    for code, desc in group.get("codes", {}).items():
        results.append((str(code), str(desc)))
    return results


def _format_code_list(codes: list[tuple[str, str]]) -> str:
    """Format code list for prompt injection, one per line."""
    if not codes:
        return "(no reference codes available)"
    return "\n".join(f"  {code} = {desc}" for code, desc in codes)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_singleton: Optional[ICDO3Reference] = None


def get_icdo3_reference(
    reference_path: Optional[Path] = None,
) -> ICDO3Reference:
    """Return a cached ICDO3Reference singleton."""
    global _singleton
    if _singleton is None:
        _singleton = ICDO3Reference(reference_path)
    return _singleton
