"""Azure OpenAI LLM client."""

import logging
import os
import subprocess
import threading
import time
from typing import Optional

from openai import APIStatusError, AuthenticationError, OpenAI, RateLimitError

from .base import LLMClient, LLMResponse
from .vllm_client import strip_reasoning

logger = logging.getLogger(__name__)

# Rate-limiting defaults
_DEFAULT_MIN_REQUEST_INTERVAL = 5.0  # seconds between requests (across all threads)
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_INITIAL_BACKOFF = 10.0  # seconds
_RATE_LIMIT_COOLDOWN = 30.0  # seconds to globally back off after a rate-limit error

_TOKEN_REFRESH_INTERVAL = 20 * 60  # seconds
_TOKEN_REFRESH_CMD = [
    "az", "account", "get-access-token",
    "--resource=https://cognitiveservices.azure.com/",
    "--query", "accessToken",
    "--output", "tsv",
]


def _fetch_azure_token() -> Optional[str]:
    """Run ``az`` CLI to get a fresh Azure AD token.  Returns None on failure."""
    try:
        result = subprocess.run(
            _TOKEN_REFRESH_CMD,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            if token:
                return token
        logger.warning("az token refresh failed (exit %d): %s",
                       result.returncode, result.stderr.strip())
    except Exception:
        logger.warning("az token refresh command failed", exc_info=True)
    return None


class AzureClient(LLMClient):
    """Client for Azure OpenAI Service.

    Args:
        azure_endpoint: Azure OpenAI endpoint URL.
        api_key: Azure OpenAI API key.
        model: Azure deployment name.
        api_version: Azure API version string.
    """

    def __init__(
        self,
        azure_endpoint: str = "",
        api_key: str = "",
        model: str = "gpt-4o",
        api_version: str = "2024-12-01-preview",
        min_request_interval: float = _DEFAULT_MIN_REQUEST_INTERVAL,
    ):
        api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY", "")
        azure_endpoint = azure_endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self.client = OpenAI(
            base_url=azure_endpoint,
            api_key=api_key,
            #api_version=api_version,
        )
        self.model = model
        self._min_request_interval = min_request_interval
        self._last_request_time = 0.0
        self._rate_limit_until = 0.0  # monotonic deadline; all threads wait until this clears
        self._throttle_lock = threading.Lock()
        self._start_token_refresh()

    _TOKEN_ERROR_PHRASES = (
        "access token",
        "token is missing",
        "token expired",
        "invalid token",
        "unauthorized",
    )

    def _is_token_error(self, exc: Exception) -> bool:
        """Return True if *exc* indicates an expired / missing access token."""
        if isinstance(exc, AuthenticationError):
            return True
        if isinstance(exc, APIStatusError):
            msg = str(exc).lower()
            return any(phrase in msg for phrase in self._TOKEN_ERROR_PHRASES)
        return False

    def _refresh_token(self):
        """Fetch a fresh Azure AD token and update the client and environment."""
        token = _fetch_azure_token()
        if token:
            self.client.api_key = token
            os.environ["AZURE_OPENAI_API_KEY"] = token
            logger.info("Azure AD token refreshed")
        return token

    def _start_token_refresh(self):
        """Fetch a token immediately, then start a daemon thread to refresh every 45 min."""
        self._refresh_token()

        def _loop():
            while True:
                time.sleep(_TOKEN_REFRESH_INTERVAL)
                self._refresh_token()

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        logger.info("Azure token refresh thread started (every %d min)",
                     _TOKEN_REFRESH_INTERVAL // 60)

    def _throttle(self):
        """Enforce minimum interval between requests across all threads.

        After a rate-limit error, ``_rate_limit_until`` pushes *all* threads
        back so the service has time to recover.
        """
        with self._throttle_lock:
            now = time.monotonic()
            # If a rate-limit cooldown is active, wait for it first
            if now < self._rate_limit_until:
                cooldown_wait = self._rate_limit_until - now
                logger.info("Rate-limit cooldown active, waiting %.1fs", cooldown_wait)
                time.sleep(cooldown_wait)
                now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_request_interval:
                wait = self._min_request_interval - elapsed
                logger.debug("Throttling Azure request for %.1fs", wait)
                time.sleep(wait)
            self._last_request_time = time.monotonic()

    def generate(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "input": prompt,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system:
            kwargs["instructions"] = system

        backoff = _DEFAULT_INITIAL_BACKOFF
        token_retries = 0
        _MAX_TOKEN_RETRIES = 2
        for attempt in range(_DEFAULT_MAX_RETRIES):
            self._throttle()
            try:
                response = self.client.responses.create(**kwargs)
                break
            except RateLimitError as e:
                if attempt == _DEFAULT_MAX_RETRIES - 1:
                    logger.error("Azure rate limit exceeded after %d retries", attempt + 1)
                    raise
                retry_after = getattr(e.response, "headers", {}).get("retry-after")
                wait = float(retry_after) if retry_after else backoff
                # Set a global cooldown so other threads also back off
                self._rate_limit_until = time.monotonic() + wait
                logger.warning(
                    "Azure rate limit hit (attempt %d/%d), waiting %.1fs before retry "
                    "(global cooldown set for all threads)",
                    attempt + 1, _DEFAULT_MAX_RETRIES, wait,
                )
                time.sleep(wait)
                backoff *= 2  # exponential backoff
            except (AuthenticationError, APIStatusError) as e:
                if not self._is_token_error(e):
                    raise
                token_retries += 1
                if token_retries > _MAX_TOKEN_RETRIES:
                    logger.error(
                        "Access-token error persists after %d refresh attempts, giving up",
                        _MAX_TOKEN_RETRIES,
                    )
                    raise
                logger.warning(
                    "Access-token error detected (attempt %d/%d): %s — refreshing token",
                    token_retries, _MAX_TOKEN_RETRIES, e,
                )
                refreshed = self._refresh_token()
                if not refreshed:
                    logger.error("Token refresh failed, cannot retry")
                    raise

        text = response.output_text or ""
        text = strip_reasoning(text)

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            }

        return LLMResponse(text=text, usage=usage, raw=response)

    def generate_structured(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        return self.generate(prompt, system, max_tokens, temperature)


def create_azure_client_from_config(llm_config) -> AzureClient:
    """Create an AzureClient from an LLMConfig dataclass."""
    return AzureClient(
        azure_endpoint=llm_config.base_url or "",
        api_key=llm_config.resolve_api_key(),
        model=llm_config.model,
        api_version=llm_config.azure_api_version,
    )
