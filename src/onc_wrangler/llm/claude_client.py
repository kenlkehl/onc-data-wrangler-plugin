"""Anthropic Claude client supporting direct API and Vertex AI."""

import logging
import os
from typing import Optional

from .base import LLMClient, LLMResponse

logger = logging.getLogger(__name__)


class ClaudeClient(LLMClient):
    """Client for Anthropic Claude (direct API or Vertex AI).

    Used for de-identified chatbot interactions and field discovery.

    Args:
        provider: "anthropic" for direct API, "vertex" for Vertex AI.
        model: Model identifier (e.g., "claude-sonnet-4-20250514").
        api_key: Anthropic API key (for direct API).
        vertex_project: GCP project ID (for Vertex AI).
        vertex_region: GCP region (for Vertex AI).
    """

    def __init__(self, provider: str = "anthropic", model: str = "claude-opus-4-6", api_key: Optional[str] = None, vertex_project: Optional[str] = None, vertex_region: str = "global"):
        self.provider = provider
        self.model = model

        if provider == "vertex":
            from anthropic import AnthropicVertex
            vertex_project = vertex_project or os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "")
            self.client = AnthropicVertex(project_id=vertex_project, region=vertex_region)
        else:
            import anthropic
            api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            self.client = anthropic.Anthropic(api_key=api_key)

    def generate(self, prompt: str, system: str = "", max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if temperature > 0:
            kwargs["temperature"] = temperature

        if self.provider == "vertex":
            with self.client.messages.stream(**kwargs) as stream:
                response = stream.get_final_message()
        else:
            response = self.client.messages.create(**kwargs)

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        return LLMResponse(text=text, usage=usage, raw=response)

    def generate_structured(self, prompt: str, system: str = "", max_tokens: int = 60000, temperature: float = 0.0) -> LLMResponse:
        if system:
            json_system = system + "\n\nYou must respond with valid JSON only. No commentary."
        else:
            json_system = "You must respond with valid JSON only. No commentary."
        return self.generate(prompt, json_system, max_tokens, temperature)


def create_claude_client_from_config(llm_config) -> ClaudeClient:
    """Create a ClaudeClient from an LLMConfig dataclass."""
    return ClaudeClient(
        provider=llm_config.provider,
        model=llm_config.model,
        api_key=llm_config.resolve_api_key(),
        vertex_project=llm_config.resolve_vertex_project(),
        vertex_region=llm_config.vertex_region,
    )
