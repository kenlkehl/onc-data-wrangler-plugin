"""Google Gemini client supporting Vertex AI and AI Studio."""

import logging
import os
import time
from typing import Optional

from .base import LLMClient, LLMResponse

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    """Client for Google Gemini (Vertex AI or AI Studio).

    Auto-detects mode based on configuration:
    - If vertex_project is set: Vertex AI with Application Default Credentials
    - Otherwise: AI Studio with GOOGLE_API_KEY

    Args:
        model: Model identifier (e.g., "gemini-3-flash-preview").
        vertex_project: GCP project ID (for Vertex AI mode).
        vertex_region: GCP region/location (for Vertex AI mode).
        api_key: Google AI Studio API key (for AI Studio mode).
        max_retries: Maximum retry attempts for transient errors.
        initial_backoff: Initial backoff in seconds before first retry.
    """

    def __init__(
        self,
        model: str = "gemini-3-flash-preview",
        vertex_project: Optional[str] = None,
        vertex_region: str = "us-east5",
        api_key: Optional[str] = None,
        max_retries: int = 3,
        initial_backoff: float = 2.0,
    ):
        from google import genai

        self.model = model
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff

        if vertex_project:
            self.client = genai.Client(
                vertexai=True,
                project=vertex_project,
                location=vertex_region,
            )
            self._mode = "vertex"
        else:
            api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
            self.client = genai.Client(api_key=api_key)
            self._mode = "ai_studio"

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """Check if an exception is transient and worth retrying."""
        try:
            from google.api_core.exceptions import (
                InternalServerError,
                ResourceExhausted,
                ServiceUnavailable,
                TooManyRequests,
            )
            if isinstance(exc, (ServiceUnavailable, ResourceExhausted,
                                InternalServerError, TooManyRequests)):
                return True
        except ImportError:
            pass
        exc_name = type(exc).__name__.lower()
        return any(s in exc_name for s in ("timeout", "connection", "unavailable"))

    def _call_api(self, prompt: str, system: str, max_tokens: int,
                  temperature: float, response_mime_type: Optional[str] = None):
        """Call Gemini API with retry and exponential backoff."""
        from google.genai.types import GenerateContentConfig

        config_kwargs = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            config_kwargs["system_instruction"] = system
        if response_mime_type:
            config_kwargs["response_mime_type"] = response_mime_type

        config = GenerateContentConfig(**config_kwargs)

        last_exc = None
        for attempt in range(self._max_retries + 1):
            try:
                return self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
            except Exception as exc:
                last_exc = exc
                if self._is_retryable(exc) and attempt < self._max_retries:
                    wait = self._initial_backoff * (2 ** attempt)
                    logger.warning(
                        "Gemini API %s (attempt %d/%d), retrying in %.1fs: %s",
                        type(exc).__name__, attempt + 1,
                        self._max_retries + 1, wait, exc,
                    )
                    time.sleep(wait)
                else:
                    raise
        raise last_exc  # type: ignore[misc]

    def _extract_text(self, response) -> str:
        """Safely extract text from a Gemini response."""
        try:
            return response.text or ""
        except (ValueError, AttributeError):
            logger.warning("Gemini response contained no text candidates")
            return ""

    def _extract_usage(self, response) -> Optional[dict[str, int]]:
        """Extract token usage from a Gemini response."""
        if response.usage_metadata:
            return {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
            }
        return None

    def generate(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        response = self._call_api(prompt, system, max_tokens, temperature)
        return LLMResponse(
            text=self._extract_text(response),
            usage=self._extract_usage(response),
            raw=response,
        )

    def generate_structured(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        """Generate JSON output using Gemini's native JSON mode."""
        json_system = (system + "\n\n" if system else "") + "You must respond with valid JSON only. No commentary."
        response = self._call_api(
            prompt, json_system, max_tokens, temperature,
            response_mime_type="application/json",
        )
        return LLMResponse(
            text=self._extract_text(response),
            usage=self._extract_usage(response),
            raw=response,
        )
