"""OpenAI-compatible LLM client for vLLM and similar servers."""

import json
import logging
import time
from typing import Optional

from openai import OpenAI, APIConnectionError, APITimeoutError, APIStatusError

from .base import LLMClient, LLMResponse

logger = logging.getLogger(__name__)


class VLLMClient(LLMClient):
    """Client for vLLM or any OpenAI-compatible API server.

    Used for PHI-containing extraction tasks where data cannot leave
    the local network.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "none",
        model: str = "gpt-oss-120b",
        reasoning_marker: Optional[str] = None,
        timeout: int = 300,
        max_retries: int = 3,
        initial_backoff: float = 2.0,
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.model = model
        self._reasoning_marker = reasoning_marker
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._json_mode_supported: Optional[bool] = None

    def _call_api(self, messages, temperature, max_tokens, response_format=None):
        """Call the API with retry and exponential backoff."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        last_exc = None
        for attempt in range(self._max_retries + 1):
            try:
                return self.client.chat.completions.create(**kwargs)
            except (APIConnectionError, APITimeoutError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    wait = self._initial_backoff * (2 ** attempt)
                    logger.warning(
                        "vLLM API %s (attempt %d/%d), retrying in %.1fs: %s",
                        type(exc).__name__, attempt + 1, self._max_retries + 1,
                        wait, exc,
                    )
                    time.sleep(wait)
            except APIStatusError as exc:
                last_exc = exc
                if exc.status_code >= 500 and attempt < self._max_retries:
                    wait = self._initial_backoff * (2 ** attempt)
                    logger.warning(
                        "vLLM API %d (attempt %d/%d), retrying in %.1fs: %s",
                        exc.status_code, attempt + 1, self._max_retries + 1,
                        wait, exc,
                    )
                    time.sleep(wait)
                else:
                    raise
        raise last_exc  # type: ignore[misc]

    def generate(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._call_api(messages, temperature, max_tokens)

        text = response.choices[0].message.content or ""
        if self._reasoning_marker:
            text = strip_reasoning(text, self._reasoning_marker)

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }

        return LLMResponse(text=text, usage=usage, raw=response)

    def generate_structured(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        """Generate JSON output using JSON mode when available."""
        json_system = (system + "\n\n" if system else "") + "You must respond with valid JSON only. No commentary."

        messages = []
        messages.append({"role": "system", "content": json_system})
        messages.append({"role": "user", "content": prompt})

        # Skip JSON mode when a reasoning marker is configured, because
        # response_format=json_object conflicts with vLLM's reasoning parser
        # (e.g., --reasoning-parser gemma4), causing mangled output.
        if self._json_mode_supported is not False and not self._reasoning_marker:
            try:
                response = self._call_api(
                    messages, temperature, max_tokens,
                    response_format={"type": "json_object"},
                )
                self._json_mode_supported = True
                raw_text = response.choices[0].message.content or ""
                text = raw_text
                if self._reasoning_marker:
                    text = strip_reasoning(text, self._reasoning_marker)
                    if len(text) < 20 and len(raw_text) > 100:
                        logger.warning(
                            "Reasoning strip left near-empty output (%d chars from %d). "
                            "Raw (last 500 chars): %s",
                            len(text), len(raw_text), raw_text[-500:],
                        )
                usage = None
                if response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                    }
                return LLMResponse(text=text, usage=usage, raw=response)
            except APIStatusError as exc:
                if exc.status_code == 400:
                    logger.warning(
                        "Server does not support response_format, falling back to prompt-only JSON enforcement"
                    )
                    self._json_mode_supported = False
                else:
                    raise

        # Fallback: prompt-only enforcement
        return self.generate(prompt, json_system, max_tokens, temperature)


def strip_reasoning(text: str, marker: str = "</think>") -> str:
    """Remove reasoning tokens before the final-answer marker.

    Handles multiple formats:
    1. Standard: <think>...</think>ANSWER  →  ANSWER
    2. Malformed (vLLM reasoning parser mangles tags): the content starts
       with "thought" followed by chain-of-thought, with the actual answer
       (often JSON) appearing at the end, possibly inside ```json blocks.
    """
    # Standard case: marker present
    if marker in text:
        return text.split(marker, 1)[-1].strip()

    # Malformed case: content starts with "thought" (mangled <think> tag)
    stripped = text.strip()
    if not stripped.lower().startswith("thought"):
        return text

    # Extract JSON from the end of the reasoning output.
    # The model typically puts the final JSON after its reasoning,
    # sometimes inside a ```json code block.
    import json as _json
    import re

    # First try: find the last ```json ... ``` block
    code_blocks = list(re.finditer(r"```(?:json)?\s*\n?([\s\S]*?)```", stripped))
    if code_blocks:
        # Take the last code block — earlier ones may be part of reasoning
        candidate = code_blocks[-1].group(1).strip()
        try:
            _json.loads(candidate)
            return candidate
        except _json.JSONDecodeError:
            pass

    # Second try: find the last JSON array or object
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        last_start = stripped.rfind(start_char)
        if last_start > 0:
            # Find the matching close
            last_end = stripped.rfind(end_char)
            if last_end > last_start:
                candidate = stripped[last_start:last_end + 1]
                try:
                    _json.loads(candidate)
                    return candidate
                except _json.JSONDecodeError:
                    pass

    return text
