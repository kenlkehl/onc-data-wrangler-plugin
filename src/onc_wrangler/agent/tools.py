"""Tool definitions and execution for the agentic LLM loop."""

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ToolDefinition:
    """Provider-agnostic tool definition."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Result of executing a tool call."""
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# Tool schemas (provider-agnostic JSON Schema)
# ---------------------------------------------------------------------------

EXECUTE_PYTHON_SCHEMA = ToolDefinition(
    name="execute_python",
    description=(
        "Write and execute a Python script. The script has access to pandas, "
        "numpy, scipy, lifelines, matplotlib, and the standard library. "
        "Returns stdout and stderr (truncated to ~8000 chars). "
        "Use print() to output results. Use json.dump() to write structured output files."
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute.",
            },
        },
        "required": ["code"],
    },
)

READ_FILE_SCHEMA = ToolDefinition(
    name="read_file",
    description=(
        "Read the contents of a file. Returns the file text (truncated to ~50000 chars). "
        "Use this to inspect data dictionaries, small data files, or previously written output files."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to read.",
            },
        },
        "required": ["path"],
    },
)

LIST_FILES_SCHEMA = ToolDefinition(
    name="list_files",
    description=(
        "List files and directories in a directory. Returns names with sizes and types."
    ),
    parameters={
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Absolute path to the directory to list.",
            },
        },
        "required": ["directory"],
    },
)

DEFAULT_TOOLS = [EXECUTE_PYTHON_SCHEMA, READ_FILE_SCHEMA, LIST_FILES_SCHEMA]

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

_MAX_OUTPUT_CHARS = 8000
_MAX_READ_CHARS = 50000


def _is_within_allowed(path: str, allowed_dirs: list[str]) -> bool:
    """Check if a path is within one of the allowed directories."""
    resolved = os.path.realpath(path)
    for d in allowed_dirs:
        d_resolved = os.path.realpath(d)
        if resolved == d_resolved or resolved.startswith(d_resolved + os.sep):
            return True
    return False


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return (
        text[:half]
        + f"\n\n... [{len(text) - limit} chars truncated] ...\n\n"
        + text[-half:]
    )


def execute_python(code: str, work_dir: str, timeout: int = 120) -> str:
    """Write code to a temp file, execute it, return stdout+stderr."""
    os.makedirs(work_dir, exist_ok=True)
    fd, script_path = tempfile.mkstemp(suffix=".py", dir=work_dir)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(code)
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            if output:
                output += "\n--- STDERR ---\n"
            output += result.stderr
        if result.returncode != 0:
            output = f"[Exit code {result.returncode}]\n{output}"
        return _truncate(output, _MAX_OUTPUT_CHARS) if output else "(no output)"
    except subprocess.TimeoutExpired:
        return f"[ERROR] Script timed out after {timeout} seconds."
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def read_file(path: str, allowed_dirs: list[str], max_chars: int = _MAX_READ_CHARS) -> str:
    """Read a file, restricted to allowed directories."""
    if not _is_within_allowed(path, allowed_dirs):
        return f"[ERROR] Access denied: {path} is not within allowed directories."
    try:
        text = Path(path).read_text(errors="replace")
        return _truncate(text, max_chars)
    except FileNotFoundError:
        return f"[ERROR] File not found: {path}"
    except Exception as e:
        return f"[ERROR] Cannot read {path}: {e}"


def list_files(directory: str, allowed_dirs: list[str]) -> str:
    """List files in a directory, restricted to allowed directories."""
    if not _is_within_allowed(directory, allowed_dirs):
        return f"[ERROR] Access denied: {directory} is not within allowed directories."
    try:
        entries = []
        for entry in sorted(Path(directory).iterdir()):
            if entry.is_dir():
                entries.append(f"  [DIR]  {entry.name}/")
            else:
                size = entry.stat().st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                entries.append(f"  {size_str:>10}  {entry.name}")
        return "\n".join(entries) if entries else "(empty directory)"
    except FileNotFoundError:
        return f"[ERROR] Directory not found: {directory}"
    except Exception as e:
        return f"[ERROR] Cannot list {directory}: {e}"


def execute_tool(tool_call: ToolCall, work_dir: str, allowed_dirs: list[str],
                 timeout: int = 120) -> ToolResult:
    """Execute a tool call and return the result."""
    try:
        if tool_call.name == "execute_python":
            content = execute_python(
                code=tool_call.arguments.get("code", ""),
                work_dir=work_dir,
                timeout=timeout,
            )
        elif tool_call.name == "read_file":
            content = read_file(
                path=tool_call.arguments.get("path", ""),
                allowed_dirs=allowed_dirs,
            )
        elif tool_call.name == "list_files":
            content = list_files(
                directory=tool_call.arguments.get("directory", ""),
                allowed_dirs=allowed_dirs,
            )
        else:
            content = f"[ERROR] Unknown tool: {tool_call.name}"
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=content,
                is_error=True,
            )
        is_error = content.startswith("[ERROR]") or content.startswith("[Exit code")
        return ToolResult(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            content=content,
            is_error=is_error,
        )
    except Exception as e:
        return ToolResult(
            tool_call_id=tool_call.id,
            name=tool_call.name,
            content=f"[ERROR] Tool execution failed: {e}",
            is_error=True,
        )
