"""Analysis worker: runs a single research question through the agentic loop."""

import json
import logging
import os
from pathlib import Path

from onc_wrangler.agent import AgentLoop
from onc_wrangler.llm.base import LLMClient

from .prompts import build_analysis_system_prompt, build_analysis_user_prompt

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = {"analysis_result", "denominator_used", "assumptions_made", "step_by_step_analysis"}


def _extract_json_from_text(text: str) -> dict | None:
    """Try to extract a JSON object from the agent's final text response."""
    # Try the whole text first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to find JSON between ```json ... ``` or { ... }
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


def run_analysis(
    client: LLMClient,
    question: str,
    data_context: str,
    data_dir: str,
    dict_dir: str,
    output_path: str,
    max_turns: int = 30,
    max_tokens: int = 16384,
    temperature: float = 0.0,
    timeout: int = 120,
) -> dict:
    """Run a single analysis question through the agentic loop.

    Args:
        client: LLM client instance.
        question: The research question to answer.
        data_context: Description of available data files.
        data_dir: Path to the data files directory.
        dict_dir: Path to the data dictionaries directory.
        output_path: Path where the result JSON should be written.
        max_turns: Maximum agent loop iterations.
        max_tokens: Max output tokens per LLM call.
        temperature: Sampling temperature.
        timeout: Timeout for Python script execution.

    Returns:
        Parsed result dict, or error dict if the agent failed.
    """
    system_prompt = build_analysis_system_prompt()
    user_prompt = build_analysis_user_prompt(
        question=question,
        data_context=data_context,
        data_dir=data_dir,
        dict_dir=dict_dir,
        output_path=output_path,
    )

    # Determine allowed directories and work directory
    output_dir = str(Path(output_path).parent)
    os.makedirs(output_dir, exist_ok=True)
    allowed_dirs = [data_dir, dict_dir, output_dir]

    loop = AgentLoop(
        llm_client=client,
        system_prompt=system_prompt,
        max_turns=max_turns,
        allowed_dirs=allowed_dirs,
        work_dir=output_dir,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )

    final_text = loop.run(user_prompt)

    # Try to read the output file the agent should have written
    result = _read_output_file(output_path)
    if result is not None:
        return result

    # Fallback: try to extract JSON from the agent's final text
    logger.warning("Output file not found at %s, extracting from text", output_path)
    result = _extract_json_from_text(final_text)
    if result is not None:
        # Write it to the expected path for the pipeline
        os.makedirs(Path(output_path).parent, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    # Complete failure
    logger.error("Agent failed to produce valid output for question: %s", question[:100])
    error_result = {
        "analysis_result": "ERROR: Agent did not produce valid output",
        "denominator_used": "N/A",
        "assumptions_made": "N/A",
        "step_by_step_analysis": final_text[:5000] if final_text else "No output",
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
