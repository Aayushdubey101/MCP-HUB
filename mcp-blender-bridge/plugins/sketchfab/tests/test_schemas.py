"""Tests for Sketchfab schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_blender_bridge_sketchfab.schemas import (
    SketchfabDownloadParams,
    SketchfabPreviewParams,
    SketchfabSearchParams,
    SketchfabStatusParams,
)


class TestSketchfabStatusParams:
    def test_no_fields_required(self) -> None:
        p = SketchfabStatusParams()
        assert p is not None

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabStatusParams(**{"nope": "x"})


class TestSketchfabSearchParams:
    def test_query_required(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabSearchParams()

    def test_query_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabSearchParams(query="")

    def test_defaults(self) -> None:
        p = SketchfabSearchParams(query="chair")
        assert p.count == 24
        assert p.downloadable is True
        assert p.animated is None
        assert p.sort_by == "relevance"

    def test_count_bounds(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabSearchParams(query="x", count=0)
        with pytest.raises(ValidationError):
            SketchfabSearchParams(query="x", count=101)
        p = SketchfabSearchParams(query="x", count=100)
        assert p.count == 100

    def test_sort_by_literal(self) -> None:
        p = SketchfabSearchParams(query="x", sort_by="-likeCount")
        assert p.sort_by == "-likeCount"
        with pytest.raises(ValidationError):
            SketchfabSearchParams(query="x", sort_by="invalid")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabSearchParams(query="x", foo="bar")


class TestSketchfabPreviewParams:
    def test_uid_required(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabPreviewParams()

    def test_uid_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabPreviewParams(uid="")

    def test_valid(self) -> None:
        p = SketchfabPreviewParams(uid="abc123")
        assert p.uid == "abc123"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabPreviewParams(uid="x", extra="y")


class TestSketchfabDownloadParams:
    def test_uid_required(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabDownloadParams()

    def test_object_name_optional(self) -> None:
        p = SketchfabDownloadParams(uid="abc123")
        assert p.object_name is None

    def test_object_name_accepted(self) -> None:
        p = SketchfabDownloadParams(uid="abc123", object_name="MyMesh")
        assert p.object_name == "MyMesh"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SketchfabDownloadParams(uid="x", nope=True)
