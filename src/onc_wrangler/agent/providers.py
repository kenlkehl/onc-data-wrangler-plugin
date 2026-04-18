"""Provider-specific SDK adapters for multi-turn tool-use calls.

Each adapter converts between a provider-agnostic message format and the
provider's native SDK format.  The agnostic format uses plain dicts:

    {"role": "system",    "content": "..."}
    {"role": "user",      "content": "..."}
    {"role": "assistant", "content": "...", "tool_calls": [ToolCall, ...]}
    {"role": "tool",      "tool_call_id": "...", "name": "...", "content": "..."}

Each ``send_with_tools_*`` function takes the full agnostic message history
and returns ``(text, list[ToolCall])`` — the assistant's text output and
any tool calls it wants to make.
"""

import json
import logging
import uuid
from typing import Any

from .tools import ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema conversion helpers
# ---------------------------------------------------------------------------

def _tools_to_openai(tools: list[ToolDefinition]) -> list[dict]:
    """Convert to OpenAI Chat Completions tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _tools_to_anthropic(tools: list[ToolDefinition]) -> list[dict]:
    """Convert to Anthropic tool format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


def _tools_to_gemini(tools: list[ToolDefinition]):
    """Convert to Gemini function declaration format."""
    from google.genai.types import FunctionDeclaration, Tool
    declarations = []
    for t in tools:
        declarations.append(FunctionDeclaration(
            name=t.name,
            description=t.description,
            parameters=t.parameters,
        ))
    return [Tool(function_declarations=declarations)]


def _tools_to_azure_responses(tools: list[ToolDefinition]) -> list[dict]:
    """Convert to Azure Responses API tool format."""
    return [
        {
            "type": "function",
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in tools
    ]


# ---------------------------------------------------------------------------
# OpenAI / vLLM (Chat Completions API)
# ---------------------------------------------------------------------------

def _messages_to_openai(messages: list[dict]) -> list[dict]:
    """Convert agnostic messages to OpenAI Chat Completions format."""
    result = []
    for msg in messages:
        role = msg["role"]
        if role == "system":
            result.append({"role": "system", "content": msg["content"]})
        elif role == "user":
            result.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            m: dict[str, Any] = {"role": "assistant"}
            if msg.get("content"):
                m["content"] = msg["content"]
            if msg.get("tool_calls"):
                m["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg["tool_calls"]
                ]
            result.append(m)
        elif role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg["tool_call_id"],
                "content": msg["content"],
            })
    return result


def send_with_tools_openai(
    client,  # OpenAI client instance
    model: str,
    messages: list[dict],
    tools: list[ToolDefinition],
    max_tokens: int,
    temperature: float,
) -> tuple[str, list[ToolCall]]:
    """Send via OpenAI Chat Completions with tool support."""
    oai_messages = _messages_to_openai(messages)
    oai_tools = _tools_to_openai(tools)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": oai_messages,
        "tools": oai_tools,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    msg = choice.message

    text = msg.content or ""
    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {"_raw": tc.function.arguments}
            tool_calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=args,
            ))

    return text, tool_calls


# ---------------------------------------------------------------------------
# Anthropic (Messages API)
# ---------------------------------------------------------------------------

def _messages_to_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    """Convert agnostic messages to Anthropic format.

    Returns (system_prompt, messages_list).
    Anthropic requires alternating user/assistant messages. Tool results
    are sent as user messages with tool_result content blocks.
    """
    system = ""
    result = []

    for msg in messages:
        role = msg["role"]
        if role == "system":
            system = msg["content"]
        elif role == "user":
            result.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            content_blocks = []
            if msg.get("content"):
                content_blocks.append({"type": "text", "text": msg["content"]})
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
            result.append({"role": "assistant", "content": content_blocks})
        elif role == "tool":
            # Anthropic sends tool results as user messages with tool_result blocks.
            # Group consecutive tool results into a single user message.
            tool_result_block = {
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": msg["content"],
            }
            # If the last message in result is a user message with tool_result blocks,
            # append to it. Otherwise create a new user message.
            if (result and result[-1]["role"] == "user"
                    and isinstance(result[-1]["content"], list)
                    and result[-1]["content"]
                    and result[-1]["content"][0].get("type") == "tool_result"):
                result[-1]["content"].append(tool_result_block)
            else:
                result.append({"role": "user", "content": [tool_result_block]})

    return system, result


def send_with_tools_anthropic(
    client,  # Anthropic client instance
    model: str,
    messages: list[dict],
    tools: list[ToolDefinition],
    max_tokens: int,
    temperature: float,
) -> tuple[str, list[ToolCall]]:
    """Send via Anthropic Messages API with tool support."""
    system, anth_messages = _messages_to_anthropic(messages)
    anth_tools = _tools_to_anthropic(tools)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": anth_messages,
        "tools": anth_tools,
        "max_tokens": max_tokens,
    }
    if system:
        kwargs["system"] = system
    if temperature > 0:
        kwargs["temperature"] = temperature

    response = client.messages.create(**kwargs)

    text = ""
    tool_calls = []
    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(
                id=block.id,
                name=block.name,
                arguments=block.input if isinstance(block.input, dict) else {},
            ))

    return text, tool_calls


# ---------------------------------------------------------------------------
# Google Gemini (GenAI SDK)
# ---------------------------------------------------------------------------

def _messages_to_gemini(messages: list[dict]) -> tuple[str, list]:
    """Convert agnostic messages to Gemini contents format.

    Returns (system_instruction, contents_list).
    """
    from google.genai.types import Content, FunctionCall, FunctionResponse, Part

    system = ""
    contents = []

    for msg in messages:
        role = msg["role"]
        if role == "system":
            system = msg["content"]
        elif role == "user":
            contents.append(Content(
                role="user",
                parts=[Part(text=msg["content"])],
            ))
        elif role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append(Part(text=msg["content"]))
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    parts.append(Part(function_call=FunctionCall(
                        name=tc.name,
                        args=tc.arguments,
                    )))
            contents.append(Content(role="model", parts=parts))
        elif role == "tool":
            # Gemini expects function responses as user-role content
            fr = Part(function_response=FunctionResponse(
                name=msg["name"],
                response={"result": msg["content"]},
            ))
            # Group consecutive tool results into one Content block
            if (contents and contents[-1].role == "user"
                    and contents[-1].parts
                    and hasattr(contents[-1].parts[0], "function_response")
                    and contents[-1].parts[0].function_response is not None):
                contents[-1].parts.append(fr)
            else:
                contents.append(Content(role="user", parts=[fr]))

    return system, contents


def send_with_tools_gemini(
    client,  # google.genai.Client instance
    model: str,
    messages: list[dict],
    tools: list[ToolDefinition],
    max_tokens: int,
    temperature: float,
) -> tuple[str, list[ToolCall]]:
    """Send via Gemini GenAI SDK with function calling."""
    from google.genai.types import GenerateContentConfig

    system, contents = _messages_to_gemini(messages)
    gemini_tools = _tools_to_gemini(tools)

    config_kwargs: dict[str, Any] = {
        "max_output_tokens": max_tokens,
        "temperature": temperature,
        "tools": gemini_tools,
    }
    if system:
        config_kwargs["system_instruction"] = system

    config = GenerateContentConfig(**config_kwargs)

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    text = ""
    tool_calls = []

    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.text:
                text += part.text
            if part.function_call:
                fc = part.function_call
                tool_calls.append(ToolCall(
                    id=f"call_{uuid.uuid4().hex[:12]}",
                    name=fc.name,
                    arguments=dict(fc.args) if fc.args else {},
                ))

    return text, tool_calls


# ---------------------------------------------------------------------------
# Azure OpenAI (Responses API)
# ---------------------------------------------------------------------------

def _messages_to_azure_responses(messages: list[dict]) -> tuple[str, list[dict]]:
    """Convert agnostic messages to Azure Responses API input format.

    Returns (instructions, input_items).
    """
    instructions = ""
    items = []

    for msg in messages:
        role = msg["role"]
        if role == "system":
            instructions = msg["content"]
        elif role == "user":
            items.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            if msg.get("content"):
                items.append({
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": msg["content"]}],
                })
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    items.append({
                        "type": "function_call",
                        "id": tc.id,
                        "call_id": tc.id,
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    })
        elif role == "tool":
            items.append({
                "type": "function_call_output",
                "call_id": msg["tool_call_id"],
                "output": msg["content"],
            })

    return instructions, items


def send_with_tools_azure(
    client,  # OpenAI client instance (used for Azure)
    model: str,
    messages: list[dict],
    tools: list[ToolDefinition],
    max_tokens: int,
    temperature: float,
) -> tuple[str, list[ToolCall]]:
    """Send via Azure Responses API with tool support."""
    instructions, input_items = _messages_to_azure_responses(messages)
    azure_tools = _tools_to_azure_responses(tools)

    kwargs: dict[str, Any] = {
        "model": model,
        "input": input_items,
        "tools": azure_tools,
        "max_output_tokens": max_tokens,
        "temperature": temperature,
    }
    if instructions:
        kwargs["instructions"] = instructions

    response = client.responses.create(**kwargs)

    text = ""
    tool_calls = []

    for item in response.output:
        item_type = getattr(item, "type", None)
        if item_type == "message":
            for content_block in getattr(item, "content", []):
                if getattr(content_block, "type", None) == "output_text":
                    text += content_block.text
        elif item_type == "function_call":
            call_id = getattr(item, "call_id", None) or getattr(item, "id", f"call_{uuid.uuid4().hex[:12]}")
            try:
                args = json.loads(item.arguments) if isinstance(item.arguments, str) else item.arguments
            except (json.JSONDecodeError, TypeError):
                args = {"_raw": item.arguments}
            tool_calls.append(ToolCall(
                id=call_id,
                name=item.name,
                arguments=args,
            ))

    return text, tool_calls


# ---------------------------------------------------------------------------
# Provider detection and dispatch
# ---------------------------------------------------------------------------

def detect_provider(llm_client) -> str:
    """Detect the provider from an LLMClient instance.

    Returns one of: "openai", "anthropic", "gemini", "azure".
    """
    from onc_wrangler.llm.vllm_client import VLLMClient
    from onc_wrangler.llm.claude_client import ClaudeClient
    from onc_wrangler.llm.azure_client import AzureClient
    from onc_wrangler.llm.gemini_client import GeminiClient

    if isinstance(llm_client, VLLMClient):
        return "openai"
    if isinstance(llm_client, ClaudeClient):
        return "anthropic"
    if isinstance(llm_client, GeminiClient):
        return "gemini"
    if isinstance(llm_client, AzureClient):
        return "azure"
    raise ValueError(f"Unknown LLM client type: {type(llm_client).__name__}")


def send_with_tools(
    llm_client,
    messages: list[dict],
    tools: list[ToolDefinition],
    max_tokens: int,
    temperature: float,
) -> tuple[str, list[ToolCall]]:
    """Dispatch to the correct provider adapter.

    Args:
        llm_client: An LLMClient instance (VLLMClient, ClaudeClient, etc.).
        messages: Provider-agnostic message history.
        tools: Tool definitions.
        max_tokens: Max output tokens.
        temperature: Sampling temperature.

    Returns:
        (text, tool_calls) tuple.
    """
    provider = detect_provider(llm_client)
    sdk_client = llm_client.client  # the raw SDK client
    model = llm_client.model

    if provider == "openai":
        return send_with_tools_openai(sdk_client, model, messages, tools, max_tokens, temperature)
    elif provider == "anthropic":
        return send_with_tools_anthropic(sdk_client, model, messages, tools, max_tokens, temperature)
    elif provider == "gemini":
        return send_with_tools_gemini(sdk_client, model, messages, tools, max_tokens, temperature)
    elif provider == "azure":
        return send_with_tools_azure(sdk_client, model, messages, tools, max_tokens, temperature)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
