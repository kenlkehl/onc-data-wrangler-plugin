"""LLM client abstractions."""

from onc_wrangler.config import LLMConfig

from .base import LLMClient, LLMResponse
from .vllm_client import VLLMClient
from .claude_client import ClaudeClient
from .azure_client import AzureClient

__all__ = ["LLMClient", "LLMResponse", "LLMConfig", "VLLMClient", "ClaudeClient", "AzureClient", "create_llm_client"]


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Factory: build the right LLMClient subclass from an LLMConfig."""
    if config.provider in ("openai", "vllm"):
        from .vllm_client import VLLMClient
        return VLLMClient(
            base_url=config.base_url or "http://localhost:8000/v1",
            api_key=config.resolve_api_key(),
            model=config.model,
        )
    elif config.provider == "azure":
        from .azure_client import AzureClient
        return AzureClient(
            azure_endpoint=config.base_url or "",
            api_key=config.resolve_api_key(),
            model=config.model,
            api_version=config.azure_api_version,
        )
    elif config.provider in ("anthropic", "vertex"):
        from .claude_client import ClaudeClient
        return ClaudeClient(
            provider=config.provider,
            model=config.model,
            api_key=config.resolve_api_key(),
            vertex_project=config.resolve_vertex_project(),
            vertex_region=config.vertex_region,
        )
    elif config.provider == "claude-code":
        raise ValueError(
            "provider 'claude-code' means Claude Code itself is the extractor. "
            "Use extraction-worker agents, not the Python LLM client."
        )
    else:
        raise ValueError(f"Unknown LLM provider: {config.provider}")
