"""Modal mesh editing tools — extrude, loop cut, bevel, knife, sculpt.

Extrude / loop_cut / bevel: EXEC_DEFAULT (fully deterministic, no user input).
Knife / sculpt: INVOKE_DEFAULT on the addon side; require an active Blender window.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from ..client import BlenderClient
from ..schemas import (
    ModalBevelInput,
    ModalExtrudeInput,
    ModalKnifeCutInput,
    ModalLoopCutInput,
    ModalSculptInput,
)
from ..utils import (
    check_read_only,
    format_success,
    handle_blender_error,
    parse_blender_response,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure implementations
# ---------------------------------------------------------------------------


async def _modal_extrude_impl(
    params: ModalExtrudeInput, client: BlenderClient, read_only: bool = False
) -> str:
    """EXEC_DEFAULT — extrude selected faces along direction by distance."""
    if err := check_read_only(read_only):
        return err
    try:
        response = await client.send_command(
            "modal_extrude",
            {
                "object_name": params.object_name,
                "direction": params.direction,
                "distance": params.distance,
            },
        )
        result = parse_blender_response(response)
        return format_success(
            result,
            message=f"Extruded '{params.object_name}' {params.direction} by {params.distance}.",
        )
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _modal_loop_cut_impl(
    params: ModalLoopCutInput, client: BlenderClient, read_only: bool = False
) -> str:
    """EXEC_DEFAULT — insert edge loop on edge_index with factor slide."""
    if err := check_read_only(read_only):
        return err
    try:
        response = await client.send_command(
            "modal_loop_cut",
            {
                "object_name": params.object_name,
                "edge_index": params.edge_index,
                "cuts": params.cuts,
                "factor": params.factor,
            },
        )
        result = parse_blender_response(response)
        return format_success(
            result,
            message=f"Loop cut '{params.object_name}': {params.cuts} cut(s) at edge {params.edge_index}.",
        )
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _modal_knife_cut_impl(
    params: ModalKnifeCutInput, client: BlenderClient, read_only: bool = False
) -> str:
    """INVOKE_DEFAULT — interactive knife cut along screen-space points.

    Requires an active Blender window. In headless mode the command
    falls back to bpy.ops.mesh.bisect using the first two points.
    """
    if err := check_read_only(read_only):
        return err
    try:
        response = await client.send_command(
            "modal_knife_cut",
            {
                "object_name": params.object_name,
                "points": [list(p) for p in params.points],
            },
        )
        result = parse_blender_response(response)
        return format_success(
            result,
            message=f"Knife cut '{params.object_name}' through {len(params.points)} points.",
        )
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _modal_bevel_impl(
    params: ModalBevelInput, client: BlenderClient, read_only: bool = False
) -> str:
    """EXEC_DEFAULT — bevel selected edges/vertices."""
    if err := check_read_only(read_only):
        return err
    try:
        response = await client.send_command(
            "modal_bevel",
            {
                "object_name": params.object_name,
                "width": params.width,
                "segments": params.segments,
            },
        )
        result = parse_blender_response(response)
        return format_success(
            result,
            message=f"Beveled '{params.object_name}' width={params.width} segments={params.segments}.",
        )
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


async def _modal_sculpt_impl(
    params: ModalSculptInput, client: BlenderClient, read_only: bool = False
) -> str:
    """INVOKE_DEFAULT — enter sculpt mode with specified brush and strength.

    Sets mode + brush; actual strokes are controlled interactively or via
    follow-up sculpt_stroke commands.
    """
    if err := check_read_only(read_only):
        return err
    try:
        response = await client.send_command(
            "modal_sculpt",
            {
                "object_name": params.object_name,
                "brush": params.brush,
                "strength": params.strength,
            },
        )
        result = parse_blender_response(response)
        return format_success(
            result,
            message=f"Entered sculpt mode on '{params.object_name}' with brush {params.brush}.",
        )
    except Exception as exc:  # noqa: BLE001
        return handle_blender_error(exc)


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, client: BlenderClient, *, read_only: bool = False) -> None:
    @mcp.tool()
    async def blender_modal_extrude(
        object_name: str,
        direction: str = "normal",
        distance: float = 1.0,
    ) -> str:
        """Extrude selected faces of a mesh object along a direction.

        direction: 'x', 'y', 'z', or 'normal' (face normal).
        distance: signed extrusion length in Blender units.
        """
        params = ModalExtrudeInput(
            object_name=object_name,
            direction=direction,
            distance=distance,
        )
        return await _modal_extrude_impl(params, client, read_only)

    @mcp.tool()
    async def blender_modal_loop_cut(
        object_name: str,
        edge_index: int,
        cuts: int = 1,
        factor: float = 0.0,
    ) -> str:
        """Insert one or more edge loops into a mesh.

        edge_index: index of the edge to cut through.
        cuts: number of parallel loops (1–64).
        factor: slide offset from center (-1.0 to 1.0).
        """
        params = ModalLoopCutInput(
            object_name=object_name,
            edge_index=edge_index,
            cuts=cuts,
            factor=factor,
        )
        return await _modal_loop_cut_impl(params, client, read_only)

    @mcp.tool()
    async def blender_modal_knife_cut(
        object_name: str,
        points: list[list[float]],
    ) -> str:
        """Cut through a mesh with a knife path.

        points: list of 2-element [x, y] screen-space coordinates defining the cut path.
        Requires at least 2 points and at most 32.
        In headless mode falls back to bisect using first two points.
        """
        parsed_points: list[tuple[float, float]] = [(p[0], p[1]) for p in points]
        params = ModalKnifeCutInput(
            object_name=object_name,
            points=parsed_points,
        )
        return await _modal_knife_cut_impl(params, client, read_only)

    @mcp.tool()
    async def blender_modal_bevel(
        object_name: str,
        width: float = 0.01,
        segments: int = 1,
    ) -> str:
        """Bevel selected edges or vertices of a mesh.

        width: bevel width in Blender units (0 < width < 10).
        segments: number of bevel segments (1–16).
        """
        params = ModalBevelInput(
            object_name=object_name,
            width=width,
            segments=segments,
        )
        return await _modal_bevel_impl(params, client, read_only)

    @mcp.tool()
    async def blender_modal_sculpt(
        object_name: str,
        brush: str = "DRAW",
        strength: float = 0.5,
    ) -> str:
        """Enter sculpt mode on an object with specified brush settings.

        brush: Blender sculpt brush name (e.g. 'DRAW', 'SMOOTH', 'INFLATE').
        strength: brush strength 0.0–1.0.
        """
        params = ModalSculptInput(
            object_name=object_name,
            brush=brush,
            strength=strength,
        )
        return await _modal_sculpt_impl(params, client, read_only)
