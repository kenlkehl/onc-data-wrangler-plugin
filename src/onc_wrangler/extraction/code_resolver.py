"""Generic code resolver for non-NAACCR ontologies.

Takes a mapping of ``field_id -> {code: description}`` built from
``DataItem.valid_values`` and implements the same 6-tier resolution
strategy as the NAACCR code resolver.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz as _fuzz, process as _process
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False

_RANGE_RE = re.compile(r"^(\d+)\s*[-\u2013]\s*(\d+)$")


class GenericCodeResolver:
    """Map free-text / LLM output to valid codes for any ontology.

    Implements the ``CodeResolverLike`` protocol.

    Parameters
    ----------
    valid_values_map:
        ``{field_id: {code: description}}`` where codes are the valid
        values and descriptions are human-readable labels.
    """

    def __init__(self, valid_values_map: dict[str, dict[str, str]]) -> None:
        self._valid_values = valid_values_map

        # Per-field indexes
        self._code_exact: dict[str, dict[str, str]] = {}   # fid -> {code: desc}
        self._code_lower: dict[str, dict[str, str]] = {}   # fid -> {lower_code: code}
        self._desc_lower: dict[str, dict[str, str]] = {}   # fid -> {lower_desc: code}
        self._desc_list: dict[str, list[tuple[str, str]]] = {}  # fid -> [(lower_desc, code)]

        self._build_indexes()

    def _build_indexes(self) -> None:
        for fid, codes_dict in self._valid_values.items():
            if not codes_dict:
                continue

            exact: dict[str, str] = {}
            lower: dict[str, str] = {}
            desc: dict[str, str] = {}
            desc_pairs: list[tuple[str, str]] = []

            for code, description in codes_dict.items():
                exact[code] = description
                lower[code.lower()] = code
                d = description.lower().strip()
                if d:
                    desc[d] = code
                    desc_pairs.append((d, code))

            self._code_exact[fid] = exact
            self._code_lower[fid] = lower
            self._desc_lower[fid] = desc
            self._desc_list[fid] = desc_pairs

    # ------------------------------------------------------------------
    # CodeResolverLike protocol
    # ------------------------------------------------------------------

    def resolve(self, field_id: str, llm_output: str) -> tuple[str, float]:
        """Resolve LLM output to a valid code.

        Returns ``(resolved_code, confidence)``.
        If the field has no valid_values, returns ``(llm_output, 1.0)``
        (pass-through with full confidence).
        """
        text = llm_output.strip()
        if not text:
            return (text, 0.0)

        if field_id not in self._code_exact:
            # No code table for this field -- pass through
            return (text, 1.0)

        # 1. Exact code match
        if text in self._code_exact.get(field_id, {}):
            return (text, 1.0)

        # 2. Case-insensitive code match
        lower_idx = self._code_lower.get(field_id, {})
        hit = lower_idx.get(text.lower())
        if hit is not None:
            return (hit, 0.95)

        # 3. Exact description match
        desc_idx = self._desc_lower.get(field_id, {})
        hit = desc_idx.get(text.lower())
        if hit is not None:
            return (hit, 0.9)

        # 4. Fuzzy description match
        desc_pairs = self._desc_list.get(field_id, [])
        if _HAS_RAPIDFUZZ and desc_pairs:
            descriptions = [d for d, _ in desc_pairs]
            result = _process.extractOne(
                text.lower(),
                descriptions,
                scorer=_fuzz.WRatio,
                score_cutoff=85,
            )
            if result is not None:
                matched_desc, score, idx = result
                code = desc_pairs[idx][1]
                confidence = 0.9 * (score / 100.0)
                return (code, round(confidence, 4))

        # 5. No match
        return (text, 0.0)

    def get_valid_codes_prompt(self, field_id: str) -> str:
        """Return compact code-reference string for prompt injection."""
        codes_dict = self._valid_values.get(field_id, {})
        if not codes_dict:
            return ""
        parts = [f"{code}={desc}" for code, desc in codes_dict.items()]
        return ", ".join(parts)

    def has_codes(self, field_id: str) -> bool:
        return bool(self._valid_values.get(field_id))

    @classmethod
    def from_data_items(cls, items: list) -> "GenericCodeResolver":
        """Build a resolver from a list of DataItem objects.

        Extracts ``valid_values`` dict from each item that has one.
        Uses ``item.id`` or ``item.json_field`` as the field_id.
        """
        valid_values_map: dict[str, dict[str, str]] = {}
        for item in items:
            fid = getattr(item, "json_field", None) or getattr(item, "id", None) or str(id(item))
            vv = getattr(item, "valid_values", None)
            if vv and isinstance(vv, dict):
                valid_values_map[fid] = {str(k): str(v) for k, v in vv.items()}
        return cls(valid_values_map)
