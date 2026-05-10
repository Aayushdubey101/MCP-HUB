"""Pydantic v2 input schemas for the Hyper3D Rodin plugin.

All models use ``extra="forbid"`` to reject unexpected fields at the boundary,
consistent with the AGENTS.md Pydantic v2 convention for this workspace.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Hyper3DStatusParams(BaseModel):
    """Parameters for hyper3d_status — no required fields."""

    model_config = {"extra": "forbid"}


class Hyper3DGenerateTextParams(BaseModel):
    """Parameters for generating a 3D model from a text prompt."""

    model_config = {"extra": "forbid"}

    prompt: str = Field(..., min_length=1, description="Text description of the 3D object to generate.")
    tier: Literal["Regular", "Sketch"] = Field(
        default="Regular",
        description="Generation quality tier. 'Regular' is higher quality; 'Sketch' is faster.",
    )
    mesh_mode: Literal["Raw", "Refined"] = Field(
        default="Refined",
        description="Mesh processing mode. 'Refined' produces cleaner geometry.",
    )
    seed: int | None = Field(
        default=None,
        description="Optional random seed for reproducible generation.",
    )


class Hyper3DGenerateImageParams(BaseModel):
    """Parameters for generating a 3D model from one or more reference images."""

    model_config = {"extra": "forbid"}

    image_url: str | None = Field(
        default=None,
        description="Publicly accessible URL of the reference image.",
    )
    image_path: str | None = Field(
        default=None,
        description="Local file path of the reference image to upload.",
    )
    tier: Literal["Regular", "Sketch"] = Field(
        default="Regular",
        description="Generation quality tier.",
    )
    mesh_mode: Literal["Raw", "Refined"] = Field(
        default="Refined",
        description="Mesh processing mode.",
    )
    seed: int | None = Field(
        default=None,
        description="Optional random seed for reproducible generation.",
    )


class Hyper3DPollParams(BaseModel):
    """Parameters for polling the status of a Rodin generation task."""

    model_config = {"extra": "forbid"}

    task_uuid: str = Field(..., min_length=1, description="The task UUID returned by generate_text or generate_image.")
    max_wait: int = Field(
        default=300,
        ge=10,
        le=600,
        description="Maximum seconds to wait for completion when polling. Default: 300.",
    )


class Hyper3DImportParams(BaseModel):
    """Parameters for downloading and importing a completed Rodin model into Blender."""

    model_config = {"extra": "forbid"}

    task_uuid: str = Field(..., min_length=1, description="The task UUID of the completed generation job.")
    object_name: str | None = Field(
        default=None,
        description="Optional name to assign to the imported object in Blender.",
    )
    import_format: Literal["glb", "fbx", "obj", "stl"] = Field(
        default="glb",
        description="3D file format to download and import. Defaults to 'glb'.",
    )
