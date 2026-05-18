"""De-identify one structured table.

This module is intentionally file-oriented: it takes one CSV/TSV/parquet table,
detects likely PHI-bearing columns, and writes a de-identified table plus a
private manifest that can be reused for stable pseudonyms and date shifts.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import pandas as pd

from ..config import LLMConfig
from ..llm import create_llm_client
from ..llm.base import LLMClient

logger = logging.getLogger(__name__)


_SCHEMA_VERSION = 1

_PATIENT_ID_NAMES = {
    "patient_id",
    "patientid",
    "pat_id",
    "record_id",
    "subject_id",
    "subjectid",
    "person_id",
    "personid",
    "empi",
    "enterprise_id",
    "study_id",
    "participant_id",
    "case_id",
}
_MRN_NAMES = {
    "mrn",
    "medical_record_number",
    "medicalrecordnumber",
    "medrecnum",
}
_FIRST_NAME_MARKERS = {"first", "given", "fname"}
_LAST_NAME_MARKERS = {"last", "family", "surname", "lname"}
_MIDDLE_NAME_MARKERS = {"middle", "mname"}
_NAME_NAMES = {
    "name",
    "patient_name",
    "full_name",
    "person_name",
    "first_name",
    "first_nm",
    "last_name",
    "last_nm",
    "middle_name",
    "middle_nm",
    "fname",
    "lname",
    "mname",
}
_DIRECT_IDENTIFIER_MARKERS = {
    "phone",
    "mobile",
    "email",
    "ssn",
    "social_security",
    "address",
    "street",
    "city",
    "state",
    "zip",
    "zipcode",
    "zip_code",
    "postal",
    "county",
    "fax",
    "insurance",
    "policy",
    "account",
    "acct",
    "accession",
}
_BIRTH_DATE_NAMES = {
    "dob",
    "date_of_birth",
    "birth_date",
    "birthdate",
    "patient_dob",
}
_AGE_NAMES = {"age", "patient_age", "age_at_visit", "age_at_diagnosis"}
_TEXT_MARKERS = {
    "text",
    "note",
    "notes",
    "comment",
    "comments",
    "evidence",
    "blurb",
    "summary",
    "narrative",
    "finding",
    "findings",
    "impression",
    "description",
    "reason",
}
_SEX_NAMES = {"sex", "gender", "patient_sex", "patient_gender"}
_NON_PERSON_NAME_MARKERS = {
    "biomarker",
    "cancer",
    "diagnosis",
    "disease",
    "drug",
    "facility",
    "gene",
    "histology",
    "hospital",
    "institution",
    "lab",
    "med",
    "medication",
    "procedure",
    "provider",
    "regimen",
    "test",
    "therapy",
    "tumor",
}

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)"
)
_SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_ADDRESS_RE = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,5}\s+"
    r"(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|court|ct)\b",
    re.I,
)
_MRN_IN_TEXT_RE = re.compile(
    r"\b(?:MRN|medical record(?: number)?|med rec)(?:\s*[:#]\s*|\s+)"
    r"(?!MRN\d{6}\b)[A-Za-z0-9-]{4,}\b",
    re.I,
)
_DATE_YYYY_RE = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b")
_DATE_US_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_AGE_YEAR_OLD_RE = re.compile(
    r"\b(?:9[0-9]|1[0-9]{2})[- ]year[- ]old\b",
    re.I,
)
_AGE_YEARS_OLD_RE = re.compile(
    r"\b(?:9[0-9]|1[0-9]{2})\s*(?:years?\s*old|yo|y/o)\b",
    re.I,
)
_AGE_PREFIX_RE = re.compile(r"\bage\s+(?:9[0-9]|1[0-9]{2})\b", re.I)
_HONORIFIC_NAME_RE = re.compile(
    r"\b(?:Mr|Ms|Mrs|Miss)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
)

_FEMALE_FIRST_NAMES = [
    "Aaliyah",
    "Amelia",
    "Camila",
    "Clara",
    "Elena",
    "Fatima",
    "Grace",
    "Hannah",
    "Isabel",
    "Jasmine",
    "Leah",
    "Maya",
    "Naomi",
    "Nora",
    "Priya",
    "Rosa",
    "Sofia",
    "Talia",
    "Vivian",
    "Zoe",
]
_MALE_FIRST_NAMES = [
    "Adrian",
    "Caleb",
    "Daniel",
    "Elias",
    "Gabriel",
    "Henry",
    "Isaac",
    "Julian",
    "Leo",
    "Mateo",
    "Miles",
    "Noah",
    "Owen",
    "Rafael",
    "Robert",
    "Samuel",
    "Theo",
    "Victor",
    "Wesley",
    "Xavier",
]
_NEUTRAL_FIRST_NAMES = [
    "Alex",
    "Avery",
    "Casey",
    "Drew",
    "Emerson",
    "Jordan",
    "Kai",
    "Morgan",
    "Quinn",
    "Reese",
    "Riley",
    "Rowan",
    "Sage",
    "Taylor",
]
_LAST_NAMES = [
    "Alvarez",
    "Bennett",
    "Brooks",
    "Carter",
    "Chen",
    "Coleman",
    "Davis",
    "Diaz",
    "Edwards",
    "Foster",
    "Garcia",
    "Green",
    "Harris",
    "Henderson",
    "Jackson",
    "Johnson",
    "Kim",
    "Lee",
    "Lewis",
    "Martinez",
    "Mitchell",
    "Nguyen",
    "Patel",
    "Price",
    "Ramirez",
    "Reed",
    "Rivera",
    "Robinson",
    "Singh",
    "Smith",
    "Taylor",
    "Thompson",
    "Walker",
    "Williams",
    "Wilson",
    "Young",
]


@dataclass
class DeidentificationConfig:
    """Configuration for table de-identification."""

    patient_id_column: Optional[str] = None
    mrn_column: Optional[str] = None
    name_columns: list[str] = field(default_factory=list)
    text_columns: list[str] = field(default_factory=list)
    date_shift_range_days: int = 180
    id_prefix: str = "patient"
    pseudo_mrn_prefix: str = "MRN"
    seed: str = "onc-data-wrangler-deidentify-table-v1"
    use_llm: bool = False
    max_workers: int = 4
    drop_direct_identifiers: bool = True


@dataclass
class ColumnDecision:
    """How one column will be treated."""

    column: str
    action: str
    phi_type: Optional[str]
    reason: str
    confidence: float


@dataclass
class DeidentificationResult:
    """Result from de-identifying a DataFrame."""

    dataframe: pd.DataFrame
    decisions: list[ColumnDecision]
    manifest: dict[str, Any]
    report: dict[str, Any]
    review_queue: pd.DataFrame


@dataclass
class _PatientIdentity:
    original_key: str
    pseudo_patient_id: str
    pseudo_mrn: str
    fake_first_name: str
    fake_last_name: str
    fake_middle_name: str
    date_shift_days: int

    @property
    def fake_full_name(self) -> str:
        return f"{self.fake_first_name} {self.fake_last_name}"


def load_table(path: str | Path) -> pd.DataFrame:
    """Load a CSV, TSV, or parquet table."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t", low_memory=False)
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    raise ValueError(f"Unsupported table file type: {path}")


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    """Write a CSV, TSV, or parquet table based on the output suffix."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df.to_parquet(path, index=False)
    elif suffix == ".tsv":
        df.to_csv(path, sep="\t", index=False)
    elif suffix == ".csv":
        df.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported output table file type: {path}")
    return path


def classify_columns(
    df: pd.DataFrame,
    config: Optional[DeidentificationConfig] = None,
) -> list[ColumnDecision]:
    """Classify columns by likely PHI handling action."""
    config = config or DeidentificationConfig()
    explicit_patient = _lower_name(config.patient_id_column)
    explicit_mrn = _lower_name(config.mrn_column)
    explicit_names = {_lower_name(c) for c in config.name_columns}
    explicit_text = {_lower_name(c) for c in config.text_columns}

    decisions: list[ColumnDecision] = []
    for col in df.columns:
        lower = _lower_name(col)
        norm = _normalize_col(col)
        markers = set(norm.split("_"))

        if explicit_patient and lower == explicit_patient:
            decisions.append(_decision(col, "patient_id", "patient_id", "explicit patient ID column", 1.0))
        elif explicit_mrn and lower == explicit_mrn:
            decisions.append(_decision(col, "mrn", "mrn", "explicit MRN column", 1.0))
        elif lower in explicit_names:
            decisions.append(_decision(col, "name", "name", "explicit name column", 1.0))
        elif lower in explicit_text:
            decisions.append(_decision(col, "text", "free_text", "explicit free-text column", 1.0))
        elif lower in _PATIENT_ID_NAMES or norm in _PATIENT_ID_NAMES or (
            "patient" in markers and "id" in markers
        ):
            decisions.append(_decision(col, "patient_id", "patient_id", "column name matches patient identifier pattern", 0.95))
        elif lower in _MRN_NAMES or norm in _MRN_NAMES or "mrn" in markers:
            decisions.append(_decision(col, "mrn", "mrn", "column name matches MRN pattern", 0.95))
        elif lower in _BIRTH_DATE_NAMES or norm in _BIRTH_DATE_NAMES:
            decisions.append(_decision(col, "birth_date", "date_of_birth", "column name matches birth date pattern", 0.95))
        elif lower in _AGE_NAMES or norm in _AGE_NAMES or (norm.startswith("age_") or norm.endswith("_age")):
            decisions.append(_decision(col, "age", "age", "column name matches age pattern", 0.9))
        elif lower in _NAME_NAMES or norm in _NAME_NAMES or _looks_like_name_column(norm):
            decisions.append(_decision(col, "name", "name", "column name matches person-name pattern", 0.9))
        elif _looks_like_direct_identifier_column(norm):
            decisions.append(_decision(col, "drop", "direct_identifier", "column name matches direct identifier pattern", 0.9))
        elif _looks_like_date_column(col, df[col]):
            decisions.append(_decision(col, "date", "date", "values or name look like dates", 0.8))
        elif _looks_like_text_column(col, df[col]):
            decisions.append(_decision(col, "text", "free_text", "values or name look like free text", 0.75))
        elif _looks_like_direct_identifier_values(df[col]):
            decisions.append(_decision(col, "drop", "direct_identifier", "sampled values look like direct identifiers", 0.8))
        else:
            decisions.append(_decision(col, "keep", None, "no likely PHI detected", 0.5))
    return decisions


def deidentify_dataframe(
    df: pd.DataFrame,
    config: Optional[DeidentificationConfig] = None,
    *,
    manifest: Optional[dict[str, Any]] = None,
    llm_client: Optional[LLMClient] = None,
) -> DeidentificationResult:
    """De-identify a DataFrame.

    The returned manifest is sensitive: it may contain original identifiers,
    fake-name mappings, and date shifts.
    """
    config = config or DeidentificationConfig()
    if config.use_llm and llm_client is None:
        raise ValueError("config.use_llm=True requires llm_client")

    decisions = classify_columns(df, config)
    decision_by_col = {d.column: d for d in decisions}
    patient_id_col = _first_action(decisions, "patient_id")
    mrn_col = _first_action(decisions, "mrn")
    name_cols = [d.column for d in decisions if d.action == "name"]
    birth_date_cols = [d.column for d in decisions if d.action == "birth_date"]
    date_cols = [d.column for d in decisions if d.action == "date"]
    text_cols = [d.column for d in decisions if d.action == "text"]
    age_cols = [d.column for d in decisions if d.action == "age"]
    drop_cols = [d.column for d in decisions if d.action == "drop"]
    sex_col = _detect_sex_column(df)

    manifest = _prepare_manifest(manifest, config)
    identities = _build_identities(
        df,
        config,
        manifest,
        patient_id_col=patient_id_col,
        mrn_col=mrn_col,
        name_cols=name_cols,
        sex_col=sex_col,
    )

    out = df.copy()
    report_counts: dict[str, int] = {}
    review_rows: list[dict[str, Any]] = []

    for col in df.columns:
        decision = decision_by_col[col]
        report_counts[decision.action] = report_counts.get(decision.action, 0) + 1

        if decision.action == "patient_id":
            out[col] = [
                identities[_identity_key_for_row(row, patient_id_col, mrn_col, name_cols)].pseudo_patient_id
                for _, row in df.iterrows()
            ]
        elif decision.action == "mrn":
            out[col] = [
                identities[_identity_key_for_row(row, patient_id_col, mrn_col, name_cols)].pseudo_mrn
                for _, row in df.iterrows()
            ]
        elif decision.action == "name":
            out[col] = [
                _fake_name_for_column(
                    col,
                    identities[_identity_key_for_row(row, patient_id_col, mrn_col, name_cols)],
                )
                for _, row in df.iterrows()
            ]
        elif decision.action == "date":
            out[col] = [
                _shift_date_value(
                    row.get(col),
                    identities[_identity_key_for_row(row, patient_id_col, mrn_col, name_cols)].date_shift_days,
                )
                for _, row in df.iterrows()
            ]
        elif decision.action == "age":
            out[col] = out[col].map(_cap_age_value)
        elif decision.action == "text":
            rewritten = [None] * len(df)
            rows = list(df.iterrows())

            def process_text_row(row_position: int, row_index: Any, row: pd.Series):
                ident = identities[_identity_key_for_row(row, patient_id_col, mrn_col, name_cols)]
                text, review_reason, llm_used = _deidentify_text_value(
                    row.get(col),
                    row=row,
                    identity=ident,
                    patient_id_col=patient_id_col,
                    mrn_col=mrn_col,
                    name_cols=name_cols,
                    llm_client=llm_client if config.use_llm else None,
                )
                return row_position, row_index, text, review_reason, llm_used

            if config.use_llm and llm_client is not None and config.max_workers > 1:
                with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
                    futures = [
                        executor.submit(process_text_row, pos, row_index, row)
                        for pos, (row_index, row) in enumerate(rows)
                    ]
                    processed_rows = [future.result() for future in as_completed(futures)]
                processed_rows.sort(key=lambda item: item[0])
            else:
                processed_rows = [
                    process_text_row(pos, row_index, row)
                    for pos, (row_index, row) in enumerate(rows)
                ]

            for row_position, row_index, text, review_reason, llm_used in processed_rows:
                rewritten[row_position] = text
                if review_reason:
                    review_rows.append(
                        {
                            "row_index": row_index,
                            "column": col,
                            "reason": review_reason,
                            "llm_used": llm_used,
                            "deidentified_preview": str(text)[:200],
                        }
                    )
            out[col] = rewritten

    cols_to_drop = []
    if config.drop_direct_identifiers:
        cols_to_drop.extend(drop_cols)
    # DOB/birth-date columns are not date-shifted. Dropping them avoids exact
    # or bounded age derivation when shifted event dates are retained.
    cols_to_drop.extend(birth_date_cols)
    cols_to_drop = [c for c in cols_to_drop if c in out.columns]
    if cols_to_drop:
        out = out.drop(columns=cols_to_drop)

    manifest["updated_at"] = _now_iso()
    manifest["column_decisions"] = [asdict(d) for d in decisions]

    report = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "input_rows": int(len(df)),
        "input_columns": int(len(df.columns)),
        "output_rows": int(len(out)),
        "output_columns": int(len(out.columns)),
        "column_action_counts": report_counts,
        "dropped_columns": cols_to_drop,
        "patient_id_column": patient_id_col,
        "mrn_column": mrn_col,
        "name_columns": name_cols,
        "text_columns": text_cols,
        "date_columns": date_cols,
        "birth_date_columns_dropped": birth_date_cols,
        "age_columns_capped": age_cols,
        "date_shift_range_days": config.date_shift_range_days,
        "review_queue_rows": len(review_rows),
        "column_decisions": [asdict(d) for d in decisions],
    }
    return DeidentificationResult(
        dataframe=out,
        decisions=decisions,
        manifest=manifest,
        report=report,
        review_queue=pd.DataFrame(review_rows),
    )


def read_manifest(path: str | Path | None) -> dict[str, Any] | None:
    """Read a private de-identification manifest if supplied."""
    if not path:
        return None
    with open(path) as f:
        return json.load(f)


def write_manifest(manifest: dict[str, Any], path: str | Path) -> Path:
    """Write the private manifest."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


def write_json_report(report: dict[str, Any], path: str | Path) -> Path:
    """Write a non-PHI de-identification report."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


def _decision(
    column: str,
    action: str,
    phi_type: Optional[str],
    reason: str,
    confidence: float,
) -> ColumnDecision:
    return ColumnDecision(
        column=column,
        action=action,
        phi_type=phi_type,
        reason=reason,
        confidence=confidence,
    )


def _prepare_manifest(
    manifest: Optional[dict[str, Any]],
    config: DeidentificationConfig,
) -> dict[str, Any]:
    manifest = dict(manifest or {})
    manifest.setdefault("schema_version", _SCHEMA_VERSION)
    manifest.setdefault("created_at", _now_iso())
    manifest.setdefault("seed", config.seed)
    manifest.setdefault("date_shift_range_days", config.date_shift_range_days)
    manifest.setdefault("patients", {})
    manifest.setdefault("source_note", "PRIVATE: contains re-identification mappings and exact date shifts.")
    return manifest


def _build_identities(
    df: pd.DataFrame,
    config: DeidentificationConfig,
    manifest: dict[str, Any],
    *,
    patient_id_col: Optional[str],
    mrn_col: Optional[str],
    name_cols: list[str],
    sex_col: Optional[str],
) -> dict[str, _PatientIdentity]:
    keys = sorted(
        {
            _identity_key_for_row(row, patient_id_col, mrn_col, name_cols)
            for _, row in df.iterrows()
        }
    )
    patients = manifest.setdefault("patients", {})
    next_index = _next_manifest_index(patients, config.id_prefix)
    identities: dict[str, _PatientIdentity] = {}

    for key in keys:
        entry = patients.get(key)
        if not entry:
            sex_value = _first_sex_for_key(df, key, patient_id_col, mrn_col, name_cols, sex_col)
            first, last, middle = _fake_name_parts(key, sex_value, config.seed)
            entry = {
                "pseudo_patient_id": f"{config.id_prefix}_{next_index:06d}",
                "pseudo_mrn": f"{config.pseudo_mrn_prefix}{next_index:06d}",
                "fake_first_name": first,
                "fake_last_name": last,
                "fake_middle_name": middle,
                "fake_name": f"{first} {last}",
                "date_shift_days": _stable_date_shift(
                    key,
                    config.date_shift_range_days,
                    config.seed,
                ),
            }
            patients[key] = entry
            next_index += 1
        identities[key] = _PatientIdentity(
            original_key=key,
            pseudo_patient_id=entry["pseudo_patient_id"],
            pseudo_mrn=entry["pseudo_mrn"],
            fake_first_name=entry["fake_first_name"],
            fake_last_name=entry["fake_last_name"],
            fake_middle_name=entry.get("fake_middle_name", "A"),
            date_shift_days=int(entry["date_shift_days"]),
        )
    return identities


def _next_manifest_index(patients: dict[str, Any], prefix: str) -> int:
    max_seen = 0
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    for entry in patients.values():
        pseudo = str(entry.get("pseudo_patient_id", ""))
        match = pattern.match(pseudo)
        if match:
            max_seen = max(max_seen, int(match.group(1)))
    return max_seen + 1


def _identity_key_for_row(
    row: pd.Series,
    patient_id_col: Optional[str],
    mrn_col: Optional[str],
    name_cols: list[str],
) -> str:
    if patient_id_col:
        value = _clean_scalar(row.get(patient_id_col))
        if value is not None:
            return value
    if mrn_col:
        value = _clean_scalar(row.get(mrn_col))
        if value is not None:
            return f"mrn:{value}"
    name_key_parts = [_clean_scalar(row.get(c)) for c in name_cols]
    name_key_parts = [p for p in name_key_parts if p]
    if name_key_parts:
        return "name:" + "|".join(name_key_parts)
    return "__file__"


def _first_sex_for_key(
    df: pd.DataFrame,
    key: str,
    patient_id_col: Optional[str],
    mrn_col: Optional[str],
    name_cols: list[str],
    sex_col: Optional[str],
) -> Optional[str]:
    if not sex_col:
        return None
    for _, row in df.iterrows():
        if _identity_key_for_row(row, patient_id_col, mrn_col, name_cols) == key:
            value = _clean_scalar(row.get(sex_col))
            if value:
                return value
    return None


def _fake_name_parts(key: str, sex_value: Optional[str], seed: str) -> tuple[str, str, str]:
    normalized_sex = (sex_value or "").strip().lower()
    if normalized_sex in {"f", "female", "woman", "w"}:
        first_pool = _FEMALE_FIRST_NAMES
    elif normalized_sex in {"m", "male", "man"}:
        first_pool = _MALE_FIRST_NAMES
    else:
        first_pool = _NEUTRAL_FIRST_NAMES
    first = first_pool[_stable_index(seed, key, "first", modulo=len(first_pool))]
    last = _LAST_NAMES[_stable_index(seed, key, "last", modulo=len(_LAST_NAMES))]
    middle = chr(ord("A") + _stable_index(seed, key, "middle", modulo=26))
    return first, last, middle


def _fake_name_for_column(col: str, identity: _PatientIdentity) -> str:
    norm = _normalize_col(col)
    markers = set(norm.split("_"))
    if markers & _FIRST_NAME_MARKERS:
        return identity.fake_first_name
    if markers & _LAST_NAME_MARKERS:
        return identity.fake_last_name
    if markers & _MIDDLE_NAME_MARKERS:
        return identity.fake_middle_name
    return identity.fake_full_name


def _deidentify_text_value(
    value: Any,
    *,
    row: pd.Series,
    identity: _PatientIdentity,
    patient_id_col: Optional[str],
    mrn_col: Optional[str],
    name_cols: list[str],
    llm_client: Optional[LLMClient],
) -> tuple[Any, Optional[str], bool]:
    text = _clean_scalar(value)
    if text is None:
        return value, None, False

    original_text = text
    replacements: list[tuple[str, str]] = []
    if patient_id_col:
        original_pid = _clean_scalar(row.get(patient_id_col))
        if original_pid:
            replacements.append((original_pid, identity.pseudo_patient_id))
    if mrn_col:
        original_mrn = _clean_scalar(row.get(mrn_col))
        if original_mrn:
            replacements.extend(
                [
                    (f"MRN {original_mrn}", identity.pseudo_mrn),
                    (f"MRN: {original_mrn}", identity.pseudo_mrn),
                    (f"MRN# {original_mrn}", identity.pseudo_mrn),
                    (f"medical record number {original_mrn}", identity.pseudo_mrn),
                ]
            )
            replacements.append((original_mrn, identity.pseudo_mrn))
    replacements.extend(_name_replacements(row, name_cols, identity))

    text = _redact_contact_identifiers(text)
    for old, new in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        text = _replace_literal(text, old, new)

    text = _redact_residual_mrns(text)
    text = _shift_dates_in_text(text, identity.date_shift_days)
    text = _cap_age_mentions(text)

    needs_review = _text_needs_review(text)
    llm_used = False
    if needs_review and llm_client is not None:
        rewritten, llm_review = _rewrite_text_with_llm(llm_client, text)
        text = rewritten
        needs_review = llm_review or _text_needs_review(text)
        llm_used = True

    if needs_review:
        return text, "possible_remaining_phi", llm_used
    if text != original_text and llm_client is not None:
        return text, None, llm_used
    return text, None, llm_used


def _name_replacements(
    row: pd.Series,
    name_cols: list[str],
    identity: _PatientIdentity,
) -> list[tuple[str, str]]:
    replacements: list[tuple[str, str]] = []
    first_value = None
    last_value = None
    middle_value = None
    for col in name_cols:
        value = _clean_scalar(row.get(col))
        if not value:
            continue
        fake = _fake_name_for_column(col, identity)
        replacements.append((value, fake))
        norm = _normalize_col(col)
        markers = set(norm.split("_"))
        if markers & _FIRST_NAME_MARKERS:
            first_value = value
        elif markers & _LAST_NAME_MARKERS:
            last_value = value
        elif markers & _MIDDLE_NAME_MARKERS:
            middle_value = value
    if first_value and last_value:
        full_values = [
            f"{first_value} {last_value}",
            f"{last_value}, {first_value}",
        ]
        if middle_value:
            full_values.extend(
                [
                    f"{first_value} {middle_value} {last_value}",
                    f"{last_value}, {first_value} {middle_value}",
                ]
            )
        for value in full_values:
            replacements.append((value, identity.fake_full_name))
    return replacements


def _redact_contact_identifiers(text: str) -> str:
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _SSN_RE.sub("[SSN]", text)
    text = _ADDRESS_RE.sub("[ADDRESS]", text)
    return text


def _redact_residual_mrns(text: str) -> str:
    return _MRN_IN_TEXT_RE.sub("[MRN]", text)


def _shift_dates_in_text(text: str, shift_days: int) -> str:
    def replace(match: re.Match[str]) -> str:
        return _shift_date_string(match.group(0), shift_days) or match.group(0)

    text = _DATE_YYYY_RE.sub(replace, text)
    text = _DATE_US_RE.sub(replace, text)
    return text


def _cap_age_mentions(text: str) -> str:
    text = _AGE_YEAR_OLD_RE.sub("90+ year-old", text)
    text = _AGE_YEARS_OLD_RE.sub("90+ years old", text)
    text = _AGE_PREFIX_RE.sub("age 90+", text)
    return text


def _text_needs_review(text: str) -> bool:
    return bool(
        _EMAIL_RE.search(text)
        or _PHONE_RE.search(text)
        or _SSN_RE.search(text)
        or _ADDRESS_RE.search(text)
        or _MRN_IN_TEXT_RE.search(text)
        or _HONORIFIC_NAME_RE.search(text)
    )


def _rewrite_text_with_llm(client: LLMClient, text: str) -> tuple[str, bool]:
    system = """\
You de-identify short clinical evidence text.
Return valid JSON only with keys:
- deidentified_text: string
- phi_removed: array of PHI category strings
- review_required: boolean

Preserve clinical meaning, diagnoses, biomarkers, treatments, measurements,
and non-identifying temporal relationships. Remove direct identifiers. Replace
any remaining patient/person names with realistic fake names. Keep already
fake-looking patient names unchanged. Do not add clinical facts.
"""
    prompt = f"""\
Text:
<text>
{text}
</text>
"""
    try:
        response = client.generate_structured(
            prompt=prompt,
            system=system,
            max_tokens=1024,
            temperature=0.0,
        )
        parsed = _parse_json_object(response.text)
        rewritten = parsed.get("deidentified_text")
        if not isinstance(rewritten, str) or not rewritten.strip():
            return text, True
        return rewritten.strip(), bool(parsed.get("review_required", False))
    except Exception as exc:  # pragma: no cover - defensive path
        logger.warning("LLM text de-identification failed: %s", exc)
        return text, True


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < start:
            raise
        parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return parsed


def _replace_literal(text: str, old: str, new: str) -> str:
    old = old.strip()
    if not old:
        return text
    escaped = re.escape(old)
    if re.match(r"^[A-Za-z0-9_ -]+$", old):
        pattern = rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
    else:
        pattern = escaped
    return re.sub(pattern, new, text, flags=re.I)


def _shift_date_value(value: Any, shift_days: int) -> Any:
    clean = _clean_scalar(value)
    if clean is None:
        return value
    shifted = _shift_date_string(clean, shift_days)
    return shifted if shifted is not None else value


def _shift_date_string(value: str, shift_days: int) -> Optional[str]:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    shifted = parsed + pd.Timedelta(days=shift_days)
    return shifted.strftime("%Y-%m-%d")


def _cap_age_value(value: Any) -> Any:
    clean = _clean_scalar(value)
    if clean is None:
        return value
    try:
        number = float(clean)
    except ValueError:
        return _cap_age_mentions(clean)
    if number > 89:
        return "90+"
    if number.is_integer():
        return int(number)
    return number


def _stable_date_shift(key: str, range_days: int, seed: str) -> int:
    if range_days < 0:
        raise ValueError("date_shift_range_days must be non-negative")
    if range_days == 0:
        return 0
    span = range_days * 2 + 1
    return _stable_index(seed, key, "date_shift", modulo=span) - range_days


def _stable_index(*parts: str, modulo: int) -> int:
    digest = sha256("||".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % modulo


def _first_action(decisions: list[ColumnDecision], action: str) -> Optional[str]:
    for decision in decisions:
        if decision.action == action:
            return decision.column
    return None


def _detect_sex_column(df: pd.DataFrame) -> Optional[str]:
    for col in df.columns:
        lower = _lower_name(col)
        norm = _normalize_col(col)
        if lower in _SEX_NAMES or norm in _SEX_NAMES:
            return col
    return None


def _looks_like_name_column(norm: str) -> bool:
    markers = set(norm.split("_"))
    if "provider" in markers or "doctor" in markers or "physician" in markers:
        return False
    if markers & _NON_PERSON_NAME_MARKERS:
        return False
    person_context = bool("name" in markers or markers & {"patient", "person", "member", "subject"})
    return bool(
        ("name" in markers and person_context)
        or ((markers & _FIRST_NAME_MARKERS) and person_context)
        or ((markers & _LAST_NAME_MARKERS) and person_context)
        or ((markers & _MIDDLE_NAME_MARKERS) and person_context)
    )


def _looks_like_direct_identifier_column(norm: str) -> bool:
    markers = set(norm.split("_"))
    if norm in {"state", "patient_state", "address_state", "mailing_state"}:
        return True
    return bool(markers & (_DIRECT_IDENTIFIER_MARKERS - {"state"}))


def _looks_like_date_column(col: str, series: pd.Series) -> bool:
    norm = _normalize_col(col)
    if norm in {"date", "dt"} or norm.endswith("_date") or norm.endswith("_dt") or "date" in norm.split("_"):
        return True
    return _date_parse_ratio(series) >= 0.8


def _looks_like_text_column(col: str, series: pd.Series) -> bool:
    norm = _normalize_col(col)
    markers = set(norm.split("_"))
    if markers & _TEXT_MARKERS:
        return True
    sample = _sample_strings(series)
    if not sample:
        return False
    avg_len = sum(len(s) for s in sample) / len(sample)
    with_spaces = sum(" " in s for s in sample) / len(sample)
    unique_ratio = len(set(sample)) / len(sample)
    return avg_len >= 25 and with_spaces >= 0.5 and unique_ratio >= 0.5


def _looks_like_direct_identifier_values(series: pd.Series) -> bool:
    sample = _sample_strings(series)
    if not sample:
        return False
    hits = 0
    for value in sample:
        if _EMAIL_RE.search(value) or _PHONE_RE.search(value) or _SSN_RE.search(value):
            hits += 1
    return hits / len(sample) >= 0.2


def _date_parse_ratio(series: pd.Series) -> float:
    sample = _sample_strings(series)
    if not sample:
        return 0.0
    date_like = [
        s for s in sample
        if _DATE_YYYY_RE.fullmatch(s) or _DATE_US_RE.fullmatch(s)
    ]
    if not date_like:
        return 0.0
    parsed = pd.to_datetime(pd.Series(date_like), errors="coerce")
    return float(parsed.notna().sum()) / len(sample)


def _sample_strings(series: pd.Series, n: int = 100) -> list[str]:
    values = []
    for value in series.dropna().head(n).tolist():
        clean = _clean_scalar(value)
        if clean is not None:
            values.append(clean)
    return values


def _clean_scalar(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    return text


def _lower_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    return str(name).strip().lower()


def _normalize_col(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower())
    return normalized.strip("_")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_for_config(provider: str) -> str:
    if provider == "openai-compatible":
        return "openai"
    return provider


def _is_cloud_or_remote_provider(provider: str, base_url: Optional[str]) -> bool:
    provider = _provider_for_config(provider)
    if provider in {"anthropic", "vertex", "azure", "gemini"}:
        return True
    if provider != "openai":
        return True
    if not base_url:
        return False
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    return host not in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="De-identify one structured CSV/TSV/parquet table.",
    )
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--output-path")
    parser.add_argument("--output-dir")
    parser.add_argument("--patient-id-column")
    parser.add_argument("--mrn-column")
    parser.add_argument("--name-column", action="append", default=[])
    parser.add_argument("--text-column", action="append", default=[])
    parser.add_argument("--date-shift-range-days", type=int, default=180)
    parser.add_argument("--manifest-in")
    parser.add_argument("--manifest-out")
    parser.add_argument("--report-out")
    parser.add_argument("--review-queue-out")
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--allow-cloud-llm", action="store_true")
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--model", default="gpt-oss-120b")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--vertex-project")
    parser.add_argument("--vertex-region", default="us-central1")
    parser.add_argument("--azure-api-version", default="2024-12-01-preview")
    parser.add_argument("--reasoning-marker")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--yes", action="store_true", help="Accepted by the skill workflow for non-interactive execution.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    input_path = Path(args.input_path)
    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    output_path = Path(args.output_path) if args.output_path else output_dir / f"{input_path.stem}_deidentified{input_path.suffix}"
    manifest_out = Path(args.manifest_out) if args.manifest_out else output_dir / f"{input_path.stem}_deidentification_manifest.json"
    report_out = Path(args.report_out) if args.report_out else output_dir / f"{input_path.stem}_deidentification_report.json"
    review_queue_out = Path(args.review_queue_out) if args.review_queue_out else output_dir / f"{input_path.stem}_review_queue.csv"

    df = load_table(input_path)
    if args.limit is not None:
        df = df.head(args.limit).copy()

    llm_client = None
    if args.use_llm:
        provider = _provider_for_config(args.provider)
        if _is_cloud_or_remote_provider(provider, args.base_url) and not args.allow_cloud_llm:
            raise ValueError(
                "LLM de-identification may send PHI to a remote/cloud endpoint. "
                "Use --allow-cloud-llm only after confirming the endpoint is approved."
            )
        llm_config = LLMConfig(
            provider=provider,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            vertex_project=args.vertex_project,
            vertex_region=args.vertex_region,
            azure_api_version=args.azure_api_version,
            reasoning_marker=args.reasoning_marker,
            timeout=args.timeout,
        )
        llm_client = create_llm_client(llm_config)

    config = DeidentificationConfig(
        patient_id_column=args.patient_id_column,
        mrn_column=args.mrn_column,
        name_columns=args.name_column,
        text_columns=args.text_column,
        date_shift_range_days=args.date_shift_range_days,
        use_llm=args.use_llm,
        max_workers=args.max_workers,
    )
    result = deidentify_dataframe(
        df,
        config,
        manifest=read_manifest(args.manifest_in),
        llm_client=llm_client,
    )

    write_table(result.dataframe, output_path)
    write_manifest(result.manifest, manifest_out)
    write_json_report(result.report, report_out)
    result.review_queue.to_csv(review_queue_out, index=False)

    print(f"Rows: {len(df)} -> {len(result.dataframe)}")
    print(f"Columns: {len(df.columns)} -> {len(result.dataframe.columns)}")
    print(f"Output table: {output_path}")
    print(f"Private manifest: {manifest_out}")
    print(f"Report: {report_out}")
    print(f"Review queue: {review_queue_out}")
    if result.report["dropped_columns"]:
        print("Dropped columns: " + ", ".join(result.report["dropped_columns"]))
    if result.report["review_queue_rows"]:
        print(f"Review rows: {result.report['review_queue_rows']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
