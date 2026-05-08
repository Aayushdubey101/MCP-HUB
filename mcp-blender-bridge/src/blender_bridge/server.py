"""MCP-Blender-Bridge server entry point.

Exposes Blender 3D operations to MCP-compatible clients (Claude Desktop,
Claude Code, etc.) via the standard Model Context Protocol.

Run locally with stdio transport (default):

    uv run mcp-blender-bridge

Or via the MCP Inspector for testing:

    npx @modelcontextprotocol/inspector uv run mcp-blender-bridge
"""

from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from ._log_formatter import JsonFormatter
from .client import BlenderClient
from .plugins import list_plugins_text, load_plugins
from .tools import code as code_tools
from .tools import objects as object_tools
from .tools import render as render_tools
from .tools import scene as scene_tools


_log_level = os.getenv("BLENDER_BRIDGE_LOG_LEVEL", "INFO")
_log_format = os.getenv("BLENDER_BRIDGE_LOG_FORMAT", "text").lower()
_read_only = os.getenv("BLENDER_BRIDGE_READ_ONLY", "false").lower() in ("1", "true", "yes")
_persistent = os.getenv("BLENDER_BRIDGE_PERSISTENT", "false").lower() in ("1", "true", "yes")

if _log_format == "json":
    _handler = logging.StreamHandler()
    _handler.setFormatter(JsonFormatter())
    logging.root.handlers = []
    logging.root.addHandler(_handler)
    logging.root.setLevel(_log_level)
else:
    logging.basicConfig(
        level=_log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

logger = logging.getLogger("blender_bridge")

mcp = FastMCP("blender_mcp")

_client = BlenderClient(
    host=os.getenv("BLENDER_BRIDGE_HOST", "127.0.0.1"),
    port=int(os.getenv("BLENDER_BRIDGE_PORT", "9876")),
    persistent=_persistent,
)

# Register built-in tool groups — each module registers its own tools with mcp
scene_tools.register(mcp, _client)
object_tools.register(mcp, _client, read_only=_read_only)
render_tools.register(mcp, _client, read_only=_read_only)
code_tools.register(mcp, _client, read_only=_read_only)

# Discover and register installed plugins (asset libraries, AI generators, etc.).
# Zero plugins ship with the core package — this is opt-in by `pip install`.
_loaded_plugins = load_plugins(mcp, _client, read_only=_read_only)


def main() -> None:
    """Run the MCP server using stdio transport (default for local Claude clients).

    Recognised CLI flags:

    * ``--list-plugins`` — print installed plugins and exit (does not start the server).
    """
    if "--list-plugins" in sys.argv[1:]:
        sys.stdout.write(list_plugins_text())
        return

    logger.info(
        "Starting MCP-Blender-Bridge v0.3.0 "
        "(stdio transport, read_only=%s, persistent=%s, log_format=%s, plugins=%d)",
        _read_only,
        _persistent,
        _log_format,
        len(_loaded_plugins),
    )
    mcp.run()


if __name__ == "__main__":
    main()
