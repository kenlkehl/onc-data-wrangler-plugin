"""Chunked/serial extraction for long patient note histories.

Splits patient text into token-based chunks and runs iterative extraction,
producing a running summary that is updated with each chunk.

Processing is organized into chunk-wise rounds: round 0 processes chunk 0
for all patients, round 1 processes chunk 1, etc. Raw JSON extractions are
saved per-round for crash-safe resume. Row-level parquet is only produced
after all rounds complete.
"""

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd

from ..llm.base import LLMClient
from .extractor import Extractor

logger = logging.getLogger(__name__)
APPROX_CHARS_PER_TOKEN = 4


def chunk_text_by_tokens(text: str, tokenizer, chunk_size: int = 40000, overlap: int = 200, boundary_marker: str = "\n--- ", boundary_window: int = 500) -> list[str]:
    """Split text into token-based chunks with overlap.

    Tries to split at document boundaries (e.g., note separators)
    when one falls within boundary_window tokens of the split point.

    Args:
        text: Full text to chunk.
        tokenizer: HuggingFace tokenizer instance.
        chunk_size: Maximum tokens per chunk.
        overlap: Overlap tokens between chunks.
        boundary_marker: String marking document boundaries.
        boundary_window: Token window to search for boundaries.

    Returns:
        List of text chunks.
    """
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    total = len(token_ids)
    chunks = []
    start = 0

    while start < total:
        end = min(start + chunk_size, total)

        # Try to find a boundary near the split point
        if end < total:
            search_start = max(start, end - boundary_window)
            window_text = tokenizer.decode(token_ids[search_start:end], skip_special_tokens=True)
            boundary_pos = window_text.rfind(boundary_marker)
            if boundary_pos != -1:
                pre_boundary = window_text[:boundary_pos]
                pre_tokens = tokenizer.encode(pre_boundary, add_special_tokens=False)
                end = search_start + len(pre_tokens)

        chunk_text = tokenizer.decode(token_ids[start:end], skip_special_tokens=True)
        chunks.append(chunk_text)
        if end >= total:
            break
        start = max(start + 1, end - overlap)

    return chunks


def chunk_text_by_chars(text: str, chunk_size_chars: int = 160000, overlap_chars: int = 800, boundary_marker: str = "\n--- ", boundary_window_chars: int = 2000) -> list[str]:
    """Split text into approximate character-based chunks with overlap.

    Used as a fallback when a tokenizer is unavailable. The default sizing
    mirrors the existing ``~4 chars/token`` heuristic already used by the
    standalone CLI.
    """
    if chunk_size_chars <= 0:
        return [text]

    total = len(text)
    chunks = []
    start = 0

    while start < total:
        end = min(start + chunk_size_chars, total)

        if end < total:
            search_start = max(start, end - boundary_window_chars)
            boundary_pos = text.rfind(boundary_marker, search_start, end)
            if boundary_pos > start:
                end = boundary_pos

        chunk_text = text[start:end]
        if not chunk_text:
            end = min(start + chunk_size_chars, total)
            chunk_text = text[start:end]

        chunks.append(chunk_text)
        if end >= total:
            break
        start = max(start + 1, end - overlap_chars)

    return chunks


def chunk_text(text: str, tokenizer=None, chunk_size: int = 40000, overlap: int = 200, boundary_marker: str = "\n--- ", boundary_window: int = 500) -> list[str]:
    """Chunk text by tokens when possible, else fall back to approximate chars."""
    if tokenizer:
        return chunk_text_by_tokens(
            text,
            tokenizer,
            chunk_size,
            overlap,
            boundary_marker,
            boundary_window,
        )

    return chunk_text_by_chars(
        text,
        chunk_size_chars=chunk_size * APPROX_CHARS_PER_TOKEN,
        overlap_chars=overlap * APPROX_CHARS_PER_TOKEN,
        boundary_marker=boundary_marker,
        boundary_window_chars=boundary_window * APPROX_CHARS_PER_TOKEN,
    )


def concatenate_patient_notes(patient_df: pd.DataFrame, text_column: str = "text", date_column: str = "date", type_column: str = "note_type") -> str:
    """Concatenate all notes for one patient chronologically.

    Args:
        patient_df: DataFrame with notes for one patient.
        text_column: Column containing note text.
        date_column: Column containing note date.
        type_column: Column containing note type.

    Returns:
        Concatenated text with note boundaries.
    """
    parts = []
    for _, row in patient_df.iterrows():
        note_type = str(row.get(type_column, "unknown")) if type_column in patient_df.columns else "unknown"
        date = str(row.get(date_column, "")) if date_column in patient_df.columns else ""
        text = str(row.get(text_column, ""))
        if len(text) < 10:
            continue
        parts.append("--- " + note_type + " | " + date + " ---\n" + text)
    return "\n\n".join(parts)


class ChunkedExtractor:
    """Chunked extraction pipeline for processing entire patient cohorts.

    Manages checkpointing, parallel processing, and iterative extraction.
    Processing is organized into chunk-wise rounds for crash-safe resume.
    """

    def __init__(self, extractor: Extractor, tokenizer=None, chunk_size: int = 40000, overlap: int = 200, max_retries: int = 10, patient_workers: int = 8, max_tokens: Optional[int] = 8000):
        self.extractor = extractor
        self.tokenizer = tokenizer
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.max_retries = max_retries
        self.patient_workers = patient_workers
        self.max_tokens = max_tokens

    def extract_patient(self, patient_id: str, patient_text: str) -> dict:
        """Run extraction for a single patient.

        Args:
            patient_id: Patient identifier.
            patient_text: Concatenated patient notes.

        Returns:
            Dict with patient_id, extractions list, and num_chunks.
        """
        chunks = chunk_text(
            patient_text,
            tokenizer=self.tokenizer,
            chunk_size=self.chunk_size,
            overlap=self.overlap,
        )
        logger.info("Patient %s: %d chunks", patient_id, len(chunks))
        extractions = self.extractor.extract_iterative(
            chunks,
            max_tokens=self.max_tokens,
            max_retries=self.max_retries,
        )
        return {"patient_id": patient_id, "extractions": extractions, "num_chunks": len(chunks)}

    def extract_cohort(self, notes_df: pd.DataFrame, output_dir: Path, patient_id_column: str = "record_id", text_column: str = "text", date_column: str = "date", type_column: str = "note_type", resume: bool = False) -> pd.DataFrame:
        """Extract data for an entire cohort using round-based processing.

        Processes all patients' chunk 0 first (round 0), then all patients'
        chunk 1 (round 1), etc. Raw JSON is saved per-round for crash-safe
        resume. Row-level parquet is only produced after all rounds complete.

        Args:
            notes_df: DataFrame with all patient notes.
            output_dir: Directory for round checkpoints and output.
            patient_id_column: Column with patient identifiers.
            text_column: Column with note text.
            date_column: Column with note dates.
            type_column: Column with note types.
            resume: Whether to resume from existing round files.

        Returns:
            DataFrame with all extractions in row-level format.
        """
        output_dir = Path(output_dir)
        ckpt = CheckpointManager(output_dir)

        # Phase 1: Pre-chunk all patients
        grouped = notes_df.sort_values(by=[patient_id_column]).reset_index(drop=True)
        patient_groups = dict(list(grouped.groupby(patient_id_column)))

        patient_chunks: dict[str, list[str]] = {}
        for pid, pdf in patient_groups.items():
            pid_str = str(pid)
            text = concatenate_patient_notes(pdf, text_column, date_column, type_column)
            chunks = chunk_text(
                text,
                tokenizer=self.tokenizer,
                chunk_size=self.chunk_size,
                overlap=self.overlap,
            )
            patient_chunks[pid_str] = chunks

        patient_num_chunks = {pid: len(chunks) for pid, chunks in patient_chunks.items()}
        all_ids = set(patient_chunks.keys())
        max_rounds = max(patient_num_chunks.values()) if patient_num_chunks else 0

        logger.info("Pre-chunked %d patients, max %d rounds", len(all_ids), max_rounds)

        # Phase 2: Resume detection
        if resume:
            resume_round, running_state = ckpt.determine_resume_state(all_ids, patient_num_chunks)
            logger.info("Resuming from round %d / %d", resume_round, max_rounds)
        else:
            ckpt.clean_old_artifacts()
            resume_round = 0
            running_state: dict[str, list] = {pid: [] for pid in all_ids}

        if resume_round >= max_rounds:
            logger.info("All rounds already complete.")
            return ckpt.build_final_output()

        # Phase 3: Round-by-round processing
        for round_idx in range(resume_round, max_rounds):
            active_pids = sorted(pid for pid in all_ids if patient_num_chunks[pid] > round_idx)
            if not active_pids:
                break

            # Check which patients are already done in this round (partial resume)
            round_progress = ckpt.load_round_completed(round_idx)
            pending_pids = [pid for pid in active_pids if pid not in round_progress]

            # Load any results already saved for this round into running_state
            if round_progress:
                round_data = ckpt.load_round(round_idx)
                for pid in round_progress:
                    if pid in all_ids and pid in round_data:
                        running_state[pid] = round_data[pid]["extraction"]

            if not pending_pids:
                logger.info("Round %d/%d: already complete (%d patients)", round_idx, max_rounds - 1, len(active_pids))
                continue

            logger.info("Round %d/%d: %d patients (%d already done, %d pending)",
                        round_idx, max_rounds - 1, len(active_pids),
                        len(active_pids) - len(pending_pids), len(pending_pids))

            processed_in_round = 0

            with ThreadPoolExecutor(max_workers=self.patient_workers) as executor:
                future_to_pid = {}
                for pid in pending_pids:
                    chunk_str = patient_chunks[pid][round_idx]
                    running = running_state[pid]
                    future = executor.submit(
                        self.extractor.extract_single_chunk,
                        chunk_text=chunk_str,
                        running=running,
                        chunk_index=round_idx,
                        total_chunks=patient_num_chunks[pid],
                        max_tokens=self.max_tokens,
                        max_retries=self.max_retries,
                    )
                    future_to_pid[future] = pid

                for future in as_completed(future_to_pid):
                    pid = future_to_pid[future]
                    try:
                        result = future.result()
                    except Exception:
                        logger.exception("Round %d, patient %s: extraction failed", round_idx, pid)
                        result = running_state[pid]

                    running_state[pid] = result
                    ckpt.append_round_result(round_idx, pid, result, patient_num_chunks[pid])
                    processed_in_round += 1

                    if processed_in_round % 50 == 0:
                        logger.info("Round %d progress: %d / %d", round_idx, processed_in_round, len(pending_pids))

            logger.info("Round %d complete: %d patients processed", round_idx, processed_in_round)

        # Phase 4: Finalize
        logger.info("All rounds complete. Building final output.")
        return ckpt.build_final_output()


class CheckpointManager:
    """Thread-safe checkpoint manager using per-round JSONL files.

    Each round produces a JSONL file (round_NNNN.jsonl) with one line per
    patient processed in that round. Row-level parquet is only produced
    at the end via build_final_output().
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def round_path(self, round_idx: int) -> Path:
        """Path to a round's JSONL file."""
        return self.output_dir / f"round_{round_idx:04d}.jsonl"

    def append_round_result(self, round_idx: int, patient_id: str, extraction: list, num_chunks: int):
        """Append one patient's result for a specific round (thread-safe)."""
        record = {
            "patient_id": patient_id,
            "round": round_idx,
            "extraction": extraction,
            "num_chunks": num_chunks,
        }
        with self._lock:
            with open(self.round_path(round_idx), "a") as f:
                f.write(json.dumps(record) + "\n")

    def load_round(self, round_idx: int) -> dict[str, dict]:
        """Load all results from a given round.

        Returns dict mapping patient_id -> full record dict.
        If a patient appears multiple times (e.g. partial re-run appended),
        the last entry wins.
        """
        path = self.round_path(round_idx)
        results: dict[str, dict] = {}
        if not path.exists():
            return results
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    results[str(record["patient_id"])] = record
                except (json.JSONDecodeError, KeyError):
                    pass
        return results

    def load_round_completed(self, round_idx: int) -> set[str]:
        """Load set of patient IDs that have results in a given round."""
        path = self.round_path(round_idx)
        completed: set[str] = set()
        if not path.exists():
            return completed
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    completed.add(str(record["patient_id"]))
                except (json.JSONDecodeError, KeyError):
                    pass
        return completed

    def find_round_files(self) -> list[int]:
        """Find all round indices that have JSONL files on disk."""
        rounds = []
        for path in self.output_dir.glob("round_*.jsonl"):
            try:
                idx = int(path.stem.split("_")[1])
                rounds.append(idx)
            except (IndexError, ValueError):
                pass
        return sorted(rounds)

    def determine_resume_state(self, all_patient_ids: set[str], patient_num_chunks: dict[str, int]) -> tuple[int, dict[str, list]]:
        """Determine where to resume from after a crash.

        Scans existing round files. A round is "complete" if every patient
        that needs processing in that round has a result. Walks forward
        through completed rounds to reconstruct running extraction state.

        Args:
            all_patient_ids: Set of all patient IDs in the cohort.
            patient_num_chunks: Dict mapping patient_id -> total chunk count.

        Returns:
            Tuple of (resume_round_index, running_state) where running_state
            maps patient_id -> extraction list from prior rounds.
        """
        running_state: dict[str, list] = {pid: [] for pid in all_patient_ids}
        existing_rounds = self.find_round_files()

        if not existing_rounds:
            return 0, running_state

        resume_from = 0

        for round_idx in existing_rounds:
            # Which patients should have been processed in this round?
            expected = {pid for pid in all_patient_ids if patient_num_chunks.get(pid, 1) > round_idx}
            round_data = self.load_round(round_idx)
            completed_in_round = set(round_data.keys()) & expected

            if completed_in_round == expected:
                # Round is fully complete -- update running state
                for pid in expected:
                    running_state[pid] = round_data[pid]["extraction"]
                resume_from = round_idx + 1
            else:
                # Round is partially complete -- will resume within this round
                # Update running state for patients that did complete
                for pid in completed_in_round:
                    running_state[pid] = round_data[pid]["extraction"]
                resume_from = round_idx
                break

        return resume_from, running_state

    def build_final_output(self) -> pd.DataFrame:
        """Convert final round extractions into row-level parquet.

        Reads all rounds, takes each patient's last extraction, flattens
        to row-level format, and saves as extractions.parquet.

        If all extractions are clinical summaries (free-text), saves as
        summaries.parquet with columns [patient_id, summary] instead.

        If all extractions are QA answers, saves as qa_results.parquet
        with columns [patient_id, question, value, confidence, evidence].
        """
        final_extractions = self.load_final_extractions()
        if not final_extractions:
            return pd.DataFrame()

        # Check extraction type
        if _is_summary_extraction(final_extractions):
            return self._build_summary_output(final_extractions)
        if _is_qa_extraction(final_extractions):
            return self._build_qa_output(final_extractions)
        return self._build_structured_output(final_extractions)

    def load_final_extractions(self) -> dict[str, list]:
        """Collect each patient's last extraction state across all rounds."""
        final_extractions: dict[str, list] = {}
        for round_idx in self.find_round_files():
            round_data = self.load_round(round_idx)
            for pid, record in round_data.items():
                final_extractions[pid] = record["extraction"]
        return final_extractions

    def _build_summary_output(self, final_extractions: dict[str, list]) -> pd.DataFrame:
        """Build output for free-text summary extractions."""
        from .extractor import _unwrap_summary

        rows = []
        for patient_id, extraction in final_extractions.items():
            summary = _unwrap_summary(extraction)
            rows.append({"patient_id": patient_id, "summary": summary})

        df = pd.DataFrame(rows)
        out_path = self.output_dir / "summaries.parquet"
        df.to_parquet(out_path, index=False)
        logger.info("Saved summaries %s (%d patients)", out_path, len(df))
        return df

    def _build_qa_output(self, final_extractions: dict[str, list]) -> pd.DataFrame:
        """Build output for clinical QA extractions."""
        from .qa_extractor import _unwrap_qa

        rows = []
        for patient_id, extraction in final_extractions.items():
            answers = _unwrap_qa(extraction)
            for question, ans in answers.items():
                rows.append({
                    "patient_id": patient_id,
                    "question": question,
                    "value": ans.get("value", ""),
                    "confidence": ans.get("confidence", 0),
                    "evidence": ans.get("evidence", ""),
                })

        df = pd.DataFrame(rows)
        out_path = self.output_dir / "qa_results.parquet"
        df.to_parquet(out_path, index=False)
        logger.info("Saved QA results %s (%d rows)", out_path, len(df))
        return df

    def _build_structured_output(self, final_extractions: dict[str, list]) -> pd.DataFrame:
        """Build output for structured JSON extractions.

        Handles multi-diagnosis format (with ``_diagnoses`` key),
        multi-instance format (with ``_multi_instance`` key for regimens etc.),
        and legacy single-diagnosis format.
        """
        rows = []
        for patient_id, extraction in final_extractions.items():
            has_diagnoses = False

            for ext in extraction:
                if not isinstance(ext, dict):
                    continue

                # Multi-diagnosis: per-diagnosis rows
                if "_diagnoses" in ext:
                    has_diagnoses = True
                    for diag_entry in ext["_diagnoses"]:
                        tumor_idx = diag_entry.get("tumor_index", 0)
                        for category, attrs in diag_entry.items():
                            if category == "tumor_index" or not isinstance(attrs, dict):
                                continue
                            row = {
                                "patient_id": patient_id,
                                "tumor_index": tumor_idx,
                                "category": category,
                            }
                            for k, v in attrs.items():
                                if isinstance(v, list):
                                    row[k] = "; ".join(str(item) for item in v)
                                else:
                                    row[k] = v
                            rows.append(row)
                    continue

                # Multi-instance: one row per instance (regimens, assessments)
                if "_multi_instance" in ext:
                    for mi_key, instances in ext["_multi_instance"].items():
                        # mi_key format: "{tumor_index}_{group_id}"
                        parts = mi_key.split("_", 1)
                        tumor_idx = int(parts[0]) if parts[0].isdigit() else 0
                        category = parts[1] if len(parts) > 1 else mi_key
                        for instance_idx, instance in enumerate(instances):
                            if not isinstance(instance, dict):
                                continue
                            row = {
                                "patient_id": patient_id,
                                "tumor_index": tumor_idx,
                                "category": category,
                                "instance_index": instance_idx,
                            }
                            for k, v in instance.items():
                                if isinstance(v, list):
                                    row[k] = "; ".join(str(item) for item in v)
                                else:
                                    row[k] = v
                            rows.append(row)
                    continue

                # Patient-level fields (from multi-diagnosis) or
                # legacy single-diagnosis format
                if len(ext) == 1:
                    category = next(iter(ext))
                    if category.startswith("_"):
                        continue
                    attrs = ext[category]
                    if not isinstance(attrs, dict):
                        continue
                    row = {"patient_id": patient_id, "category": category}
                    if has_diagnoses:
                        row["tumor_index"] = -1  # Sentinel for patient-level
                    for k, v in attrs.items():
                        if isinstance(v, list):
                            row[k] = "; ".join(str(item) for item in v)
                        else:
                            row[k] = v
                    rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        # Coerce mixed-type object columns to strings so PyArrow can serialize
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(lambda x: str(x) if x is not None and not isinstance(x, str) else x)
        out_path = self.output_dir / "extractions.parquet"
        df.to_parquet(out_path, index=False)
        logger.info("Saved final output %s (%d rows from %d patients)",
                     out_path, len(df), len(final_extractions))
        return df

    def clean_old_artifacts(self):
        """Remove legacy and stale files for a fresh run."""
        legacy = self.output_dir / "checkpoint.jsonl"
        if legacy.exists():
            legacy.unlink()
        for shard in self.output_dir.glob("shard_*.parquet"):
            shard.unlink()
        for name in ("extractions.parquet", "summaries.parquet", "qa_results.parquet"):
            out = self.output_dir / name
            if out.exists():
                out.unlink()
        for rnd in self.output_dir.glob("round_*.jsonl"):
            rnd.unlink()


def _is_summary_extraction(final_extractions: dict[str, list]) -> bool:
    """Check if extractions are all clinical summaries."""
    for extraction in final_extractions.values():
        for entry in extraction:
            if isinstance(entry, dict) and "clinical_summary" in entry:
                return True
            return False  # First non-summary entry means structured
    return False


def _is_qa_extraction(final_extractions: dict[str, list]) -> bool:
    """Check if extractions are clinical QA answers."""
    for extraction in final_extractions.values():
        for entry in extraction:
            if isinstance(entry, dict) and "_qa_answers" in entry:
                return True
            return False
    return False
