"""Depsgraph update handler — buffers scene diffs for injection into the next prompt."""

from __future__ import annotations

from collections import deque

try:
    import bpy
    from bpy.app.handlers import persistent as _persistent
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    def _persistent(fn):  # type: ignore[misc]
        return fn


_diff_buffer: deque = deque(maxlen=200)


def _on_depsgraph_update(scene: object, depsgraph: object) -> None:  # noqa: ARG001
    for update in depsgraph.updates:  # type: ignore[attr-defined]
        obj = update.id
        if obj is None:
            continue
        name: str = getattr(obj, "name", str(obj))

        if update.is_updated_transform:
            matrix = None
            if hasattr(obj, "matrix_world"):
                matrix = [list(row) for row in obj.matrix_world]
            _diff_buffer.append({"op": "transform", "name": name, "matrix": matrix})

        if update.is_updated_geometry:
            _diff_buffer.append({"op": "geometry", "name": name})

        # Material change detection (object has new material slot)
        if getattr(update, "is_updated_shading", False):
            _diff_buffer.append({"op": "shading", "name": name})

        # Light type / energy change
        if hasattr(obj, "type") and getattr(obj, "type", "") == "LIGHT":
            if update.is_updated_geometry or getattr(update, "is_updated_shading", False):
                light = getattr(obj, "data", None)
                _diff_buffer.append({
                    "op": "light",
                    "name": name,
                    "light_type": getattr(light, "type", None),
                    "energy": getattr(light, "energy", None),
                })


# Apply @persistent decorator only when bpy is available
_on_depsgraph_update = _persistent(_on_depsgraph_update)


def flush_diffs() -> list[dict]:
    """Return buffered diffs and clear the buffer. Thread-safe for reads."""
    diffs = list(_diff_buffer)
    _diff_buffer.clear()
    return diffs


def format_diffs(diffs: list[dict]) -> str:
    lines = []
    for d in diffs:
        op = d.get("op", "")
        name = d.get("name", "?")
        if op == "transform":
            lines.append(f"User moved/rotated/scaled '{name}'")
        elif op == "geometry":
            lines.append(f"User modified geometry of '{name}'")
        elif op == "shading":
            lines.append(f"User changed material/shading on '{name}'")
        elif op == "light":
            ltype = d.get("light_type", "")
            energy = d.get("energy", "")
            lines.append(f"User updated light '{name}' (type={ltype}, energy={energy})")
        else:
            lines.append(f"Scene change: {d}")
    return "\n".join(lines)


def register() -> None:
    if not _HAS_BPY:
        return
    if _on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)


def unregister() -> None:
    if not _HAS_BPY:
        return
    if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
