#!/usr/bin/env python3
"""Stdio MCP server entry point for the onc-data-wrangler plugin.

Starts a FastMCP query server that dynamically loads the project config
on each tool call, so it automatically picks up new databases created by
make-database without requiring a restart.

Config discovery order:
  1. ONC_CONFIG_PATH env var (explicit override)
  2. active_config.yaml in the current working directory (project folder)
"""

import os
import sys
from pathlib import Path

# Add the plugin's src directory to the Python path
plugin_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(plugin_root / "src"))

from onc_wrangler.query.mcp_server import create_server


def _resolve_config_path() -> str:
    """Find the config path, preferring explicit env var, then CWD."""
    # Explicit override via env var
    explicit = os.environ.get("ONC_CONFIG_PATH", "").strip()
    if explicit:
        return explicit

    # Default: active_config.yaml in the working directory
    return str(Path.cwd() / "active_config.yaml")


def main():
    config_path = _resolve_config_path()
    server = create_server(config_path)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
