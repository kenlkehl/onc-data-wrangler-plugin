"""Agentic LLM loop with multi-turn tool use."""

import hashlib
import json
import logging
from typing import Optional

from .providers import send_with_tools
from .tools import DEFAULT_TOOLS, ToolCall, ToolDefinition, ToolResult, execute_tool

logger = logging.getLogger(__name__)


class AgentLoop:
    """Multi-turn agent loop that uses LLM tool-use to iteratively solve tasks.

    The loop sends messages to the LLM, parses tool calls, executes tools
    locally, feeds results back, and repeats until the LLM produces a
    text-only response (no tool calls) or max_turns is reached.
    """

    def __init__(
        self,
        llm_client,
        system_prompt: str,
        tools: Optional[list[ToolDefinition]] = None,
        max_turns: int = 30,
        max_context_chars: int = 200_000,
        allowed_dirs: Optional[list[str]] = None,
        work_dir: str = "/tmp",
        max_tokens: int = 16384,
        temperature: float = 0.0,
        timeout: int = 120,
    ):
        """
        Args:
            llm_client: An LLMClient instance (VLLMClient, ClaudeClient, etc.).
            system_prompt: System prompt for the agent.
            tools: Tool definitions. Defaults to execute_python + read_file + list_files.
            max_turns: Maximum LLM call iterations.
            max_context_chars: Estimated char limit for context truncation.
            allowed_dirs: Directories that read_file and list_files can access.
            work_dir: Working directory for execute_python scripts.
            max_tokens: Max output tokens per LLM call.
            temperature: Sampling temperature.
            timeout: Timeout in seconds for execute_python.
        """
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.tools = tools or DEFAULT_TOOLS
        self.max_turns = max_turns
        self.max_context_chars = max_context_chars
        self.allowed_dirs = allowed_dirs or []
        self.work_dir = work_dir
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    def run(self, user_message: str) -> str:
        """Run the agent loop to completion.

        Args:
            user_message: The initial user message (task description).

        Returns:
            The final text response from the LLM.
        """
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        stall_count = 0
        last_call_hash = ""
        final_text = ""

        for turn in range(self.max_turns):
            # Truncate history if it's getting too long
            self._truncate_history(messages)

            logger.info("Agent turn %d/%d", turn + 1, self.max_turns)

            try:
                text, tool_calls = send_with_tools(
                    self.llm_client,
                    messages,
                    self.tools,
                    self.max_tokens,
                    self.temperature,
                )
            except Exception as e:
                logger.error("LLM call failed on turn %d: %s", turn + 1, e)
                if final_text:
                    return final_text
                raise

            # Track the latest text
            if text:
                final_text = text

            if not tool_calls:
                # LLM returned text only — done
                logger.info("Agent completed after %d turns", turn + 1)
                return text

            # Stall detection: check if the same tool calls are repeated
            call_hash = self._hash_tool_calls(tool_calls)
            if call_hash == last_call_hash:
                stall_count += 1
                logger.warning("Stall detected (%d consecutive)", stall_count)
                if stall_count >= 3:
                    logger.warning("Forcing completion after %d stalls", stall_count)
                    messages.append({
                        "role": "assistant",
                        "content": text,
                        "tool_calls": tool_calls,
                    })
                    # Execute the tool calls one more time
                    for tc in tool_calls:
                        result = execute_tool(tc, self.work_dir, self.allowed_dirs, self.timeout)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": result.tool_call_id,
                            "name": result.name,
                            "content": result.content,
                        })
                    # Ask for final output
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have been repeating the same tool calls. Please stop and "
                            "produce your final JSON output now based on the results you have so far."
                        ),
                    })
                    try:
                        text, _ = send_with_tools(
                            self.llm_client, messages, self.tools,
                            self.max_tokens, self.temperature,
                        )
                    except Exception:
                        pass
                    return text or final_text
            else:
                stall_count = 0
            last_call_hash = call_hash

            # Add assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": text,
                "tool_calls": tool_calls,
            })

            # Execute tool calls and add results
            for tc in tool_calls:
                logger.info("  Executing tool: %s", tc.name)
                result = execute_tool(tc, self.work_dir, self.allowed_dirs, self.timeout)
                messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "name": result.name,
                    "content": result.content,
                })

            if stall_count == 1:
                # Inject a gentle nudge after first stall
                messages.append({
                    "role": "user",
                    "content": (
                        "Note: You seem to be repeating a previous tool call. "
                        "If you have the information you need, proceed to produce "
                        "your final output."
                    ),
                })

        # Exhausted max_turns — ask for final output
        logger.warning("Agent exhausted %d turns, forcing completion", self.max_turns)
        messages.append({
            "role": "user",
            "content": (
                "You have reached the maximum number of iterations. Please produce "
                "your final JSON output now based on all the analysis you have done so far."
            ),
        })
        try:
            text, _ = send_with_tools(
                self.llm_client, messages, self.tools,
                self.max_tokens, self.temperature,
            )
            if text:
                return text
        except Exception:
            pass
        return final_text

    def _truncate_history(self, messages: list[dict]):
        """Truncate old tool results when context is getting too large.

        Keeps the system message, first user message, and the last few
        exchanges intact. Middle tool results are replaced with summaries.
        """
        total_chars = sum(self._msg_chars(m) for m in messages)
        if total_chars <= int(self.max_context_chars * 0.8):
            return

        # Keep: system (index 0), first user (index 1), and last 6 messages
        keep_start = 2
        keep_end = max(keep_start, len(messages) - 6)

        truncated = 0
        for i in range(keep_start, keep_end):
            msg = messages[i]
            if msg["role"] == "tool" and len(msg["content"]) > 500:
                original_len = len(msg["content"])
                msg["content"] = (
                    msg["content"][:200]
                    + f"\n\n[... {original_len - 400} chars truncated for context management ...]\n\n"
                    + msg["content"][-200:]
                )
                truncated += 1

        if truncated:
            logger.info("Truncated %d old tool results to manage context size", truncated)

    @staticmethod
    def _msg_chars(msg: dict) -> int:
        """Estimate the character count of a message."""
        chars = len(msg.get("content", "") or "")
        for tc in msg.get("tool_calls", []):
            chars += len(json.dumps(tc.arguments)) if isinstance(tc, ToolCall) else 0
        return chars

    @staticmethod
    def _hash_tool_calls(tool_calls: list[ToolCall]) -> str:
        """Hash tool calls for stall detection."""
        data = json.dumps(
            [(tc.name, tc.arguments) for tc in tool_calls],
            sort_keys=True,
        )
        return hashlib.md5(data.encode()).hexdigest()
