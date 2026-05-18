"""Tests for the Pydantic input schemas.

These tests don't require Blender to be running — they only validate the
input schema layer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from blender_bridge.schemas import (
    AddLightInput,
    CreatePrimitiveInput,
    DeleteObjectInput,
    ExecutePythonInput,
    GetObjectInfoInput,
    GetSceneInfoInput,
    LightType,
    ListObjectsInput,
    PrimitiveType,
    RenderEngine,
    RenderImageInput,
    ResponseFormat,
    SetCameraInput,
    SetMaterialInput,
    TransformObjectInput,
    ViewportScreenshotInput,
)

# ---------------------------------------------------------------------------
# CreatePrimitiveInput
# ---------------------------------------------------------------------------


class TestCreatePrimitiveInput:
    def test_valid_minimal(self):
        p = CreatePrimitiveInput(primitive_type="cube")
        assert p.primitive_type == PrimitiveType.CUBE
        assert p.location == (0.0, 0.0, 0.0)
        assert p.size == 2.0
        assert p.name is None

    def test_valid_full(self):
        p = CreatePrimitiveInput(
            primitive_type="sphere",
            name="MySphere",
            location=(1.0, 2.0, 3.0),
            size=5.0,
        )
        assert p.primitive_type == PrimitiveType.SPHERE
        assert p.name == "MySphere"
        assert p.location == (1.0, 2.0, 3.0)

    def test_all_primitive_types(self):
        for pt in PrimitiveType:
            p = CreatePrimitiveInput(primitive_type=pt.value)
            assert p.primitive_type == pt

    def test_invalid_primitive_type(self):
        with pytest.raises(ValidationError):
            CreatePrimitiveInput(primitive_type="dodecahedron")

    def test_invalid_size_zero(self):
        with pytest.raises(ValidationError):
            CreatePrimitiveInput(primitive_type="cube", size=0.0)

    def test_invalid_size_negative(self):
        with pytest.raises(ValidationError):
            CreatePrimitiveInput(primitive_type="cube", size=-1.0)

    def test_size_too_large(self):
        with pytest.raises(ValidationError):
            CreatePrimitiveInput(primitive_type="cube", size=1001.0)

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            CreatePrimitiveInput(primitive_type="cube", color="red")  # type: ignore[call-arg]

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            CreatePrimitiveInput(primitive_type="cube", name="x" * 64)

    def test_name_stripped(self):
        p = CreatePrimitiveInput(primitive_type="cube", name="  Cube  ")
        assert p.name == "Cube"


# ---------------------------------------------------------------------------
# TransformObjectInput
# ---------------------------------------------------------------------------


class TestTransformObjectInput:
    def test_valid_location_only(self):
        p = TransformObjectInput(name="Cube", location=(1, 2, 3))
        assert p.location == (1, 2, 3)
        assert p.rotation_euler is None
        assert p.scale is None

    def test_valid_all_transforms(self):
        p = TransformObjectInput(
            name="Cube",
            location=(1, 2, 3),
            rotation_euler=(0, 0, 1.5708),
            scale=(2, 2, 2),
        )
        assert p.scale == (2, 2, 2)

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            TransformObjectInput(location=(0, 0, 0))  # type: ignore[call-arg]

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            TransformObjectInput(name="x" * 64, location=(0, 0, 0))


# ---------------------------------------------------------------------------
# DeleteObjectInput
# ---------------------------------------------------------------------------


class TestDeleteObjectInput:
    def test_valid(self):
        p = DeleteObjectInput(name="Cube")
        assert p.name == "Cube"

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            DeleteObjectInput(name="")

    def test_whitespace_stripped(self):
        p = DeleteObjectInput(name="  Cube  ")
        assert p.name == "Cube"


# ---------------------------------------------------------------------------
# GetSceneInfoInput / ListObjectsInput
# ---------------------------------------------------------------------------


class TestResponseFormat:
    def test_default_markdown(self):
        p = GetSceneInfoInput()
        assert p.response_format == ResponseFormat.MARKDOWN

    def test_explicit_json(self):
        p = GetSceneInfoInput(response_format="json")
        assert p.response_format == ResponseFormat.JSON

    def test_list_objects_filter(self):
        p = ListObjectsInput(object_type="MESH")
        assert p.object_type == "MESH"
        assert p.response_format == ResponseFormat.MARKDOWN

    def test_list_objects_no_filter(self):
        p = ListObjectsInput()
        assert p.object_type is None


# ---------------------------------------------------------------------------
# GetObjectInfoInput
# ---------------------------------------------------------------------------


class TestGetObjectInfoInput:
    def test_valid(self):
        p = GetObjectInfoInput(name="Cube")
        assert p.name == "Cube"

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            GetObjectInfoInput(name="")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            GetObjectInfoInput(name="x" * 64)

    def test_default_format_markdown(self):
        p = GetObjectInfoInput(name="Cube")
        assert p.response_format == ResponseFormat.MARKDOWN


# ---------------------------------------------------------------------------
# ViewportScreenshotInput
# ---------------------------------------------------------------------------


class TestViewportScreenshotInput:
    def test_default(self):
        p = ViewportScreenshotInput()
        assert p.max_size == 800

    def test_custom_size(self):
        p = ViewportScreenshotInput(max_size=1920)
        assert p.max_size == 1920

    def test_size_too_small(self):
        with pytest.raises(ValidationError):
            ViewportScreenshotInput(max_size=10)

    def test_size_too_large(self):
        with pytest.raises(ValidationError):
            ViewportScreenshotInput(max_size=9999)


# ---------------------------------------------------------------------------
# SetMaterialInput
# ---------------------------------------------------------------------------


class TestSetMaterialInput:
    def test_defaults(self):
        p = SetMaterialInput(object_name="Cube")
        assert p.color == (0.8, 0.8, 0.8, 1.0)
        assert p.metallic == 0.0
        assert p.roughness == 0.5
        assert p.emission_color is None
        assert p.emission_strength == 0.0

    def test_full(self):
        p = SetMaterialInput(
            object_name="Sphere",
            color=(0.2, 0.4, 0.8, 1.0),
            metallic=0.9,
            roughness=0.1,
            material_name="Metal",
            emission_color=(1.0, 0.5, 0.0),
            emission_strength=10.0,
        )
        assert p.metallic == 0.9
        assert p.material_name == "Metal"

    def test_metallic_out_of_range(self):
        with pytest.raises(ValidationError):
            SetMaterialInput(object_name="Cube", metallic=1.5)

    def test_roughness_out_of_range(self):
        with pytest.raises(ValidationError):
            SetMaterialInput(object_name="Cube", roughness=-0.1)

    def test_empty_object_name(self):
        with pytest.raises(ValidationError):
            SetMaterialInput(object_name="")


# ---------------------------------------------------------------------------
# AddLightInput
# ---------------------------------------------------------------------------


class TestAddLightInput:
    def test_point_defaults(self):
        p = AddLightInput(light_type="POINT")
        assert p.light_type == LightType.POINT
        assert p.energy == 1000.0
        assert p.color == (1.0, 1.0, 1.0)
        assert p.location == (0.0, 0.0, 3.0)

    def test_all_light_types(self):
        for lt in LightType:
            p = AddLightInput(light_type=lt.value)
            assert p.light_type == lt

    def test_invalid_light_type(self):
        with pytest.raises(ValidationError):
            AddLightInput(light_type="NEON")

    def test_energy_must_be_positive(self):
        with pytest.raises(ValidationError):
            AddLightInput(light_type="POINT", energy=0.0)

    def test_spot_size_bounds(self):
        with pytest.raises(ValidationError):
            AddLightInput(light_type="SPOT", spot_size=0.0)
        with pytest.raises(ValidationError):
            AddLightInput(light_type="SPOT", spot_size=181.0)


# ---------------------------------------------------------------------------
# SetCameraInput
# ---------------------------------------------------------------------------


class TestSetCameraInput:
    def test_defaults(self):
        p = SetCameraInput()
        assert p.name is None
        assert p.location is None
        assert p.target is None
        assert p.lens is None
        assert p.set_active is True

    def test_full(self):
        p = SetCameraInput(
            name="Camera",
            location=(5.0, -5.0, 3.0),
            target=(0.0, 0.0, 0.0),
            lens=50.0,
            set_active=True,
        )
        assert p.lens == 50.0
        assert p.target == (0.0, 0.0, 0.0)

    def test_lens_too_small(self):
        with pytest.raises(ValidationError):
            SetCameraInput(lens=0.5)

    def test_lens_too_large(self):
        with pytest.raises(ValidationError):
            SetCameraInput(lens=6000.0)


# ---------------------------------------------------------------------------
# ExecutePythonInput
# ---------------------------------------------------------------------------


class TestExecutePythonInput:
    def test_valid(self):
        p = ExecutePythonInput(code="result = 42")
        assert p.code == "result = 42"

    def test_empty_code(self):
        with pytest.raises(ValidationError):
            ExecutePythonInput(code="")

    def test_code_too_long(self):
        with pytest.raises(ValidationError):
            ExecutePythonInput(code="x" * 20_001)


# ---------------------------------------------------------------------------
# RenderImageInput
# ---------------------------------------------------------------------------


class TestRenderImageInput:
    def test_defaults(self):
        p = RenderImageInput()
        assert p.frame is None
        assert p.output_path is None
        assert p.engine is None
        assert p.samples is None
        assert p.max_preview_size == 512
        assert p.timeout_seconds == 300.0

    def test_valid_full(self):
        p = RenderImageInput(
            frame=10,
            engine="CYCLES",
            samples=128,
            max_preview_size=1024,
            timeout_seconds=600.0,
        )
        assert p.frame == 10
        assert p.engine == RenderEngine.CYCLES
        assert p.samples == 128
        assert p.max_preview_size == 1024
        assert p.timeout_seconds == 600.0

    def test_eevee_engine(self):
        p = RenderImageInput(engine="BLENDER_EEVEE")
        assert p.engine == RenderEngine.EEVEE

    def test_eevee_next_engine(self):
        p = RenderImageInput(engine="BLENDER_EEVEE_NEXT")
        assert p.engine == RenderEngine.EEVEE_NEXT

    def test_invalid_engine(self):
        with pytest.raises(ValidationError):
            RenderImageInput(engine="INVALID_ENGINE")

    def test_frame_zero_valid(self):
        p = RenderImageInput(frame=0)
        assert p.frame == 0

    def test_frame_negative_invalid(self):
        with pytest.raises(ValidationError):
            RenderImageInput(frame=-1)

    def test_samples_minimum(self):
        p = RenderImageInput(samples=1)
        assert p.samples == 1

    def test_samples_zero_invalid(self):
        with pytest.raises(ValidationError):
            RenderImageInput(samples=0)

    def test_max_preview_too_small(self):
        with pytest.raises(ValidationError):
            RenderImageInput(max_preview_size=63)

    def test_max_preview_too_large(self):
        with pytest.raises(ValidationError):
            RenderImageInput(max_preview_size=2049)

    def test_timeout_too_short(self):
        with pytest.raises(ValidationError):
            RenderImageInput(timeout_seconds=9.9)

    def test_timeout_too_long(self):
        with pytest.raises(ValidationError):
            RenderImageInput(timeout_seconds=3601.0)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            RenderImageInput(unknown_field="x")
