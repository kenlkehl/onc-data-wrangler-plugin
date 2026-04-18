"""Discrepancy worker: investigates root causes of result differences."""

import json
import logging
import os
from pathlib import Path

from onc_wrangler.agent import AgentLoop
from onc_wrangler.agent.tools import ALL_TOOLS
from onc_wrangler.llm.base import LLMClient

from .prompts import build_discrepancy_system_prompt, build_discrepancy_user_prompt

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = {
    "concordance_status", "analysis_result", "discrepancy_analysis",
    "discrepancy_magnitude", "root_cause_classification",
    "proposed_fix", "confidence",
}


def _extract_json_from_text(text: str) -> dict | None:
    """Try to extract a JSON object from the agent's final text response."""
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass

    import re
    for pattern in [r"```json\s*\n(.*?)\n\s*```", r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(1))
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, TypeError):
                continue
    return None


def run_discrepancy(
    client: LLMClient,
    question: str,
    reported_result: str,
    model_result: str,
    denominator: str,
    assumptions: str,
    step_by_step: str,
    paper_context: str,
    data_dir: str,
    dict_dir: str,
    paper_pdf: str,
    output_path: str,
    max_turns: int = 30,
    max_tokens: int = 16384,
    temperature: float = 0.0,
    timeout: int = 120,
) -> dict:
    """Run a single discrepancy analysis through the agentic loop.

    Returns:
        Parsed result dict, or error dict if the agent failed.
    """
    system_prompt = build_discrepancy_system_prompt()
    user_prompt = build_discrepancy_user_prompt(
        question=question,
        reported_result=reported_result,
        model_result=model_result,
        denominator=denominator,
        assumptions=assumptions,
        step_by_step=step_by_step,
        paper_context=paper_context,
        data_dir=data_dir,
        dict_dir=dict_dir,
        paper_pdf=paper_pdf,
        output_path=output_path,
    )

    output_dir = str(Path(output_path).parent)
    os.makedirs(output_dir, exist_ok=True)
    paper_pdf_dir = str(Path(paper_pdf).parent) if paper_pdf else output_dir
    allowed_dirs = [data_dir, dict_dir, output_dir, paper_pdf_dir]

    loop = AgentLoop(
        llm_client=client,
        system_prompt=system_prompt,
        tools=ALL_TOOLS,
        max_turns=max_turns,
        allowed_dirs=allowed_dirs,
        work_dir=output_dir,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )

    final_text = loop.run(user_prompt)

    # Try to read the output file
    result = _read_output_file(output_path)
    if result is not None:
        return result

    # Fallback: extract from text
    logger.warning("Output file not found at %s, extracting from text", output_path)
    result = _extract_json_from_text(final_text)
    if result is not None:
        os.makedirs(Path(output_path).parent, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    # Complete failure
    logger.error("Discrepancy agent failed for question: %s", question[:100])
    error_result = {
        "concordance_status": "ERROR",
        "analysis_result": "ERROR: Agent did not produce valid output",
        "discrepancy_analysis": final_text[:5000] if final_text else "No output",
        "discrepancy_magnitude": "N/A",
        "root_cause_classification": "N/A",
        "proposed_fix": "N/A",
        "confidence": "N/A",
    }
    with open(output_path, "w") as f:
        json.dump(error_result, f, indent=2)
    return error_result


def _read_output_file(path: str) -> dict | None:
    """Read and validate the output JSON file."""
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and _REQUIRED_KEYS.issubset(data.keys()):
            return data
        if isinstance(data, dict):
            logger.warning("Output file missing keys: %s", _REQUIRED_KEYS - data.keys())
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None
