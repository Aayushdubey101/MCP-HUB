"""Pydantic v2 input schemas for the Sketchfab plugin.

All models use ``extra="forbid"`` to reject unexpected fields.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SketchfabStatusParams(BaseModel):
    """Parameters for sketchfab_status — no required fields."""

    model_config = {"extra": "forbid"}


class SketchfabSearchParams(BaseModel):
    """Parameters for searching Sketchfab's 3D model library."""

    model_config = {"extra": "forbid"}

    query: str = Field(..., min_length=1, description="Search keywords, e.g. 'wooden chair'.")
    count: int = Field(
        default=24,
        ge=1,
        le=100,
        description="Number of results to return (1–100). Default: 24.",
    )
    downloadable: bool = Field(
        default=True,
        description="Restrict to models with a free download available. Default: True.",
    )
    animated: bool | None = Field(
        default=None,
        description="Filter to animated models only. None = no filter.",
    )
    categories: str | None = Field(
        default=None,
        description="Comma-separated category slugs, e.g. 'architecture,nature'.",
    )
    sort_by: Literal["-publishedAt", "-likeCount", "-viewCount", "relevance"] = Field(
        default="relevance",
        description="Sort order for results.",
    )


class SketchfabPreviewParams(BaseModel):
    """Parameters for getting detailed metadata about a single Sketchfab model."""

    model_config = {"extra": "forbid"}

    uid: str = Field(
        ..., min_length=1, description="The Sketchfab model UID (from search results)."
    )


class SketchfabDownloadParams(BaseModel):
    """Parameters for downloading a Sketchfab GLTF model and importing it into Blender."""

    model_config = {"extra": "forbid"}

    uid: str = Field(
        ..., min_length=1, description="The Sketchfab model UID to download."
    )
    object_name: str | None = Field(
        default=None,
        description="Optional name to assign to the imported object in Blender.",
    )
