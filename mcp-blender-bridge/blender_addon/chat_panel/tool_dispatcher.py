"""Route tool_use events to blender_bridge _impl functions."""

from __future__ import annotations

import sys
import pathlib

# Make blender_bridge importable when running inside blender_addon context
_src = pathlib.Path(__file__).parents[3] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from blender_bridge.tools.code import _execute_python_impl
from blender_bridge.tools.objects import (
    _add_light_impl,
    _create_primitive_impl,
    _delete_object_impl,
    _set_camera_impl,
    _set_material_impl,
    _transform_object_impl,
)
from blender_bridge.tools.modal import (
    _modal_bevel_impl,
    _modal_extrude_impl,
    _modal_knife_cut_impl,
    _modal_loop_cut_impl,
    _modal_sculpt_impl,
)
from blender_bridge.tools.render import _render_image_impl
from blender_bridge.tools.scene import (
    _get_object_info_impl,
    _get_scene_info_impl,
    _get_viewport_screenshot_impl,
    _list_objects_impl,
    _open_file_impl,
    _ping_impl,
    _save_file_impl,
)
from blender_bridge.schemas import (
    AddLightInput,
    CreatePrimitiveInput,
    DeleteObjectInput,
    ExecutePythonInput,
    GetObjectInfoInput,
    GetSceneInfoInput,
    ListObjectsInput,
    ModalBevelInput,
    ModalExtrudeInput,
    ModalKnifeCutInput,
    ModalLoopCutInput,
    ModalSculptInput,
    OpenFileInput,
    RenderImageInput,
    SaveFileInput,
    SetCameraInput,
    SetMaterialInput,
    TransformObjectInput,
    ViewportScreenshotInput,
)
from blender_bridge.utils import format_error

# (impl_fn, schema_cls)
_REGISTRY: dict = {
    "blender_ping": (_ping_impl, None),
    "blender_get_scene_info": (_get_scene_info_impl, GetSceneInfoInput),
    "blender_list_objects": (_list_objects_impl, ListObjectsInput),
    "blender_get_object_info": (_get_object_info_impl, GetObjectInfoInput),
    "blender_save_file": (_save_file_impl, SaveFileInput),
    "blender_open_file": (_open_file_impl, OpenFileInput),
    "blender_get_viewport_screenshot": (_get_viewport_screenshot_impl, ViewportScreenshotInput),
    "blender_create_primitive": (_create_primitive_impl, CreatePrimitiveInput),
    "blender_transform_object": (_transform_object_impl, TransformObjectInput),
    "blender_delete_object": (_delete_object_impl, DeleteObjectInput),
    "blender_set_material": (_set_material_impl, SetMaterialInput),
    "blender_add_light": (_add_light_impl, AddLightInput),
    "blender_set_camera": (_set_camera_impl, SetCameraInput),
    "blender_render_image": (_render_image_impl, RenderImageInput),
    "blender_execute_python": (_execute_python_impl, ExecutePythonInput),
    "blender_modal_extrude": (_modal_extrude_impl, ModalExtrudeInput),
    "blender_modal_loop_cut": (_modal_loop_cut_impl, ModalLoopCutInput),
    "blender_modal_knife_cut": (_modal_knife_cut_impl, ModalKnifeCutInput),
    "blender_modal_bevel": (_modal_bevel_impl, ModalBevelInput),
    "blender_modal_sculpt": (_modal_sculpt_impl, ModalSculptInput),
}


def _location_from_params(raw_args: dict) -> tuple[float, float, float] | None:
    loc = raw_args.get("location")
    if isinstance(loc, (list, tuple)) and len(loc) >= 3:
        return (float(loc[0]), float(loc[1]), float(loc[2]))
    return None


async def dispatch(tool_name: str, raw_args: dict, client: object) -> str:
    if tool_name not in _REGISTRY:
        return format_error(f"Unknown tool: {tool_name}")
    impl_fn, schema_cls = _REGISTRY[tool_name]

    # Ghost cursor — show target location while tool runs
    try:
        from . import ghost_cursor  # noqa: PLC0415
        ghost_cursor.set_target(_location_from_params(raw_args))
    except Exception:
        pass

    try:
        if schema_cls is None:
            result = await impl_fn(client)
        else:
            params = schema_cls(**raw_args)
            result = await impl_fn(params, client)
    except Exception as exc:
        return format_error(str(exc))
    finally:
        try:
            from . import ghost_cursor  # noqa: PLC0415, F811
            ghost_cursor.set_target(None)
        except Exception:
            pass

    # _impl functions may return str or list; normalise to str
    if isinstance(result, list):
        import json
        return json.dumps(result)
    return str(result)
