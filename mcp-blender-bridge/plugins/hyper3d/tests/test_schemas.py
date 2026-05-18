"""Tests for Hyper3D Rodin input schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_blender_bridge_hyper3d.schemas import (
    Hyper3DGenerateImageParams,
    Hyper3DGenerateTextParams,
    Hyper3DImportParams,
    Hyper3DPollParams,
    Hyper3DStatusParams,
)


class TestHyper3DStatusParams:
    def test_no_fields_required(self) -> None:
        p = Hyper3DStatusParams()
        assert p is not None

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DStatusParams(**{"unexpected": "field"})  # type: ignore[call-overload]


class TestHyper3DGenerateTextParams:
    def test_prompt_required(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DGenerateTextParams()  # type: ignore[call-overload]

    def test_prompt_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DGenerateTextParams(prompt="")

    def test_defaults(self) -> None:
        p = Hyper3DGenerateTextParams(prompt="a wooden chair")
        assert p.tier == "Regular"
        assert p.mesh_mode == "Refined"
        assert p.seed is None

    def test_tier_literal(self) -> None:
        p = Hyper3DGenerateTextParams(prompt="test", tier="Sketch")
        assert p.tier == "Sketch"
        with pytest.raises(ValidationError):
            Hyper3DGenerateTextParams(prompt="test", tier="Invalid")  # type: ignore[call-overload]

    def test_mesh_mode_literal(self) -> None:
        p = Hyper3DGenerateTextParams(prompt="test", mesh_mode="Raw")
        assert p.mesh_mode == "Raw"
        with pytest.raises(ValidationError):
            Hyper3DGenerateTextParams(prompt="test", mesh_mode="BadMode")  # type: ignore[call-overload]

    def test_seed_optional(self) -> None:
        p = Hyper3DGenerateTextParams(prompt="test", seed=42)
        assert p.seed == 42

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DGenerateTextParams(prompt="test", extra_field="bad")  # type: ignore[call-overload]


class TestHyper3DGenerateImageParams:
    def test_all_optional(self) -> None:
        # Both image_url and image_path are optional at schema level
        p = Hyper3DGenerateImageParams()
        assert p.image_url is None
        assert p.image_path is None

    def test_image_url_accepted(self) -> None:
        p = Hyper3DGenerateImageParams(image_url="https://example.com/img.jpg")
        assert p.image_url == "https://example.com/img.jpg"

    def test_image_path_accepted(self) -> None:
        p = Hyper3DGenerateImageParams(image_path="/tmp/photo.jpg")
        assert p.image_path == "/tmp/photo.jpg"

    def test_defaults(self) -> None:
        p = Hyper3DGenerateImageParams(image_url="https://x.com/a.jpg")
        assert p.tier == "Regular"
        assert p.mesh_mode == "Refined"
        assert p.seed is None

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DGenerateImageParams(bad_field="oops")  # type: ignore[call-overload]


class TestHyper3DPollParams:
    def test_task_uuid_required(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DPollParams()  # type: ignore[call-overload]

    def test_task_uuid_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DPollParams(task_uuid="")

    def test_default_max_wait(self) -> None:
        p = Hyper3DPollParams(task_uuid="abc-123")
        assert p.max_wait == 300

    def test_max_wait_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DPollParams(task_uuid="x", max_wait=5)  # below min=10
        with pytest.raises(ValidationError):
            Hyper3DPollParams(task_uuid="x", max_wait=700)  # above max=600

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DPollParams(task_uuid="x", nope="y")  # type: ignore[call-overload]


class TestHyper3DImportParams:
    def test_task_uuid_required(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DImportParams()  # type: ignore[call-overload]

    def test_defaults(self) -> None:
        p = Hyper3DImportParams(task_uuid="abc-123")
        assert p.import_format == "glb"
        assert p.object_name is None

    def test_import_format_literal(self) -> None:
        for fmt in ("glb", "fbx", "obj", "stl"):
            p = Hyper3DImportParams(task_uuid="x", import_format=fmt)  # type: ignore[call-overload]
            assert p.import_format == fmt
        with pytest.raises(ValidationError):
            Hyper3DImportParams(task_uuid="x", import_format="dae")  # type: ignore[call-overload]

    def test_object_name_optional(self) -> None:
        p = Hyper3DImportParams(task_uuid="x", object_name="MyRodinMesh")
        assert p.object_name == "MyRodinMesh"

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Hyper3DImportParams(task_uuid="x", surprise="!!")  # type: ignore[call-overload]
