"""Render submission tool — synchronous render with inline image preview."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from ..client import BlenderClient
from ..schemas import RenderImageInput
from ..utils import check_read_only, handle_blender_error, parse_blender_response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure implementation — callable without going through MCP/TCP registration
# ---------------------------------------------------------------------------


async def _render_image_impl(
    params: RenderImageInput, client: BlenderClient, read_only: bool = False
) -> list[Any]:
    if err := check_read_only(read_only):
        return [err]
    try:
        response = await client.send_command(
            "render_image",
            {
                "frame": params.frame,
                "output_path": params.output_path,
                "engine": params.engine.value if params.engine else None,
                "samples": params.samples,
                "max_preview_size": params.max_preview_size,
            },
            timeout=params.timeout_seconds,
        )
        result = parse_blender_response(response)

        metadata = {
            "status": "complete",
            "frame": result.get("frame"),
            "engine": result.get("engine"),
            "render_time_seconds": result.get("render_time_seconds"),
            "resolution": result.get("resolution"),
            "output_path": result.get("output_path"),
        }
        meta_str = json.dumps({"status": "success", "result": metadata}, indent=2)
        image_bytes = base64.b64decode(result["image_data"])
        return [meta_str, Image(data=image_bytes, format="png")]
    except Exception as exc:  # noqa: BLE001
        return [handle_blender_error(exc)]


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, client: BlenderClient, *, read_only: bool = False) -> None:
    """Register the render submission tool."""

    @mcp.tool(
        name="blender_render_image",
        annotations={
            "title": "Render Image",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def blender_render_image(params: RenderImageInput):  # noqa: ANN201  # list[str | Image]
        """Render a frame using Blender's render engine and return the result inline.

        Blocks until the render is complete. For fast previews use EEVEE; for
        photorealistic output use CYCLES (much slower — increase timeout_seconds).

        Returns both a JSON metadata block and an inline image preview. If
        output_path is given the full-resolution render is also saved to disk.

        Args:
            params: RenderImageInput with optional frame, output_path, engine override,
                Cycles sample override, preview size, and timeout.

        Returns:
            List of [metadata JSON string, inline PNG preview Image].

        Example:
            blender_render_image(engine="BLENDER_EEVEE", frame=1, max_preview_size=512)
            blender_render_image(engine="CYCLES", samples=64, timeout_seconds=600)
        """
        return await _render_image_impl(params, client, read_only)
