"""Object manipulation tools — create, transform, delete, material, light, camera."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from ..client import BlenderClient
from ..schemas import (
    AddLightInput,
    CreatePrimitiveInput,
    DeleteObjectInput,
    SetCameraInput,
    SetMaterialInput,
    TransformObjectInput,
)
from ..utils import (
    check_read_only,
    format_error,
    format_success,
    handle_blender_error,
    parse_blender_response,
)

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, client: BlenderClient, *, read_only: bool = False) -> None:
    """Register all object manipulation tools."""

    @mcp.tool(
        name="blender_create_primitive",
        annotations={
            "title": "Create Primitive Mesh",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def blender_create_primitive(params: CreatePrimitiveInput) -> str:
        """Create a primitive mesh (cube, sphere, cylinder, etc.) in the scene.

        Args:
            params: CreatePrimitiveInput with primitive_type, optional name,
                location (x, y, z), and size.

        Returns:
            JSON describing the newly created object.

        Example:
            blender_create_primitive(primitive_type="cube", name="MyCube", location=(0,0,1))
        """
        if err := check_read_only(read_only):
            return err
        try:
            response = await client.send_command(
                "create_primitive",
                {
                    "primitive_type": params.primitive_type.value,
                    "name": params.name,
                    "location": list(params.location),
                    "size": params.size,
                },
            )
            result = parse_blender_response(response)
            return format_success(
                result,
                message=f"Created {params.primitive_type.value} '{result.get('name', 'unnamed')}'.",
            )
        except Exception as exc:  # noqa: BLE001
            return handle_blender_error(exc)

    @mcp.tool(
        name="blender_transform_object",
        annotations={
            "title": "Transform Object",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def blender_transform_object(params: TransformObjectInput) -> str:
        """Set location, rotation, and/or scale of an existing object.

        Any field left as `None` is left unchanged. This is idempotent — calling
        with the same values is a no-op.

        Args:
            params: TransformObjectInput with the target object name and any
                combination of `location`, `rotation_euler`, and `scale`.

        Returns:
            JSON with the updated transform values.

        Example:
            blender_transform_object(name="Cube", location=(1,0,0), scale=(2,2,2))
        """
        if err := check_read_only(read_only):
            return err
        if all(v is None for v in (params.location, params.rotation_euler, params.scale)):
            return format_error(
                "No transform values provided. Specify at least one of: "
                "location, rotation_euler, or scale."
            )

        try:
            response = await client.send_command(
                "transform_object",
                {
                    "name": params.name,
                    "location": list(params.location) if params.location else None,
                    "rotation_euler": (
                        list(params.rotation_euler) if params.rotation_euler else None
                    ),
                    "scale": list(params.scale) if params.scale else None,
                },
            )
            result = parse_blender_response(response)
            return format_success(result, message=f"Transformed '{params.name}'.")
        except Exception as exc:  # noqa: BLE001
            return handle_blender_error(exc)

    @mcp.tool(
        name="blender_delete_object",
        annotations={
            "title": "Delete Object",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def blender_delete_object(params: DeleteObjectInput) -> str:
        """Delete an object from the scene by name.

        DESTRUCTIVE: permanently removes the object. Idempotent: deleting a
        missing object returns success with a note.

        Args:
            params: DeleteObjectInput with the exact `name` of the object to delete.

        Returns:
            JSON confirming the deletion.

        Example:
            blender_delete_object(name="Cube")
        """
        if err := check_read_only(read_only):
            return err
        try:
            response = await client.send_command(
                "delete_object",
                {"name": params.name},
            )
            result = parse_blender_response(response)
            return format_success(result, message=f"Deleted '{params.name}'.")
        except Exception as exc:  # noqa: BLE001
            return handle_blender_error(exc)

    @mcp.tool(
        name="blender_set_material",
        annotations={
            "title": "Set Object Material",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def blender_set_material(params: SetMaterialInput) -> str:
        """Apply a PBR material to an object using Principled BSDF.

        Creates or updates a material with the given base color, metallic, roughness,
        and optional emission. Assigns it to the first material slot of the object.

        Args:
            params: SetMaterialInput with object_name, color (RGBA), metallic,
                roughness, optional material_name, and optional emission.

        Returns:
            JSON with the material name and applied properties.

        Example:
            blender_set_material(object_name="Cube", color=(0.2, 0.4, 0.8, 1.0), metallic=0.9)
        """
        if err := check_read_only(read_only):
            return err
        try:
            response = await client.send_command(
                "set_material",
                {
                    "object_name": params.object_name,
                    "color": list(params.color),
                    "metallic": params.metallic,
                    "roughness": params.roughness,
                    "material_name": params.material_name,
                    "emission_color": list(params.emission_color)
                    if params.emission_color
                    else None,
                    "emission_strength": params.emission_strength,
                },
            )
            result = parse_blender_response(response)
            return format_success(
                result,
                message=f"Applied material '{result.get('material')}' to '{params.object_name}'.",
            )
        except Exception as exc:  # noqa: BLE001
            return handle_blender_error(exc)

    @mcp.tool(
        name="blender_add_light",
        annotations={
            "title": "Add Light",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    async def blender_add_light(params: AddLightInput) -> str:
        """Add a light source to the scene.

        Supports POINT (omnidirectional), SUN (directional), SPOT (cone), and
        AREA (panel) lights.

        Args:
            params: AddLightInput with light_type, optional name, location,
                energy, color, and type-specific settings (spot_size, size, etc.).

        Returns:
            JSON with the light object name and properties.

        Example:
            blender_add_light(light_type="POINT", location=(0, 0, 4), energy=2000)
        """
        if err := check_read_only(read_only):
            return err
        try:
            response = await client.send_command(
                "add_light",
                {
                    "light_type": params.light_type.value,
                    "name": params.name,
                    "location": list(params.location),
                    "energy": params.energy,
                    "color": list(params.color),
                    "radius": params.radius,
                    "spot_size": params.spot_size,
                    "spot_blend": params.spot_blend,
                    "size": params.size,
                },
            )
            result = parse_blender_response(response)
            return format_success(
                result,
                message=f"Added {params.light_type.value} light '{result.get('name')}'.",
            )
        except Exception as exc:  # noqa: BLE001
            return handle_blender_error(exc)

    @mcp.tool(
        name="blender_set_camera",
        annotations={
            "title": "Set Camera",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def blender_set_camera(params: SetCameraInput) -> str:
        """Configure a camera's position, aim target, and focal length.

        Uses the active scene camera if no name is given. Creates a new camera if
        the scene has none. Optionally points the camera at a 3D target point.

        Args:
            params: SetCameraInput with optional name, location, target (point to
                aim at), lens (focal length in mm), and set_active flag.

        Returns:
            JSON with the camera name, location, rotation, and lens.

        Example:
            blender_set_camera(location=(5, -5, 3), target=(0, 0, 0), lens=50)
        """
        if err := check_read_only(read_only):
            return err
        try:
            response = await client.send_command(
                "set_camera",
                {
                    "name": params.name,
                    "location": list(params.location) if params.location else None,
                    "target": list(params.target) if params.target else None,
                    "lens": params.lens,
                    "set_active": params.set_active,
                },
            )
            result = parse_blender_response(response)
            return format_success(
                result,
                message=f"Camera '{result.get('name')}' configured.",
            )
        except Exception as exc:  # noqa: BLE001
            return handle_blender_error(exc)
