"""Shared utilities for response formatting and error handling."""

from __future__ import annotations

import json
from typing import Any

from .client import BlenderConnectionError


def format_error(message: str) -> str:
    """Format an error message as a JSON string for tool returns."""
    return json.dumps({"status": "error", "message": message}, indent=2)


def format_success(result: Any, *, message: str | None = None) -> str:
    """Format a success response as a JSON string."""
    payload: dict[str, Any] = {"status": "success", "result": result}
    if message:
        payload["message"] = message
    return json.dumps(payload, indent=2, default=str)


def handle_blender_error(exc: Exception) -> str:
    """Translate exceptions into actionable error messages for the agent."""
    if isinstance(exc, BlenderConnectionError):
        return format_error(
            f"Cannot reach Blender. {exc} "
            "Next steps: (1) Open Blender, (2) install and enable the "
            "'mcp_blender_bridge' addon from the blender_addon/ folder, "
            "(3) start the bridge server from the addon's 3D View N-panel."
        )
    return format_error(f"Unexpected error ({type(exc).__name__}): {exc}")


READ_ONLY_ERROR: str = format_error(
    "Server is in read-only mode (BLENDER_BRIDGE_READ_ONLY=true). "
    "This operation is disabled. Set BLENDER_BRIDGE_READ_ONLY=false to enable writes."
)


def check_read_only(read_only: bool) -> str | None:
    """Return READ_ONLY_ERROR if read_only is True, else None."""
    return READ_ONLY_ERROR if read_only else None


def parse_blender_response(response: dict[str, Any]) -> Any:
    """Validate Blender's response envelope and return the inner result.

    Raises BlenderConnectionError if the response indicates failure.
    """
    if response.get("status") != "success":
        raise BlenderConnectionError(
            response.get("message", "Blender returned an unknown error.")
        )
    return response.get("result")
