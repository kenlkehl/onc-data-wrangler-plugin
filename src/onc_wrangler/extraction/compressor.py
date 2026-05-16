"""LLM-based compression of individual clinical documents."""

from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from ..config import LLMConfig, load_config
from ..llm import create_llm_client
from ..llm.base import LLMClient

logger = logging.getLogger(__name__)


COMPRESSION_SYSTEM_PROMPT = """\
You are an expert oncology clinical-document summarizer.

TASK:
Summarize one clinical document using only information explicitly stated in
the document and metadata supplied by the user.

OUTPUT FORMAT:
- Output only the summary text. Do not include headings, bullets, labels,
  markdown, preamble, caveats, or JSON.
- Use one paragraph of three sentences or less for the clinical document.
- If the document explicitly describes multiple independent primary cancers,
  output one paragraph per primary cancer diagnosis; each paragraph must still
  be three sentences or less.
- If a concept below is not mentioned in the document, omit that concept from
  the summary rather than writing that it is missing or unknown.
- Never write meta-commentary about the document itself. Do not state what the
  document does or does not contain, mention, address, describe, or discuss.
  Do not write phrases like "The document does not contain...", "No information
  is provided about...", "This report does not mention...", "The note focuses
  on...", or "This is not an oncology document." Just summarize the clinical
  content that is present.
- If the document has no oncology content (for example a spine imaging report
  for back pain, a non-cancer-related encounter, or an administrative note),
  simply summarize the clinical content that is present in three sentences or
  less. Do not add a disclaimer that the document is unrelated to cancer.

CONTENT TO CAPTURE WHEN PRESENT OR KNOWN:
- Age and sex.
- Cancer type and histology.
- Disease burden at diagnosis, including original stage, TNM, extent of
  metastatic disease, sites of involvement, and explicit disease risk scores
  such as International Prognostic Index, Follicular Lymphoma International
  Prognostic Index, or similar disease-specific scores.
- Current disease burden, including current sites of disease, progression,
  response, recurrence, remission, tumor markers such as carcinoembryonic
  antigen or CA 19-9, and clinically meaningful disease measurements.
- Biomarkers: capture all documented biomarkers without summarizing away
  individual results. Biomarkers include molecular alterations, cytogenetics,
  gene fusions, immunohistochemistry, microsatellite instability or mismatch
  repair status, tumor mutational burden, programmed death-ligand 1, hormone
  receptors, human epidermal growth factor receptor 2, and similar predictive,
  prognostic, or diagnostic findings. Biomarkers are NOT routine laboratory
  values and are NOT tumor markers such as carcinoembryonic antigen, CA 19-9,
  CA-125, alpha-fetoprotein, or prostate-specific antigen; tumor markers belong
  under current disease burden when clinically relevant.
- Current and prior treatments, with dates when present. Include details of
  each systemic therapy and local therapy, including surgery and radiation.
- Current and prior adverse events.
- Current and prior comorbidities.
- Current and prior performance status.
- For clinician notes, planned next steps.

STYLE RULES:
- Spell drug names out in full. Expand common oncology shorthand when the
  expansion is clear, for example fluorouracil for 5-FU, oxaliplatin for oxali,
  bevacizumab for bev, pembrolizumab for pembro, capecitabine for cape, and
  doxorubicin, bleomycin, vinblastine, and dacarbazine for ABVD. If expansion
  is uncertain, preserve the documented name and do not guess.
- Preserve dates of current and prior events in the categories above when
  dates are present; partial dates are acceptable.
- Do not invent facts, normalize uncertain values into certainty, or infer a
  biomarker or treatment from cancer type alone.
- Prefer concise clinical prose over exhaustive narrative, but do not omit
  documented biomarkers or distinct treatment lines solely to save words.
"""


def build_document_prompt(
    document_text: str,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Build the user prompt for one clinical document."""
    metadata = metadata or {}
    metadata_lines = []
    for key, value in metadata.items():
        clean = _clean_scalar(value)
        if clean is not None:
            metadata_lines.append(f"- {key}: {clean}")
    metadata_block = "\n".join(metadata_lines) if metadata_lines else "- none supplied"

    return f"""\
Document metadata:
{metadata_block}

Clinical document:
<document>
{document_text}
</document>
"""


def normalize_summary(text: str) -> str:
    """Clean common wrapper text without changing clinical content."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    lower = cleaned.lower()
    for prefix in ("summary:", "clinical summary:"):
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned


def compress_document(
    client: LLMClient,
    document_text: str,
    metadata: Optional[dict[str, Any]] = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> tuple[str, Optional[dict[str, int]]]:
    """Compress one clinical document with an LLM."""
    prompt = build_document_prompt(document_text, metadata)
    response = client.generate(
        prompt=prompt,
        system=COMPRESSION_SYSTEM_PROMPT,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return normalize_summary(response.text), response.usage


def load_notes_table(path: str | Path) -> pd.DataFrame:
    """Load a CSV or parquet notes table."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        return pd.read_csv(path, sep=sep, low_memory=False)
    raise ValueError(f"Unsupported notes file type: {path}")


def compress_notes_dataframe(
    notes_df: pd.DataFrame,
    client: LLMClient,
    *,
    patient_id_column: str = "patient_id",
    text_column: str = "text",
    date_column: str = "date",
    note_type_column: str = "note_type",
    document_id_column: Optional[str] = None,
    source_file: Optional[str] = None,
    max_workers: int = 4,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> pd.DataFrame:
    """Compress each row in a notes table as an individual document."""
    if text_column not in notes_df.columns:
        raise ValueError(f"Text column not found: {text_column}")

    records: list[dict[str, Any]] = []

    def process_row(row_index: Any, row: pd.Series) -> dict[str, Any]:
        text_value = _clean_scalar(row.get(text_column))
        text = "" if text_value is None else str(text_value)

        patient_id = _clean_scalar(row.get(patient_id_column))
        note_date = _clean_scalar(row.get(date_column))
        note_type = _clean_scalar(row.get(note_type_column))
        document_id = (
            _clean_scalar(row.get(document_id_column))
            if document_id_column
            else None
        )
        if document_id is None:
            prefix = source_file or "notes"
            document_id = f"{prefix}:row{row_index}"

        result: dict[str, Any] = {
            "source_file": source_file,
            "source_row_index": row_index,
            "document_id": str(document_id),
            "patient_id": None if patient_id is None else str(patient_id),
            "date": None if note_date is None else str(note_date),
            "note_type": None if note_type is None else str(note_type),
            "text_chars": len(text),
            "summary": "",
            "error": None,
        }

        if not text.strip():
            result["error"] = "empty_text"
            return result

        metadata = {
            "document_id": document_id,
            "patient_id": patient_id,
            "date": note_date,
            "note_type": note_type,
        }
        try:
            summary, usage = compress_document(
                client,
                text,
                metadata=metadata,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            result["summary"] = summary
            if usage:
                result["prompt_tokens"] = usage.get("prompt_tokens") or usage.get("input_tokens")
                result["completion_tokens"] = (
                    usage.get("completion_tokens") or usage.get("output_tokens")
                )
        except Exception as exc:  # pragma: no cover - exercised only on API failure
            logger.exception("Failed to compress document %s", document_id)
            result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    rows = list(notes_df.iterrows())
    if max_workers <= 1:
        for row_index, row in rows:
            records.append(process_row(row_index, row))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_row, row_index, row): row_index
                for row_index, row in rows
            }
            for future in as_completed(futures):
                records.append(future.result())

    out = pd.DataFrame(records)
    if not out.empty:
        out = out.sort_values(by=["source_file", "source_row_index"], na_position="first")
    return out.reset_index(drop=True)


def compress_notes_file(
    notes_path: str | Path,
    client: LLMClient,
    **kwargs: Any,
) -> pd.DataFrame:
    """Load and compress each document in one notes file."""
    notes_path = Path(notes_path)
    notes_df = load_notes_table(notes_path)
    return compress_notes_dataframe(
        notes_df,
        client,
        source_file=str(notes_path),
        **kwargs,
    )


def write_outputs(results: pd.DataFrame, output_dir: str | Path, prefix: str = "compressed_notes") -> tuple[Path, Path]:
    """Write CSV and JSONL outputs."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{prefix}.csv"
    jsonl_path = output_dir / f"{prefix}.jsonl"

    results.to_csv(csv_path, index=False)
    with open(jsonl_path, "w") as f:
        for record in results.to_dict(orient="records"):
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
    return csv_path, jsonl_path


def _clean_scalar(value: Any) -> Optional[Any]:
    """Return None for pandas-style missing values."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value)
    if text.strip() == "":
        return None
    return value


def _provider_for_config(provider: str) -> str:
    if provider == "openai-compatible":
        return "openai"
    return provider


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compress individual clinical documents with an LLM.",
    )
    parser.add_argument("--config", help="Project YAML config. Uses extraction.llm and notes settings.")
    parser.add_argument("--notes-path", action="append", help="CSV/parquet notes file. Repeat for multiple files.")
    parser.add_argument("--output-dir", help="Directory for compressed_notes.csv/jsonl.")
    parser.add_argument("--output-prefix", default="compressed_notes")

    parser.add_argument(
        "--provider",
        default="openai",
        help="openai/openai-compatible, azure, anthropic, vertex, gemini.",
    )
    parser.add_argument("--model", default="gpt-oss-120b")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--vertex-project")
    parser.add_argument("--vertex-region", default="us-central1")
    parser.add_argument("--azure-api-version", default="2024-12-01-preview")
    parser.add_argument("--reasoning-marker")
    parser.add_argument("--timeout", type=int, default=300)

    parser.add_argument("--patient-id-column", default=None)
    parser.add_argument("--text-column", default=None)
    parser.add_argument("--date-column", default=None)
    parser.add_argument("--note-type-column", default=None)
    parser.add_argument("--document-id-column", default=None)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--limit", type=int, help="Only process the first N rows per notes file.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    project_config = load_config(args.config) if args.config else None
    if project_config:
        llm_config = project_config.extraction.llm
        llm_config.provider = _provider_for_config(llm_config.provider)
        notes_paths = args.notes_path or [str(p) for p in project_config.resolve_notes_files()]
        output_dir = args.output_dir or str(Path(project_config.output_dir) / "compressed_notes")
        patient_id_column = args.patient_id_column or project_config.extraction.patient_id_column
        text_column = args.text_column or project_config.extraction.notes_text_column
        date_column = args.date_column or project_config.extraction.notes_date_column
        note_type_column = args.note_type_column or project_config.extraction.notes_type_column
        max_workers = args.max_workers or project_config.extraction.patient_workers
        max_tokens = args.max_tokens or min(project_config.extraction.llm.max_tokens, 2048)
        temperature = (
            args.temperature
            if args.temperature is not None
            else project_config.extraction.llm.temperature
        )
    else:
        if not args.notes_path:
            parser.error("--notes-path is required when --config is not supplied")
        notes_paths = args.notes_path
        output_dir = args.output_dir or "compressed_notes"
        patient_id_column = args.patient_id_column or "patient_id"
        text_column = args.text_column or "text"
        date_column = args.date_column or "date"
        note_type_column = args.note_type_column or "note_type"
        max_workers = args.max_workers or 4
        max_tokens = args.max_tokens or 1024
        temperature = args.temperature if args.temperature is not None else 0.0
        llm_config = LLMConfig(
            provider=_provider_for_config(args.provider),
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            max_tokens=max_tokens,
            temperature=temperature,
            vertex_project=args.vertex_project,
            vertex_region=args.vertex_region,
            azure_api_version=args.azure_api_version,
            reasoning_marker=args.reasoning_marker,
            timeout=args.timeout,
        )

    if not notes_paths:
        raise ValueError("No notes files found. Provide --notes-path or extraction.notes_paths.")
    if llm_config.provider == "claude-code":
        raise ValueError("provider claude-code is handled by the compress-notes skill native mode, not this Python CLI.")

    client = create_llm_client(llm_config)

    all_results = []
    for notes_path in notes_paths:
        notes_df = load_notes_table(notes_path)
        if args.limit is not None:
            notes_df = notes_df.head(args.limit)
        result = compress_notes_dataframe(
            notes_df,
            client,
            patient_id_column=patient_id_column,
            text_column=text_column,
            date_column=date_column,
            note_type_column=note_type_column,
            document_id_column=args.document_id_column,
            source_file=str(notes_path),
            max_workers=max_workers,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        all_results.append(result)

    combined = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    csv_path, jsonl_path = write_outputs(combined, output_dir, args.output_prefix)
    errors = int(combined["error"].notna().sum()) if "error" in combined else 0
    print(f"Compressed {len(combined)} documents")
    print(f"Errors: {errors}")
    print(f"CSV: {csv_path}")
    print(f"JSONL: {jsonl_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
