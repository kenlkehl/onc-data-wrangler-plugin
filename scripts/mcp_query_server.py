#!/usr/bin/env python3
"""Stdio MCP server entry point for the onc-data-wrangler plugin.

Loads the project config and starts the FastMCP query server on stdio transport.
"""

import os
import sys
from pathlib import Path

# Add the plugin's src directory to the Python path
plugin_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(plugin_root / "src"))

from onc_wrangler.config import load_config
from onc_wrangler.query.mcp_server import create_server_from_config


def main():
    config_path = os.environ.get("ONC_CONFIG_PATH", "")

    if not config_path or not Path(config_path).exists():
        # Return a minimal server that reports the error
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP(
            name="onc-data-wrangler (not configured)",
            instructions="No project configuration found. Run /onc-data-wrangler:setup-project first.",
        )

        @mcp.tool()
        def get_status() -> dict:
            """Check server status."""
            return {
                "status": "not_configured",
                "message": "No project config found. Run /onc-data-wrangler:setup-project to create one.",
                "config_path_checked": config_path,
            }

        mcp.run(transport="stdio")
        return

    config = load_config(config_path)
    server = create_server_from_config(config)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
