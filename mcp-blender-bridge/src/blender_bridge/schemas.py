"""Pydantic input schemas for MCP Blender Bridge tools.

All tools use Pydantic models for input validation. This keeps validation
declarative and lets FastMCP auto-generate accurate input schemas.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


class StrictModel(BaseModel):
    """Base model with strict validation defaults shared by all inputs."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


class PrimitiveType(str, Enum):
    """Supported primitive mesh types for `blender_create_primitive`."""

    CUBE = "cube"
    SPHERE = "sphere"
    CYLINDER = "cylinder"
    CONE = "cone"
    PLANE = "plane"
    TORUS = "torus"
    MONKEY = "monkey"  # Suzanne


class LightType(str, Enum):
    """Blender light types for `blender_add_light`."""

    POINT = "POINT"
    SUN = "SUN"
    SPOT = "SPOT"
    AREA = "AREA"


# ---------------------------------------------------------------------------
# Scene / inspection schemas
# ---------------------------------------------------------------------------


class GetSceneInfoInput(StrictModel):
    """Input for `blender_get_scene_info`."""

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' for human-readable, 'json' for structured data.",
    )


class ListObjectsInput(StrictModel):
    """Input for `blender_list_objects`."""

    object_type: str | None = Field(
        default=None,
        description=(
            "Filter by Blender object type, e.g. 'MESH', 'LIGHT', 'CAMERA', 'EMPTY'. "
            "If omitted, returns objects of all types."
        ),
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class GetObjectInfoInput(StrictModel):
    """Input for `blender_get_object_info`."""

    name: str = Field(
        ...,
        description="Exact object name (case-sensitive).",
        min_length=1,
        max_length=63,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'.",
    )


class ViewportScreenshotInput(StrictModel):
    """Input for `blender_get_viewport_screenshot`."""

    max_size: int = Field(
        default=800,
        ge=64,
        le=4096,
        description="Maximum width or height of the screenshot in pixels.",
    )


# ---------------------------------------------------------------------------
# Object manipulation schemas
# ---------------------------------------------------------------------------


class CreatePrimitiveInput(StrictModel):
    """Input for `blender_create_primitive`."""

    primitive_type: PrimitiveType = Field(
        ...,
        description="Type of primitive mesh to create (e.g., 'cube', 'sphere', 'monkey').",
    )
    name: str | None = Field(
        default=None,
        description="Optional name for the new object. Blender auto-names if omitted.",
        min_length=1,
        max_length=63,
    )
    location: tuple[float, float, float] = Field(
        default=(0.0, 0.0, 0.0),
        description="World-space location as (x, y, z). Defaults to origin.",
    )
    size: float = Field(
        default=2.0,
        description="Size of the primitive (radius for sphere/cylinder, edge for cube).",
        gt=0.0,
        le=1000.0,
    )


class TransformObjectInput(StrictModel):
    """Input for `blender_transform_object`."""

    name: str = Field(
        ...,
        description="Exact name of the object to transform.",
        min_length=1,
        max_length=63,
    )
    location: tuple[float, float, float] | None = Field(
        default=None,
        description="New (x, y, z) location. Omit to leave unchanged.",
    )
    rotation_euler: tuple[float, float, float] | None = Field(
        default=None,
        description="New (x, y, z) Euler rotation in radians. Omit to leave unchanged.",
    )
    scale: tuple[float, float, float] | None = Field(
        default=None,
        description="New (x, y, z) scale factors. Omit to leave unchanged.",
    )


class DeleteObjectInput(StrictModel):
    """Input for `blender_delete_object`."""

    name: str = Field(
        ...,
        description="Exact name of the object to delete (case-sensitive).",
        min_length=1,
        max_length=63,
    )


class SetMaterialInput(StrictModel):
    """Input for `blender_set_material`."""

    object_name: str = Field(
        ...,
        description="Exact name of the object to apply the material to.",
        min_length=1,
        max_length=63,
    )
    color: tuple[float, float, float, float] = Field(
        default=(0.8, 0.8, 0.8, 1.0),
        description="RGBA base color, each channel 0.0–1.0.",
    )
    metallic: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Metallic value (0 = dielectric, 1 = metal).",
    )
    roughness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Roughness value (0 = mirror, 1 = fully diffuse).",
    )
    material_name: str | None = Field(
        default=None,
        description="Name for the material. Auto-generated if omitted.",
        min_length=1,
        max_length=63,
    )
    emission_color: tuple[float, float, float] | None = Field(
        default=None,
        description="RGB emission color. Set to enable glow effect.",
    )
    emission_strength: float = Field(
        default=0.0,
        ge=0.0,
        le=1_000_000.0,
        description="Emission strength in watts per square meter.",
    )


class AddLightInput(StrictModel):
    """Input for `blender_add_light`."""

    light_type: LightType = Field(
        ...,
        description="Light type: POINT (omnidirectional), SUN (directional), SPOT (cone), AREA (panel).",
    )
    name: str | None = Field(
        default=None,
        description="Optional name for the light object.",
        min_length=1,
        max_length=63,
    )
    location: tuple[float, float, float] = Field(
        default=(0.0, 0.0, 3.0),
        description="World-space location as (x, y, z).",
    )
    energy: float = Field(
        default=1000.0,
        gt=0.0,
        le=1_000_000.0,
        description="Light energy in watts (POINT/SPOT/AREA) or irradiance (SUN).",
    )
    color: tuple[float, float, float] = Field(
        default=(1.0, 1.0, 1.0),
        description="RGB light color, each channel 0.0–1.0.",
    )
    radius: float = Field(
        default=0.1,
        ge=0.0,
        le=1000.0,
        description="Light source radius (soft shadows). POINT/SPOT only.",
    )
    spot_size: float = Field(
        default=45.0,
        ge=1.0,
        le=180.0,
        description="Spot cone half-angle in degrees. SPOT lights only.",
    )
    spot_blend: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Spot edge softness. SPOT lights only.",
    )
    size: float = Field(
        default=1.0,
        gt=0.0,
        le=1000.0,
        description="Area light size in meters. AREA lights only.",
    )


class SetCameraInput(StrictModel):
    """Input for `blender_set_camera`."""

    name: str | None = Field(
        default=None,
        description="Camera object name. Uses the active scene camera if omitted.",
        min_length=1,
        max_length=63,
    )
    location: tuple[float, float, float] | None = Field(
        default=None,
        description="New (x, y, z) camera position. Omit to leave unchanged.",
    )
    target: tuple[float, float, float] | None = Field(
        default=None,
        description="Point in 3D space for the camera to aim at. Omit to leave rotation unchanged.",
    )
    lens: float | None = Field(
        default=None,
        ge=1.0,
        le=5000.0,
        description="Focal length in mm (e.g. 50 for normal, 24 for wide, 200 for telephoto).",
    )
    set_active: bool = Field(
        default=True,
        description="Make this camera the active render camera.",
    )


# ---------------------------------------------------------------------------
# Render schemas
# ---------------------------------------------------------------------------


class RenderEngine(str, Enum):
    """Blender render engines."""

    EEVEE = "BLENDER_EEVEE"
    EEVEE_NEXT = "BLENDER_EEVEE_NEXT"  # Blender 4.2+
    CYCLES = "CYCLES"
    WORKBENCH = "BLENDER_WORKBENCH"


class RenderImageInput(StrictModel):
    """Input for `blender_render_image`."""

    frame: int | None = Field(
        default=None,
        ge=0,
        le=1_000_000,
        description="Frame number to render. Uses the scene's current frame if omitted.",
    )
    output_path: str | None = Field(
        default=None,
        description=(
            "Absolute path to save the render (e.g. '/tmp/render.png'). "
            "Saves to the scene's configured render path if omitted."
        ),
    )
    engine: RenderEngine | None = Field(
        default=None,
        description="Override render engine for this render only. Restores original engine afterward.",
    )
    samples: int | None = Field(
        default=None,
        ge=1,
        le=65_536,
        description="Override Cycles sample count for this render only. No effect on EEVEE.",
    )
    max_preview_size: int = Field(
        default=512,
        ge=64,
        le=2048,
        description="Max pixel dimension of the inline image preview returned alongside metadata.",
    )
    timeout_seconds: float = Field(
        default=300.0,
        ge=10.0,
        le=3600.0,
        description="Max seconds to wait for render to complete. Increase for complex Cycles renders.",
    )


# ---------------------------------------------------------------------------
# File management schemas
# ---------------------------------------------------------------------------


class SaveFileInput(StrictModel):
    """Input for `blender_save_file`."""

    filepath: str | None = Field(
        default=None,
        description=(
            "Absolute path to save the .blend file. "
            "Uses the currently open file path if omitted."
        ),
        min_length=1,
        max_length=4096,
    )


class OpenFileInput(StrictModel):
    """Input for `blender_open_file`."""

    filepath: str = Field(
        ...,
        description="Absolute path to the .blend file to open.",
        min_length=1,
        max_length=4096,
    )


# ---------------------------------------------------------------------------
# Code execution schema
# ---------------------------------------------------------------------------


class ExecutePythonInput(StrictModel):
    """Input for `blender_execute_python`.

    Power-user tool: runs arbitrary Python code inside Blender.
    Use sparingly and only when no dedicated tool fits.
    """

    code: str = Field(
        ...,
        description=(
            "Python source code to execute inside Blender. Has access to `bpy`. "
            "Set a variable named `result` to return data back to the caller."
        ),
        min_length=1,
        max_length=20_000,
    )
