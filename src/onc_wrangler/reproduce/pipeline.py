"""Parallel pipeline for reproduce-paper analysis and discrepancy phases.

Uses ThreadPoolExecutor for concurrent worker execution with
checkpoint/resume support via per-question/row JSON output files.
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from onc_wrangler.config import LLMConfig
from onc_wrangler.llm import create_llm_client

from .analysis_worker import run_analysis
from .discrepancy_worker import run_discrepancy

logger = logging.getLogger(__name__)


def run_analysis_phase(
    config: LLMConfig,
    questions: list[dict],
    data_context: str,
    data_dir: str,
    dict_dir: str,
    output_dir: str,
    num_workers: int = 5,
    max_turns: int = 30,
    max_tokens: int = 16384,
    temperature: float = 0.0,
    timeout: int = 120,
) -> list[dict]:
    """Run the analysis phase: one worker per question, in parallel.

    Each question dict must have at minimum a "question" key.
    Optionally an "index" key (int) for output file naming.

    Args:
        config: LLMConfig for creating per-worker LLM clients.
        questions: List of question dicts.
        data_context: Description of available data files.
        data_dir: Path to data files directory.
        dict_dir: Path to data dictionaries directory.
        output_dir: Directory for output JSON files.
        num_workers: Maximum concurrent workers.
        max_turns: Max agent loop iterations per worker.
        max_tokens: Max output tokens per LLM call.
        temperature: Sampling temperature.
        timeout: Timeout for Python script execution.

    Returns:
        List of result dicts (one per question, in input order).
    """
    os.makedirs(output_dir, exist_ok=True)
    results = [None] * len(questions)
    pending = []

    # Check for existing results (checkpoint/resume)
    for i, q in enumerate(questions):
        idx = q.get("index", i + 1)
        output_path = os.path.join(output_dir, f"q{idx:03d}_result.json")
        existing = _read_json(output_path)
        if existing is not None:
            logger.info("Skipping q%03d (checkpoint exists)", idx)
            results[i] = existing
        else:
            pending.append((i, idx, q, output_path))

    if not pending:
        logger.info("All %d questions already have results", len(questions))
        return results

    logger.info("Running %d analysis workers (%d already complete, %d workers max)",
                len(pending), len(questions) - len(pending), num_workers)

    def _run_one(item):
        i, idx, q, output_path = item
        # Each worker gets its own LLM client instance (thread safety)
        client = create_llm_client(config)
        logger.info("Starting analysis q%03d: %s", idx, q["question"][:80])
        result = run_analysis(
            client=client,
            question=q["question"],
            data_context=data_context,
            data_dir=data_dir,
            dict_dir=dict_dir,
            output_path=output_path,
            max_turns=max_turns,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        logger.info("Completed analysis q%03d", idx)
        return i, result

    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {pool.submit(_run_one, item): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            i, idx = item[0], item[1]
            try:
                result_i, result = future.result()
                results[result_i] = result
            except Exception as e:
                logger.error("Analysis q%03d failed: %s", idx, e)
                results[i] = {
                    "analysis_result": f"ERROR: {e}",
                    "denominator_used": "N/A",
                    "assumptions_made": "N/A",
                    "step_by_step_analysis": "Worker failed with exception",
                }

    completed = sum(1 for r in results if r is not None)
    logger.info("Analysis phase complete: %d/%d succeeded", completed, len(questions))
    return results


def run_discrepancy_phase(
    config: LLMConfig,
    rows: list[dict],
    data_context: str,
    data_dir: str,
    dict_dir: str,
    paper_pdf: str,
    paper_context: str,
    output_dir: str,
    num_workers: int = 5,
    max_turns: int = 30,
    max_tokens: int = 16384,
    temperature: float = 0.0,
    timeout: int = 120,
) -> list[dict]:
    """Run the discrepancy phase: one worker per comparison row, in parallel.

    Each row dict must have: question, reported_result, model_result,
    denominator, assumptions, step_by_step. Optionally an "index" key.

    Args:
        config: LLMConfig for creating per-worker LLM clients.
        rows: List of comparison row dicts.
        data_context: Description of available data files.
        data_dir: Path to data files directory.
        dict_dir: Path to data dictionaries directory.
        paper_pdf: Path to the paper PDF.
        paper_context: Summary of study design from the paper.
        output_dir: Directory for output JSON files.
        num_workers: Maximum concurrent workers.
        max_turns: Max agent loop iterations per worker.
        max_tokens: Max output tokens per LLM call.
        temperature: Sampling temperature.
        timeout: Timeout for Python script execution.

    Returns:
        List of result dicts (one per row, in input order).
    """
    os.makedirs(output_dir, exist_ok=True)
    results = [None] * len(rows)
    pending = []

    for i, row in enumerate(rows):
        idx = row.get("index", i + 1)
        output_path = os.path.join(output_dir, f"row_{idx:02d}.json")
        existing = _read_json(output_path)
        if existing is not None:
            logger.info("Skipping row_%02d (checkpoint exists)", idx)
            results[i] = existing
        else:
            pending.append((i, idx, row, output_path))

    if not pending:
        logger.info("All %d discrepancy rows already have results", len(rows))
        return results

    logger.info("Running %d discrepancy workers (%d already complete, %d workers max)",
                len(pending), len(rows) - len(pending), num_workers)

    def _run_one(item):
        i, idx, row, output_path = item
        client = create_llm_client(config)
        logger.info("Starting discrepancy row_%02d", idx)
        result = run_discrepancy(
            client=client,
            question=row["question"],
            reported_result=str(row["reported_result"]),
            model_result=str(row["model_result"]),
            denominator=str(row.get("denominator", "N/A")),
            assumptions=str(row.get("assumptions", "N/A")),
            step_by_step=str(row.get("step_by_step", "N/A")),
            paper_context=paper_context,
            data_dir=data_dir,
            dict_dir=dict_dir,
            paper_pdf=paper_pdf,
            output_path=output_path,
            max_turns=max_turns,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        logger.info("Completed discrepancy row_%02d", idx)
        return i, result

    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = {pool.submit(_run_one, item): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            i, idx = item[0], item[1]
            try:
                result_i, result = future.result()
                results[result_i] = result
            except Exception as e:
                logger.error("Discrepancy row_%02d failed: %s", idx, e)
                results[i] = {
                    "concordance_status": "ERROR",
                    "analysis_result": f"ERROR: {e}",
                    "discrepancy_analysis": "Worker failed with exception",
                    "discrepancy_magnitude": "N/A",
                    "root_cause_classification": "N/A",
                    "proposed_fix": "N/A",
                    "confidence": "N/A",
                }

    completed = sum(1 for r in results if r is not None)
    logger.info("Discrepancy phase complete: %d/%d succeeded", completed, len(rows))
    return results


def _read_json(path: str) -> dict | None:
    """Read a JSON file, returning None if it doesn't exist or is invalid."""
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None
