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

from mcp.server.fastmcp import FastMCP

from .client import BlenderClient
from .tools import code as code_tools
from .tools import objects as object_tools
from .tools import render as render_tools
from .tools import scene as scene_tools

logging.basicConfig(
    level=os.getenv("BLENDER_BRIDGE_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("blender_bridge")

mcp = FastMCP("blender_mcp")

_client = BlenderClient(
    host=os.getenv("BLENDER_BRIDGE_HOST", "127.0.0.1"),
    port=int(os.getenv("BLENDER_BRIDGE_PORT", "9876")),
)

# Register tool groups — each module registers its own tools with mcp
scene_tools.register(mcp, _client)
object_tools.register(mcp, _client)
render_tools.register(mcp, _client)
code_tools.register(mcp, _client)


def main() -> None:
    """Run the MCP server using stdio transport (default for local Claude clients)."""
    logger.info("Starting MCP-Blender-Bridge v0.2.0 (stdio transport)...")
    mcp.run()


if __name__ == "__main__":
    main()
