"""MCP-Blender-Bridge server entry point.

Exposes Blender 3D operations to MCP-compatible clients (Claude Desktop,
Claude Code, etc.) via the standard Model Context Protocol.

Run locally with stdio transport (default):

    uv run mcp-blender-bridge

Or via HTTP (remote/render-farm) transport:

    BLENDER_BRIDGE_AUTH_TOKEN=secret uv run mcp-blender-bridge --transport http

Or via the MCP Inspector for testing:

    npx @modelcontextprotocol/inspector uv run mcp-blender-bridge
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import sys
from importlib.metadata import version as _pkg_version
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp

from ._log_formatter import JsonFormatter
from .asset_cache import prune_sha256_cache
from .client import BlenderClient
from .headless_blender import launch_blender
from .plugins import list_plugins_text, load_plugins
from .tools import code as code_tools
from .tools import objects as object_tools
from .tools import render as render_tools
from .tools import scene as scene_tools

# ---------------------------------------------------------------------------
# Logging bootstrap (happens before anything else)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Core server + client
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Auth middleware for HTTP transport
# ---------------------------------------------------------------------------


class AuthMiddleware(BaseHTTPMiddleware):
    """Bearer-token authentication middleware for the HTTP transport.

    Rejects any request whose ``Authorization`` header is missing or does not
    match the server-configured token with a ``401 Unauthorized`` response.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        super().__init__(app)
        # Encode once so compare_digest sees fixed-length bytes regardless of input.
        self._token_bytes = token.encode("utf-8")

    async def dispatch(
        self,
        request: Any,
        call_next: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Unauthorized: Missing or invalid Authorization header"},
                status_code=401,
            )

        presented = auth_header.split(" ", 1)[1].encode("utf-8")
        if not secrets.compare_digest(presented, self._token_bytes):
            return JSONResponse(
                {"error": "Unauthorized: Invalid token"},
                status_code=401,
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server.

    Recognised CLI flags:

    * ``--transport`` — Transport protocol: ``stdio`` (default), ``http``, or ``sse``.
    * ``--host`` — Bind host for HTTP/SSE transport (default: ``0.0.0.0`` for http, ``127.0.0.1`` otherwise).
    * ``--port`` — Bind port for HTTP/SSE transport (default: ``8765`` for http, ``8000`` otherwise).
    * ``--list-plugins`` — Print installed plugins and exit (does not start the server).
    """
    parser = argparse.ArgumentParser(
        prog="mcp-blender-bridge",
        description="Production-grade Blender MCP server",
    )
    parser.add_argument(
        "--list-plugins",
        action="store_true",
        help="Print installed plugins and exit",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport protocol to use (default: stdio)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind to for HTTP/SSE transport",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to for HTTP/SSE transport",
    )
    parser.add_argument(
        "--launch-blender",
        action="store_true",
        help=(
            "Launch Blender in --background mode with the MCP addon auto-loaded. "
            "The server waits for Blender to be ready before accepting MCP connections."
        ),
    )
    parser.add_argument(
        "--blender-path",
        type=str,
        default=None,
        metavar="PATH",
        help="Explicit path to the Blender executable (overrides BLENDER_PATH env var).",
    )

    args = parser.parse_args()

    if args.list_plugins:
        sys.stdout.write(list_plugins_text())
        return

    # ── Optional: launch Blender headless ─────────────────────────────────────
    _blender_proc = None
    if args.launch_blender:
        import asyncio as _asyncio

        bridge_host = os.getenv("BLENDER_BRIDGE_HOST", "127.0.0.1")
        bridge_port = int(os.getenv("BLENDER_BRIDGE_PORT", "9876"))
        try:
            _blender_proc = _asyncio.run(
                launch_blender(
                    blender_path=args.blender_path,
                    bridge_host=bridge_host,
                    bridge_port=bridge_port,
                )
            )
        except (FileNotFoundError, RuntimeError) as exc:
            sys.stderr.write(f"Error: {exc}\n")
            sys.exit(1)

    # Determine defaults based on transport. HTTP defaults to loopback; explicit
    # --host 0.0.0.0 is required to expose the server to other machines.
    host = args.host if args.host is not None else "127.0.0.1"
    port = args.port if args.port is not None else (8765 if args.transport == "http" else 8000)

    if args.transport == "http" and host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "HTTP transport bound to non-loopback host %r — ensure BLENDER_BRIDGE_AUTH_TOKEN "
            "is rotated and the network path is trusted.",
            host,
        )

    logger.info(
        "Starting MCP-Blender-Bridge v%s "
        "(transport=%s, read_only=%s, persistent=%s, log_format=%s, plugins=%d)",
        _pkg_version("mcp-blender-bridge"),
        args.transport,
        _read_only,
        _persistent,
        _log_format,
        len(_loaded_plugins),
    )

    # Prune stale asset cache entries before serving any tool calls
    import asyncio as _asyncio_prune

    try:
        removed = _asyncio_prune.run(prune_sha256_cache())
        if removed:
            logger.info("SHA256 cache pruned %d stale entries.", removed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SHA256 cache prune failed (non-fatal): %s", exc)

    if args.transport == "http":
        auth_token = os.getenv("BLENDER_BRIDGE_AUTH_TOKEN")
        if not auth_token:
            sys.stderr.write(
                "Error: BLENDER_BRIDGE_AUTH_TOKEN environment variable is required "
                "when using HTTP transport.\n"
            )
            sys.exit(1)

        app = mcp.streamable_http_app()
        app.add_middleware(AuthMiddleware, token=auth_token)

        # Persist the resolved host/port on settings so plugins can inspect them.
        mcp.settings.host = host
        mcp.settings.port = port

        uvicorn.run(app, host=host, port=port, log_level=_log_level.lower())

    elif args.transport == "sse":
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="sse")

    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
