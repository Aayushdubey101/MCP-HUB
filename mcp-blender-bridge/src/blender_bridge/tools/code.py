"""Python escape-hatch tool — execute arbitrary code inside Blender."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from ..client import BlenderClient
from ..schemas import ExecutePythonInput
from ..utils import check_read_only, format_success, handle_blender_error, parse_blender_response

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, client: BlenderClient, *, read_only: bool = False) -> None:
    """Register the Python execution escape-hatch tool."""

    @mcp.tool(
        name="blender_execute_python",
        annotations={
            "title": "Execute Python in Blender",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def blender_execute_python(params: ExecutePythonInput) -> str:
        """Execute arbitrary Python code inside Blender (escape hatch for advanced ops).

        The code runs with `bpy` already imported. To return data, assign it to
        a variable named `result`. Use this only when no dedicated tool fits.

        DESTRUCTIVE: arbitrary code can modify or delete anything in the scene.

        Args:
            params: ExecutePythonInput with the `code` string to execute (max 20,000 chars).

        Returns:
            JSON with the value of `result` (if set) or a success confirmation.

        Example:
            code = "result = [obj.name for obj in bpy.data.objects if obj.type == 'MESH']"
        """
        if err := check_read_only(read_only):
            return err
        try:
            response = await client.send_command(
                "execute_python",
                {"code": params.code},
            )
            result = parse_blender_response(response)
            return format_success(result)
        except Exception as exc:  # noqa: BLE001
            return handle_blender_error(exc)
