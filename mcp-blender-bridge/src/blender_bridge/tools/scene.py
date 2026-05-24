"""Scene inspection and read-only tools."""

from __future__ import annotations

import base64
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from ..client import BRIDGE_PROTOCOL_VERSION, BlenderClient
from ..schemas import (
    GetObjectInfoInput,
    GetSceneInfoInput,
    ListObjectsInput,
    OpenFileInput,
    ResponseFormat,
    SaveFileInput,
    ViewportScreenshotInput,
)
from ..utils import format_error, format_success, handle_blender_error, parse_blender_response

logger = logging.getLogger(__name__)

_ANNOTATIONS_RO = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


# ---------------------------------------------------------------------------
# Pure implementations — callable without going through MCP/TCP registration
# ---------------------------------------------------------------------------


async def _ping_impl(client: BlenderClient) -> str:
    try:
        response = await client.send_command("ping")
        result = parse_blender_response(response)
        addon_protocol = result.get("protocol_version") if isinstance(result, dict) else None
        if addon_protocol and addon_protocol != BRIDGE_PROTOCOL_VERSION:
            return format_error(
                f"Protocol version mismatch: server={BRIDGE_PROTOCOL_VERSION!r}, "
                f"addon={addon_protocol!r}. "
                "Update blender_addon/mcp_blender_bridge.py to the latest version."
            )
        return format_success(
            {
                "reachable": True,
                "blender_version": result.get("blender_version") if isinstance(result, dict) else None,
                "bridge_version": result.get("bridge_version") if isinstance(result, dict) else None,
                "protocol_version": addon_protocol or "legacy",
            },
            message="Blender bridge is online.",
        )
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _get_scene_info_impl(params: GetSceneInfoInput, client: BlenderClient) -> str:
    try:
        response = await client.send_command("get_scene_info")
        result = parse_blender_response(response)

        if params.response_format == ResponseFormat.JSON:
            return format_success(result)

        lines = [
            "# Blender Scene Overview",
            "",
            f"- **Scene:** {result.get('name', 'Unknown')}",
            f"- **Render engine:** {result.get('engine', 'Unknown')}",
            f"- **Frame range:** {result.get('frame_start')} → {result.get('frame_end')} "
            f"(current: {result.get('frame_current')})",
            f"- **Total objects:** {result.get('object_count', 0)}",
            f"- **Active object:** {result.get('active_object') or '(none)'}",
        ]
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _list_objects_impl(params: ListObjectsInput, client: BlenderClient) -> str:
    try:
        response = await client.send_command(
            "list_objects",
            {"object_type": params.object_type},
        )
        result = parse_blender_response(response)
        objects = result.get("objects", []) if isinstance(result, dict) else result

        if params.response_format == ResponseFormat.JSON:
            return format_success({"count": len(objects), "objects": objects})

        if not objects:
            filt = f" of type `{params.object_type}`" if params.object_type else ""
            return f"No objects{filt} found in the scene."

        lines = [
            f"# Scene Objects ({len(objects)} found)",
            "",
            "| Name | Type | Location |",
            "|------|------|----------|",
        ]
        for obj in objects:
            loc = obj.get("location", [0, 0, 0])
            loc_str = f"({loc[0]:.2f}, {loc[1]:.2f}, {loc[2]:.2f})"
            lines.append(f"| {obj.get('name', '?')} | {obj.get('type', '?')} | {loc_str} |")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _get_object_info_impl(params: GetObjectInfoInput, client: BlenderClient) -> str:
    try:
        response = await client.send_command(
            "get_object_info",
            {"name": params.name},
        )
        result = parse_blender_response(response)

        if params.response_format == ResponseFormat.JSON:
            return format_success(result)

        loc = result.get("location", [0, 0, 0])
        rot = result.get("rotation_euler", [0, 0, 0])
        scl = result.get("scale", [1, 1, 1])
        dim = result.get("dimensions", [0, 0, 0])

        lines = [
            f"# Object: {result.get('name', params.name)}",
            f"**Type:** {result.get('type', 'Unknown')}",
            "",
            "## Transform",
            f"- **Location:** ({loc[0]:.3f}, {loc[1]:.3f}, {loc[2]:.3f})",
            f"- **Rotation (Euler):** ({rot[0]:.3f}, {rot[1]:.3f}, {rot[2]:.3f}) rad",
            f"- **Scale:** ({scl[0]:.3f}, {scl[1]:.3f}, {scl[2]:.3f})",
            f"- **Dimensions:** ({dim[0]:.3f}, {dim[1]:.3f}, {dim[2]:.3f}) m",
            f"- **Visible:** {result.get('visible', True)}",
        ]

        mats = result.get("materials", [])
        if mats:
            lines += ["", "## Materials", *[f"- {m or '(empty slot)'}" for m in mats]]

        if "mesh" in result:
            m = result["mesh"]
            lines += [
                "",
                "## Mesh Stats",
                f"- **Vertices:** {m.get('vertices', 0)}",
                f"- **Edges:** {m.get('edges', 0)}",
                f"- **Faces:** {m.get('faces', 0)}",
            ]

        if "light" in result:
            li = result["light"]
            c = li.get("color", [1, 1, 1])
            lines += [
                "",
                "## Light",
                f"- **Type:** {li.get('type')}",
                f"- **Energy:** {li.get('energy')} W",
                f"- **Color:** ({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})",
            ]

        if "camera" in result:
            cam = result["camera"]
            lines += [
                "",
                "## Camera",
                f"- **Focal length:** {cam.get('lens')} mm",
                f"- **Sensor width:** {cam.get('sensor_width')} mm",
                f"- **Clip range:** {cam.get('clip_start')} – {cam.get('clip_end')} m",
            ]

        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _save_file_impl(params: SaveFileInput, client: BlenderClient) -> str:
    try:
        response = await client.send_command(
            "save_file",
            {"filepath": params.filepath},
        )
        return format_success(response)
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _open_file_impl(params: OpenFileInput, client: BlenderClient) -> str:
    try:
        response = await client.send_command(
            "open_file",
            {"filepath": params.filepath},
        )
        return format_success(response)
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _get_viewport_screenshot_impl(
    params: ViewportScreenshotInput, client: BlenderClient
) -> Any:
    try:
        response = await client.send_command(
            "get_viewport_screenshot",
            {"max_size": params.max_size},
        )
        result = parse_blender_response(response)
        image_bytes = base64.b64decode(result["image_data"])
        return Image(data=image_bytes, format="png")
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, client: BlenderClient) -> None:
    """Register all scene/inspection tools."""

    @mcp.tool(name="blender_ping", annotations={**_ANNOTATIONS_RO, "title": "Ping Blender"})
    async def blender_ping() -> str:
        """Check whether Blender is running and the bridge addon is reachable.

        Use this as the first step before any other tool to confirm the integration is live.

        Returns:
            JSON with `status` and a message indicating reachability.

        Example:
            blender_ping() → {"status": "success", "result": {"reachable": true}}
        """
        return await _ping_impl(client)

    @mcp.tool(
        name="blender_get_scene_info",
        annotations={**_ANNOTATIONS_RO, "title": "Get Blender Scene Info"},
    )
    async def blender_get_scene_info(params: GetSceneInfoInput) -> str:
        """Get an overview of the current Blender scene.

        Returns scene name, frame range, render engine, and total object count.

        Args:
            params: GetSceneInfoInput with response_format ('markdown' or 'json').

        Returns:
            Markdown summary or JSON object describing the scene.

        Example:
            blender_get_scene_info(response_format="json")
        """
        return await _get_scene_info_impl(params, client)

    @mcp.tool(
        name="blender_list_objects",
        annotations={**_ANNOTATIONS_RO, "title": "List Blender Objects"},
    )
    async def blender_list_objects(params: ListObjectsInput) -> str:
        """List objects in the current Blender scene, optionally filtered by type.

        Args:
            params: ListObjectsInput with optional `object_type` filter (e.g. 'MESH')
                and `response_format`.

        Returns:
            Markdown table or JSON list of objects with name, type, and location.

        Example:
            blender_list_objects(object_type="MESH", response_format="json")
        """
        return await _list_objects_impl(params, client)

    @mcp.tool(
        name="blender_get_object_info",
        annotations={**_ANNOTATIONS_RO, "title": "Get Object Info"},
    )
    async def blender_get_object_info(params: GetObjectInfoInput) -> str:
        """Get detailed information about a specific object by name.

        Returns transform, dimensions, material slots, and type-specific data
        (mesh stats for MESH, light settings for LIGHT, focal length for CAMERA).

        Args:
            params: GetObjectInfoInput with the object `name` and `response_format`.

        Returns:
            Markdown summary or JSON with full object properties.

        Example:
            blender_get_object_info(name="Cube")
        """
        return await _get_object_info_impl(params, client)

    @mcp.tool(
        name="blender_save_file",
        annotations={
            "title": "Save Blender File",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def blender_save_file(params: SaveFileInput) -> str:
        """Save the current Blender scene to a .blend file.

        Args:
            params: SaveFileInput with optional `filepath`. Uses the currently
                open file path if omitted.

        Returns:
            JSON with the path the file was saved to.

        Example:
            blender_save_file(filepath="/tmp/my_scene.blend")
            blender_save_file()  # saves to current file path
        """
        return await _save_file_impl(params, client)

    @mcp.tool(
        name="blender_open_file",
        annotations={
            "title": "Open Blender File",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def blender_open_file(params: OpenFileInput) -> str:
        """Open a .blend file in Blender, replacing the current scene.

        WARNING: Unsaved changes to the current scene will be lost.

        Args:
            params: OpenFileInput with `filepath` (absolute path to .blend file).

        Returns:
            JSON confirming the file that was opened.

        Example:
            blender_open_file(filepath="/home/user/projects/scene.blend")
        """
        return await _open_file_impl(params, client)

    @mcp.tool(
        name="blender_get_viewport_screenshot",
        annotations={**_ANNOTATIONS_RO, "title": "Get Viewport Screenshot"},
    )
    async def blender_get_viewport_screenshot(params: ViewportScreenshotInput):  # noqa: ANN201
        """Capture a screenshot of the current Blender 3D viewport.

        Renders using OpenGL and returns the image inline. Great for inspecting
        the current state of the scene visually.

        Args:
            params: ViewportScreenshotInput with `max_size` (default 800px).

        Returns:
            An inline PNG image of the viewport, or an error string if capture fails.

        Example:
            blender_get_viewport_screenshot(max_size=1024)
        """
        return await _get_viewport_screenshot_impl(params, client)
