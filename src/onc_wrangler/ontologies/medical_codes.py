"""Medical code knowledge base with fuzzy retrieval.

Loads bundled oncology subsets (and optionally full releases) of
ICD-10-CM, LOINC, and SNOMED CT from ``data/ontologies/medical_codes/``
and exposes fuzzy search + keyword-based retrieval used by the synthetic
data generation pipeline to ground LLM output in real codes.

Each vocabulary is a CSV with columns ``code,description,category``.
If a ``full/`` subdirectory exists under the vocabulary directory, any
CSVs there are preferred over the bundled subset.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from rapidfuzz import fuzz, process, utils

logger = logging.getLogger(__name__)

# Default data location inside the plugin.
_PLUGIN_DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "ontologies"
    / "medical_codes"
)

SUPPORTED_VOCABS = ("icd10cm", "loinc", "snomed")


# Boilerplate tokens common to medical-code descriptions that shouldn't
# contribute meaningful match score on their own.
_BOILERPLATE_TOKENS: frozenset[str] = frozenset({
    "the", "of", "in", "and", "or", "with", "by", "to", "for",
    "malignant", "neoplasm", "unspecified", "disease", "disorder",
    "value", "volume", "mass", "type", "other", "not", "elsewhere",
    "classified", "nos", "finding", "procedure", "qualifier",
    # Generic oncology verbs that appear in many descriptions.
    "tumor", "tumour", "carcinoma",
})

# Query-side synonym expansion. When a user searches for a colloquial
# term that isn't present in formal medical code descriptions (e.g.
# "cancer"), we tack on the formal synonym so token/partial match
# scoring sees the same vocabulary as the code strings.
_QUERY_SYNONYMS: dict[str, str] = {
    "cancer": "cancer malignant neoplasm carcinoma tumor",
    "cancers": "cancers malignant neoplasm carcinoma tumor",
}


def _expand_query(query: str) -> str:
    tokens = query.split()
    expanded: list[str] = []
    for t in tokens:
        expanded.append(t)
        extra = _QUERY_SYNONYMS.get(t)
        if extra:
            expanded.append(extra)
    return " ".join(expanded)


def _composite_scorer(
    query: str,
    choice: str,
    processor=None,
    score_cutoff: float | None = None,
) -> float:
    """Max(partial_ratio, token_set_ratio) with a topic-overlap bonus.

    Adds a small bonus when the query and choice share at least one
    non-boilerplate token, which helps "breast" outrank "pancreas"
    entries that share generic "Malignant neoplasm of ..." boilerplate.
    """
    partial = fuzz.partial_ratio(query, choice)
    token_set = fuzz.token_set_ratio(query, choice)
    base = max(partial, token_set)
    q_tokens = {t for t in query.split() if t and t not in _BOILERPLATE_TOKENS}
    c_tokens = {t for t in choice.split() if t and t not in _BOILERPLATE_TOKENS}
    if q_tokens and c_tokens and q_tokens.isdisjoint(c_tokens):
        # Strongly penalize matches where no content-token overlaps.
        base *= 0.6
    return base


@dataclass(frozen=True)
class MedicalCode:
    """A single code entry from one of the supported vocabularies."""

    vocab: str
    code: str
    description: str
    category: Optional[str] = None

    def to_prompt_line(self) -> str:
        """Render as a compact markdown-ready line: ``code  description``."""
        return f"- {self.code}  {self.description}"


class MedicalCodeRegistry:
    """Loads bundled medical code CSVs and exposes fuzzy retrieval.

    Parameters
    ----------
    data_dir : Path | str | None
        Root directory containing per-vocabulary subdirectories
        (``icd10cm/``, ``loinc/``, ``snomed/``). Defaults to the bundled
        location inside the plugin.
    """

    def __init__(self, data_dir: Optional[Path | str] = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else _PLUGIN_DATA_DIR
        self._codes: dict[str, list[MedicalCode]] = {v: [] for v in SUPPORTED_VOCABS}
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load every supported vocabulary from disk.

        For each vocab we look first in ``<vocab>/full/*.csv`` (the
        downloader's output) and fall back to ``<vocab>/*.csv`` (the
        bundled subset).
        """
        for vocab in SUPPORTED_VOCABS:
            self._codes[vocab] = self._load_vocab(vocab)
        self._loaded = True
        logger.info(
            "MedicalCodeRegistry loaded: %s",
            {v: len(c) for v, c in self._codes.items()},
        )

    def _load_vocab(self, vocab: str) -> list[MedicalCode]:
        vocab_dir = self._data_dir / vocab
        if not vocab_dir.exists():
            logger.warning("Vocabulary directory missing: %s", vocab_dir)
            return []
        full_dir = vocab_dir / "full"
        csv_files: list[Path]
        if full_dir.is_dir() and any(full_dir.glob("*.csv")):
            csv_files = sorted(full_dir.glob("*.csv"))
            logger.info("Using full release for %s from %s", vocab, full_dir)
        else:
            csv_files = sorted(p for p in vocab_dir.glob("*.csv"))
        codes: list[MedicalCode] = []
        for path in csv_files:
            codes.extend(self._read_csv(vocab, path))
        return codes

    @staticmethod
    def _read_csv(vocab: str, path: Path) -> list[MedicalCode]:
        codes: list[MedicalCode] = []
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                code = (row.get("code") or "").strip()
                desc = (row.get("description") or "").strip()
                if not code or not desc:
                    continue
                category = (row.get("category") or "").strip() or None
                codes.append(
                    MedicalCode(
                        vocab=vocab,
                        code=code,
                        description=desc,
                        category=category,
                    )
                )
        return codes

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def codes(self, vocab: str) -> list[MedicalCode]:
        """Return all loaded codes for *vocab*."""
        self._ensure_loaded()
        if vocab not in self._codes:
            raise ValueError(f"Unsupported vocab: {vocab}")
        return list(self._codes[vocab])

    def count(self, vocab: str) -> int:
        self._ensure_loaded()
        return len(self._codes.get(vocab, []))

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        vocab: str,
        limit: int = 20,
        score_cutoff: float = 65.0,
    ) -> list[MedicalCode]:
        """Fuzzy-rank codes in *vocab* by similarity of their description to *query*.

        Uses a composite scorer that takes the max of ``partial_ratio``
        (good for single keyword in a long description, e.g.
        "hemoglobin" in "Hemoglobin [Mass/volume] in Blood") and
        ``token_set_ratio`` (good for multi-word bag-of-words queries
        like "breast cancer" vs "Malignant tumor of breast"), with a
        penalty for pairs that share generic boilerplate tokens (e.g.
        "malignant neoplasm of") without a true topic overlap.
        """
        self._ensure_loaded()
        if vocab not in self._codes:
            raise ValueError(f"Unsupported vocab: {vocab}")
        query = (query or "").strip()
        if not query:
            return []
        corpus = self._codes[vocab]
        if not corpus:
            return []
        choices = [c.description for c in corpus]
        expanded = _expand_query(utils.default_process(query))
        matches = process.extract(
            expanded,
            choices,
            scorer=_composite_scorer,
            processor=utils.default_process,
            limit=limit,
            score_cutoff=score_cutoff,
        )
        # Each match is (description, score, index).
        return [corpus[idx] for _desc, _score, idx in matches]

    def retrieve_for_context(
        self,
        keywords: Iterable[str],
        vocabs: Iterable[str] = SUPPORTED_VOCABS,
        per_vocab_limit: int = 25,
        per_keyword_limit: int = 5,
        score_cutoff: float = 70.0,
    ) -> dict[str, list[MedicalCode]]:
        """Aggregate top fuzzy matches across a list of keywords.

        For each vocab, each keyword contributes up to *per_keyword_limit*
        matches; duplicates (by code) are removed while preserving order;
        the final list is truncated to *per_vocab_limit*.
        """
        self._ensure_loaded()
        kw_list = [k.strip() for k in keywords if k and k.strip()]
        result: dict[str, list[MedicalCode]] = {}
        for vocab in vocabs:
            if vocab not in self._codes:
                continue
            seen: set[str] = set()
            ordered: list[MedicalCode] = []
            for kw in kw_list:
                hits = self.search(
                    kw,
                    vocab,
                    limit=per_keyword_limit,
                    score_cutoff=score_cutoff,
                )
                for code in hits:
                    if code.code in seen:
                        continue
                    seen.add(code.code)
                    ordered.append(code)
                    if len(ordered) >= per_vocab_limit:
                        break
                if len(ordered) >= per_vocab_limit:
                    break
            result[vocab] = ordered
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()
