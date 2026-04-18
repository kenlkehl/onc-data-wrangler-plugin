"""Clinical question-answering extractor.

Answers a list of free-form clinical questions per patient by processing
their notes through an LLM.  Questions are loaded from a simple text file
(one per line, optionally with valid answer options in trailing parentheses
delimited by semicolons).

The ``QAExtractor`` class implements the same ``extract_single_chunk`` /
``extract_iterative`` interface used by ``Extractor`` and
``SummaryExtractor``, so it plugs directly into ``ChunkedExtractor`` for
round-based parallel processing.

Ported from ``bpc_breast_feasibility/clinical_qa.py``.
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Optional

from ..llm.base import LLMClient
from .extractor import parse_json_object

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Question parsing
# ---------------------------------------------------------------------------

_OPTIONS_RE = re.compile(r"\s*\(([^)]+)\)\s*$")


def parse_questions(path: str) -> list[dict]:
    """Parse questions file.

    Each line is a question, optionally with valid options in trailing
    parentheses delimited by semicolons.

    Example lines::

        What is the PD-L1 value? (0%; 1-49%; 50%+; unknown/not recorded)
        What is the patient's age at diagnosis?

    Returns list of {"question": str, "options": list[str] | None}.
    """
    questions = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _OPTIONS_RE.search(line)
            if m:
                q_text = line[: m.start()].strip()
                options = [o.strip() for o in m.group(1).split(";") if o.strip()]
                questions.append({"question": q_text, "options": options})
            else:
                questions.append({"question": line, "options": None})
    if not questions:
        raise ValueError(f"No questions found in {path}")
    logger.info("Loaded %d questions from %s", len(questions), path)
    return questions


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

QA_SYSTEM_PROMPT = """\
You are an expert clinical data abstractor with deep knowledge of oncology, \
medical terminology, and clinical documentation. Your task is to answer clinical \
questions by extracting information from patient medical records.

TASK: Read the provided clinical notes and answer each question based ONLY on \
information found in the text. Do not infer or assume information not explicitly stated.

RULES:
1. For each question, provide:
   - "value": your answer (be specific and concise)
   - "confidence": a float 0.0-1.0 indicating how confident you are
   - "evidence": a direct quote (max 200 chars) from the text supporting your answer
2. If information is not found, set value to "Not documented", confidence to 0.0, \
and evidence to "".
3. If you are updating a prior answer, only change it if the current text provides \
STRONGER evidence or a MORE SPECIFIC answer.
4. For questions with listed valid options, you MUST choose one of those options as \
your value. For open-ended questions, provide a concise free-text answer.
5. Confidence guidelines:
   - 0.9-1.0: Explicitly and clearly stated in the text
   - 0.7-0.89: Strongly implied or stated with some ambiguity
   - 0.4-0.69: Partially supported, requires some inference
   - 0.0-0.39: Weak or no evidence

Respond with ONLY a valid JSON object. No markdown fences, no commentary, no explanation."""

QA_USER_PROMPT_TEMPLATE = """\
Clinical notes:
---
{chunk_text}
---

{prior_state_block}

Answer the following questions. Respond with a JSON object where each key is the \
exact question text and the value is an object with "value", "confidence", and "evidence" fields.

{questions_block}"""


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def build_questions_block(questions: list[dict]) -> str:
    """Format questions for the user prompt."""
    lines = []
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q['question']}")
        if q["options"]:
            lines.append(f"   Valid answers: {'; '.join(q['options'])}")
    return "\n".join(lines)


def build_qa_prior_state(answers: dict) -> str:
    """Format prior answers for iterative refinement."""
    if not answers:
        return "No prior answers -- this is the first chunk of text."
    lines = ["PRIOR ANSWERS (update only with higher-confidence evidence):"]
    for question, ans in answers.items():
        conf = ans.get("confidence", 0)
        if conf <= 0:
            continue
        lines.append(f'- "{question}": {ans.get("value", "")} (confidence: {conf:.2f})')
    if len(lines) == 1:
        return "No prior answers -- this is the first chunk of text."
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Answer merging and key normalization
# ---------------------------------------------------------------------------


def merge_qa_answers(existing: dict, new_answers: dict) -> dict:
    """Merge new answers into existing.  Higher confidence wins."""
    merged = dict(existing)
    for question, answer in new_answers.items():
        if not isinstance(answer, dict):
            continue
        new_conf = answer.get("confidence", 0)
        if question not in merged:
            merged[question] = answer
        elif new_conf > merged[question].get("confidence", 0):
            merged[question] = answer
    return merged


def normalize_qa_keys(parsed: dict, question_texts: list[str]) -> dict:
    """Map LLM response keys back to canonical question texts.

    Handles exact match, case-insensitive match, and substring matching.
    """
    normalized: dict = {}
    question_lower = {q.lower(): q for q in question_texts}

    for key, val in parsed.items():
        if key.startswith("_"):
            continue
        if key in question_texts:
            normalized[key] = val
        elif key.lower() in question_lower:
            normalized[question_lower[key.lower()]] = val
        else:
            for qt in question_texts:
                if qt.lower() in key.lower() or key.lower() in qt.lower():
                    normalized[qt] = val
                    break
    return normalized


# ---------------------------------------------------------------------------
# State wrappers  (mirror _wrap_summary / _unwrap_summary)
# ---------------------------------------------------------------------------


def _wrap_qa(answers: dict) -> list[dict]:
    return [{"_qa_answers": answers}]


def _unwrap_qa(running: Optional[list[dict]]) -> dict:
    if not running:
        return {}
    for entry in running:
        if isinstance(entry, dict) and "_qa_answers" in entry:
            return entry["_qa_answers"]
    return {}


def is_qa_extraction(final_extractions: dict) -> bool:
    """Check whether final_extractions were produced by QAExtractor."""
    for extraction in final_extractions.values():
        for entry in extraction:
            if isinstance(entry, dict) and "_qa_answers" in entry:
                return True
        break  # only need to check one patient
    return False


# ---------------------------------------------------------------------------
# QAExtractor
# ---------------------------------------------------------------------------


class QAExtractor:
    """Question-driven clinical data extraction.

    Implements the same ``extract_single_chunk`` / ``extract_iterative``
    interface as ``Extractor`` and ``SummaryExtractor`` so it can be used
    with ``ChunkedExtractor`` unchanged.
    """

    def __init__(self, llm_client: LLMClient, questions: list[dict]):
        self.llm_client = llm_client
        self.questions = questions
        self._question_texts = [q["question"] for q in questions]

    def extract_from_text(
        self,
        text: str,
        cancer_type: Optional[str] = None,
        max_tokens: Optional[int] = 16384,
    ) -> list[dict]:
        """Answer questions from a single text document."""
        return self.extract_single_chunk(text, [], 0, 1, cancer_type, max_tokens)

    def extract_single_chunk(
        self,
        chunk_text: str,
        running: Optional[list[dict]] = None,
        chunk_index: int = 0,
        total_chunks: int = 1,
        cancer_type: Optional[str] = None,
        max_tokens: Optional[int] = 16384,
        max_retries: int = 3,
    ) -> list[dict]:
        """Process one chunk: call LLM, parse response, merge answers."""
        current_answers = _unwrap_qa(running)

        prior_block = build_qa_prior_state(current_answers)
        questions_block = build_questions_block(self.questions)

        user_prompt = QA_USER_PROMPT_TEMPLATE.format(
            chunk_text=chunk_text,
            prior_state_block=prior_block,
            questions_block=questions_block,
        )

        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate_structured(
                    user_prompt,
                    system=QA_SYSTEM_PROMPT,
                    max_tokens=max_tokens,
                    temperature=0.0,
                )
                parsed = parse_json_object(response.text)
                if parsed is None:
                    logger.warning(
                        "Chunk %d/%d attempt %d: failed to parse JSON",
                        chunk_index + 1,
                        total_chunks,
                        attempt + 1,
                    )
                    continue

                normalized = normalize_qa_keys(parsed, self._question_texts)
                merged = merge_qa_answers(current_answers, normalized)
                return _wrap_qa(merged)

            except Exception:
                logger.exception(
                    "Chunk %d/%d attempt %d: LLM call failed",
                    chunk_index + 1,
                    total_chunks,
                    attempt + 1,
                )

        logger.warning(
            "Chunk %d/%d: all %d retries failed, keeping prior answers",
            chunk_index + 1,
            total_chunks,
            max_retries,
        )
        return _wrap_qa(current_answers)

    def extract_iterative(
        self,
        texts: list[str],
        cancer_type: Optional[str] = None,
        max_tokens: Optional[int] = 16384,
        max_retries: int = 3,
    ) -> list[dict]:
        """Process multiple chunks sequentially, refining answers."""
        running: list[dict] = []
        for i, chunk_text in enumerate(texts):
            running = self.extract_single_chunk(
                chunk_text, running, i, len(texts), cancer_type, max_tokens, max_retries,
            )
        return running


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def build_qa_output(final_extractions: dict, output_path: Path) -> None:
    """Write JSONL and CSV from QA extraction results.

    Args:
        final_extractions: Dict mapping patient_id -> extraction list
            (as returned by ``CheckpointManager.load_final_extractions``).
        output_path: Path for the JSONL file.  CSV is written alongside.
    """
    output_path = Path(output_path)

    # --- JSONL ---
    with open(output_path, "w") as f:
        for patient_id, extraction in final_extractions.items():
            answers = _unwrap_qa(extraction)
            record = {"patient_id": patient_id, "answers": answers}
            f.write(json.dumps(record) + "\n")
    logger.info("JSONL written: %s (%d patients)", output_path, len(final_extractions))

    # --- CSV (one row per patient, one column per question) ---
    all_questions: list[str] = []
    seen: set[str] = set()
    for extraction in final_extractions.values():
        answers = _unwrap_qa(extraction)
        for q in answers:
            if q not in seen:
                all_questions.append(q)
                seen.add(q)

    csv_path = output_path.with_suffix(".csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        header = ["patient_id"] + all_questions
        writer.writerow(header)
        for patient_id, extraction in final_extractions.items():
            answers = _unwrap_qa(extraction)
            row = [patient_id]
            for q in all_questions:
                ans = answers.get(q, {})
                row.append(ans.get("value", "") if isinstance(ans, dict) else "")
            writer.writerow(row)
    logger.info("CSV written: %s (%d patients, %d questions)", csv_path, len(final_extractions), len(all_questions))
