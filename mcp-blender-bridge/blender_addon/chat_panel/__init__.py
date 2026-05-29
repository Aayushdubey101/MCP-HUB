"""MCP-HUB chat panel — Blender addon sub-package.

register() / unregister() are called from the parent addon's bl_info entry point.
Bpy is imported lazily so this package is importable in test environments.
"""

from __future__ import annotations


def register() -> None:
    import bpy  # noqa: PLC0415
    from . import operators, panel, preferences, properties  # noqa: PLC0415
    from . import realtime_monitor  # noqa: PLC0415
    from .threading_bridge import _main_thread_tick  # noqa: PLC0415

    properties.register()
    preferences.register()
    panel.register()
    operators.register()
    bpy.app.timers.register(_main_thread_tick, persistent=True)
    realtime_monitor.register()


def unregister() -> None:
    import bpy  # noqa: PLC0415
    from . import operators, panel, preferences, properties  # noqa: PLC0415
    from . import realtime_monitor  # noqa: PLC0415
    from .threading_bridge import _main_thread_tick  # noqa: PLC0415

    realtime_monitor.unregister()
    if bpy.app.timers.is_registered(_main_thread_tick):
        bpy.app.timers.unregister(_main_thread_tick)
    operators.unregister()
    panel.unregister()
    preferences.unregister()
    properties.unregister()
