"""MCP-Blender-Bridge addon for Blender.

Install this addon inside Blender (Edit > Preferences > Add-ons > Install...)
and start the bridge server from the 3D Viewport's N-panel ("MCP" tab).

The addon listens on a TCP socket (default 127.0.0.1:9876) and executes
JSON commands sent by the MCP server.

NOTE: Single-file layout is intentional — Blender addon installation requires
a single .py file for drag-and-drop installs. Logic is organised into clearly
named functions rather than split across modules.
"""

bl_info = {
    "name": "MCP Blender Bridge",
    "author": "Aayush Dubey",
    "version": (0, 2, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > MCP",
    "description": "Bridge Blender to AI assistants via the Model Context Protocol",
    "category": "Development",
}

import base64
import contextlib
import json
import math
import os
import queue
import socket
import tempfile
import threading
import traceback
from typing import Any

import bpy

# ---------------------------------------------------------------------------
# Global server state
# ---------------------------------------------------------------------------
_server_socket: socket.socket | None = None
_server_thread: threading.Thread | None = None
_server_running = False
_command_queue: "queue.Queue[tuple[Any, ...]]" = queue.Queue()


# ---------------------------------------------------------------------------
# Scene / inspection command handlers
# ---------------------------------------------------------------------------


def cmd_ping(params: dict[str, Any]) -> dict[str, Any]:
    return {"pong": True, "blender_version": bpy.app.version_string, "bridge_version": "0.2.0"}


def cmd_get_scene_info(params: dict[str, Any]) -> dict[str, Any]:
    scene = bpy.context.scene
    return {
        "name": scene.name,
        "engine": scene.render.engine,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "object_count": len(bpy.data.objects),
        "active_object": (
            bpy.context.view_layer.objects.active.name
            if bpy.context.view_layer.objects.active
            else None
        ),
    }


def cmd_list_objects(params: dict[str, Any]) -> dict[str, Any]:
    object_type = params.get("object_type")
    objects = []
    for obj in bpy.data.objects:
        if object_type and obj.type != object_type:
            continue
        objects.append({"name": obj.name, "type": obj.type, "location": list(obj.location)})
    return {"objects": objects}


def cmd_get_object_info(params: dict[str, Any]) -> dict[str, Any]:
    name = params["name"]
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object '{name}' not found in scene.")

    info: dict[str, Any] = {
        "name": obj.name,
        "type": obj.type,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
        "dimensions": list(obj.dimensions),
        "visible": obj.visible_get(),
        "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
    }

    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        info["mesh"] = {
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "faces": len(mesh.polygons),
        }

    if obj.type == "LIGHT" and obj.data:
        light = obj.data
        info["light"] = {
            "type": light.type,
            "energy": light.energy,
            "color": list(light.color),
        }

    if obj.type == "CAMERA" and obj.data:
        cam = obj.data
        info["camera"] = {
            "lens": cam.lens,
            "sensor_width": cam.sensor_width,
            "clip_start": cam.clip_start,
            "clip_end": cam.clip_end,
        }

    return info


def cmd_get_viewport_screenshot(params: dict[str, Any]) -> dict[str, Any]:
    max_size = int(params.get("max_size", 800))
    scene = bpy.context.scene

    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)

    try:
        # Render current viewport via OpenGL; result lands in "Render Result" image
        bpy.ops.render.opengl(write_still=False)
        render_result = bpy.data.images.get("Render Result")
        if render_result is None:
            raise RuntimeError("OpenGL render produced no output — is a 3D viewport open?")

        # Resize if needed (operates on a copy to avoid modifying the render result)
        w, h = render_result.size
        if max(w, h) > max_size and max(w, h) > 0:
            scale = max_size / max(w, h)
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            # Save to temp, reload, scale, save again
            render_result.save_render(tmp_path)
            tmp_img = bpy.data.images.load(tmp_path)
            tmp_img.scale(new_w, new_h)
            tmp_img.save_render(tmp_path)
            out_w, out_h = tmp_img.size
            bpy.data.images.remove(tmp_img)
        else:
            render_result.save_render(tmp_path)
            out_w, out_h = w, h

        with open(tmp_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        return {"image_data": encoded, "format": "png", "width": out_w, "height": out_h}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Render command handler
# ---------------------------------------------------------------------------


def cmd_render_image(params: dict[str, Any]) -> dict[str, Any]:
    import time

    frame = params.get("frame")
    output_path = params.get("output_path")
    engine = params.get("engine")
    samples = params.get("samples")
    max_preview_size = int(params.get("max_preview_size", 512))

    scene = bpy.context.scene

    # Save state we will restore
    old_engine = scene.render.engine
    old_frame = scene.frame_current
    old_filepath = scene.render.filepath
    old_format = scene.render.image_settings.file_format
    old_cycles_samples = None
    if hasattr(scene, "cycles"):
        old_cycles_samples = scene.cycles.samples

    try:
        if engine:
            scene.render.engine = engine
        if frame is not None:
            scene.frame_current = int(frame)
        if samples is not None and hasattr(scene, "cycles"):
            scene.cycles.samples = int(samples)

        # Always render to RAM first so we can capture the result
        scene.render.image_settings.file_format = "PNG"

        t0 = time.monotonic()
        bpy.ops.render.render(write_still=False)
        render_time = time.monotonic() - t0

        render_result = bpy.data.images.get("Render Result")
        if render_result is None:
            raise RuntimeError("Render completed but 'Render Result' image not found.")

        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        pct = scene.render.resolution_percentage / 100.0
        actual_w = int(res_x * pct)
        actual_h = int(res_y * pct)

        # Save full-res to output_path if requested
        saved_path: str | None = None
        if output_path:
            render_result.save_render(output_path)
            saved_path = output_path

        # Build preview (resize from render result)
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            render_result.save_render(tmp_path)

            if max(actual_w, actual_h) > max_preview_size and max(actual_w, actual_h) > 0:
                scale = max_preview_size / max(actual_w, actual_h)
                new_w = max(1, int(actual_w * scale))
                new_h = max(1, int(actual_h * scale))
                tmp_img = bpy.data.images.load(tmp_path)
                tmp_img.scale(new_w, new_h)
                tmp_img.save_render(tmp_path)
                bpy.data.images.remove(tmp_img)

            with open(tmp_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

        return {
            "frame": scene.frame_current,
            "engine": scene.render.engine,
            "render_time_seconds": round(render_time, 2),
            "resolution": [actual_w, actual_h],
            "output_path": saved_path,
            "image_data": encoded,
        }

    finally:
        scene.render.engine = old_engine
        scene.frame_current = old_frame
        scene.render.filepath = old_filepath
        scene.render.image_settings.file_format = old_format
        if old_cycles_samples is not None and hasattr(scene, "cycles"):
            scene.cycles.samples = old_cycles_samples


# ---------------------------------------------------------------------------
# Object manipulation command handlers
# ---------------------------------------------------------------------------


def cmd_create_primitive(params: dict[str, Any]) -> dict[str, Any]:
    primitive_type = params["primitive_type"]
    location = tuple(params.get("location", (0, 0, 0)))
    size = float(params.get("size", 2.0))
    name = params.get("name")

    op_map = {
        "cube": lambda: bpy.ops.mesh.primitive_cube_add(size=size, location=location),
        "sphere": lambda: bpy.ops.mesh.primitive_uv_sphere_add(radius=size / 2, location=location),
        "cylinder": lambda: bpy.ops.mesh.primitive_cylinder_add(radius=size / 2, location=location),
        "cone": lambda: bpy.ops.mesh.primitive_cone_add(radius1=size / 2, location=location),
        "plane": lambda: bpy.ops.mesh.primitive_plane_add(size=size, location=location),
        "torus": lambda: bpy.ops.mesh.primitive_torus_add(major_radius=size / 2, location=location),
        "monkey": lambda: bpy.ops.mesh.primitive_monkey_add(size=size, location=location),
    }

    if primitive_type not in op_map:
        raise ValueError(f"Unsupported primitive type: {primitive_type!r}")

    op_map[primitive_type]()
    obj = bpy.context.view_layer.objects.active

    if name:
        obj.name = name

    return {"name": obj.name, "type": obj.type, "location": list(obj.location), "primitive_type": primitive_type}


def cmd_transform_object(params: dict[str, Any]) -> dict[str, Any]:
    name = params["name"]
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object '{name}' not found in scene.")

    if params.get("location") is not None:
        obj.location = tuple(params["location"])
    if params.get("rotation_euler") is not None:
        obj.rotation_euler = tuple(params["rotation_euler"])
    if params.get("scale") is not None:
        obj.scale = tuple(params["scale"])

    return {
        "name": obj.name,
        "location": list(obj.location),
        "rotation_euler": list(obj.rotation_euler),
        "scale": list(obj.scale),
    }


def cmd_delete_object(params: dict[str, Any]) -> dict[str, Any]:
    name = params["name"]
    obj = bpy.data.objects.get(name)
    if obj is None:
        return {"deleted": False, "reason": f"Object '{name}' did not exist."}
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": True, "name": name}


def cmd_set_material(params: dict[str, Any]) -> dict[str, Any]:
    object_name = params["object_name"]
    color = params.get("color", [0.8, 0.8, 0.8, 1.0])
    metallic = float(params.get("metallic", 0.0))
    roughness = float(params.get("roughness", 0.5))
    material_name = params.get("material_name")
    emission_color = params.get("emission_color")
    emission_strength = float(params.get("emission_strength", 0.0))

    obj = bpy.data.objects.get(object_name)
    if obj is None:
        raise ValueError(f"Object '{object_name}' not found in scene.")

    mat_name = material_name or f"MCP_{object_name}"
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes

    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        nodes.clear()
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        output = nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    bsdf.inputs["Base Color"].default_value = tuple(color[:4] if len(color) >= 4 else [*color, 1.0])
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness

    if emission_color is not None:
        ec = tuple(emission_color[:3])
        if "Emission Color" in bsdf.inputs:  # Blender 4.x
            bsdf.inputs["Emission Color"].default_value = (*ec, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emission_strength
        elif "Emission" in bsdf.inputs:  # Blender 3.x
            bsdf.inputs["Emission"].default_value = (*ec, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emission_strength

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return {
        "object": object_name,
        "material": mat.name,
        "color": list(color),
        "metallic": metallic,
        "roughness": roughness,
    }


def cmd_add_light(params: dict[str, Any]) -> dict[str, Any]:
    light_type = params["light_type"]
    name = params.get("name") or f"MCP_{light_type.capitalize()}"
    location = tuple(params.get("location", [0, 0, 3]))
    energy = float(params.get("energy", 1000.0))
    color = tuple(params.get("color", [1.0, 1.0, 1.0])[:3])

    light_data = bpy.data.lights.new(name=name, type=light_type)
    light_data.energy = energy
    light_data.color = color

    if light_type == "POINT":
        light_data.shadow_soft_size = float(params.get("radius", 0.1))
    elif light_type == "SPOT":
        light_data.shadow_soft_size = float(params.get("radius", 0.1))
        light_data.spot_size = math.radians(float(params.get("spot_size", 45.0)))
        light_data.spot_blend = float(params.get("spot_blend", 0.15))
    elif light_type == "AREA":
        light_data.size = float(params.get("size", 1.0))

    light_obj = bpy.data.objects.new(name=name, object_data=light_data)
    light_obj.location = location
    bpy.context.collection.objects.link(light_obj)
    bpy.context.view_layer.objects.active = light_obj

    return {
        "name": light_obj.name,
        "type": light_type,
        "location": list(light_obj.location),
        "energy": energy,
        "color": list(color),
    }


def cmd_set_camera(params: dict[str, Any]) -> dict[str, Any]:
    import mathutils

    name = params.get("name")
    location = params.get("location")
    target = params.get("target")
    lens = params.get("lens")
    set_active = bool(params.get("set_active", True))

    # Resolve camera object
    if name:
        cam_obj = bpy.data.objects.get(name)
        if cam_obj is None or cam_obj.type != "CAMERA":
            raise ValueError(f"Camera '{name}' not found.")
    else:
        cam_obj = bpy.context.scene.camera
        if cam_obj is None:
            cam_data = bpy.data.cameras.new("MCP_Camera")
            cam_obj = bpy.data.objects.new("MCP_Camera", cam_data)
            bpy.context.collection.objects.link(cam_obj)

    if location is not None:
        cam_obj.location = tuple(location)

    if lens is not None and cam_obj.data:
        cam_obj.data.lens = float(lens)

    if target is not None:
        direction = mathutils.Vector(target) - mathutils.Vector(cam_obj.location)
        cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    if set_active:
        bpy.context.scene.camera = cam_obj

    return {
        "name": cam_obj.name,
        "location": list(cam_obj.location),
        "rotation_euler": list(cam_obj.rotation_euler),
        "lens": cam_obj.data.lens if cam_obj.data else None,
        "is_active_camera": bpy.context.scene.camera == cam_obj,
    }


# ---------------------------------------------------------------------------
# Code execution
# ---------------------------------------------------------------------------


def cmd_execute_python(params: dict[str, Any]) -> dict[str, Any]:
    code = params["code"]
    local_ns: dict[str, Any] = {"bpy": bpy}
    exec(code, local_ns)  # noqa: S102 — intentional escape hatch
    result = local_ns.get("result")
    try:
        json.dumps(result)
        return {"result": result}
    except TypeError:
        return {"result": repr(result)}


# ---------------------------------------------------------------------------
# Command dispatch table
# ---------------------------------------------------------------------------

COMMAND_HANDLERS: dict[str, Any] = {
    "ping": cmd_ping,
    "get_scene_info": cmd_get_scene_info,
    "list_objects": cmd_list_objects,
    "get_object_info": cmd_get_object_info,
    "get_viewport_screenshot": cmd_get_viewport_screenshot,
    "create_primitive": cmd_create_primitive,
    "transform_object": cmd_transform_object,
    "delete_object": cmd_delete_object,
    "set_material": cmd_set_material,
    "add_light": cmd_add_light,
    "set_camera": cmd_set_camera,
    "execute_python": cmd_execute_python,
}


# ---------------------------------------------------------------------------
# Main-thread execution via queue + timer
# ---------------------------------------------------------------------------


def _drain_command_queue() -> float:
    """Timer callback — drains queued commands on Blender's main thread."""
    while not _command_queue.empty():
        try:
            handler, params, response_holder, done_event = _command_queue.get_nowait()
        except queue.Empty:
            break

        try:
            result = handler(params)
            response_holder["response"] = {"status": "success", "result": result}
        except Exception as e:  # noqa: BLE001
            response_holder["response"] = {
                "status": "error",
                "message": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
            }
        finally:
            done_event.set()

    return 0.05  # re-fire every 50 ms while server is running


def _handle_client(conn: socket.socket) -> None:
    """Handle one client connection: read one command, send one response."""
    try:
        with conn:
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk

            line, _, _ = buf.partition(b"\n")
            request = json.loads(line.decode("utf-8"))
            command = request.get("command")
            params = request.get("params") or {}

            handler = COMMAND_HANDLERS.get(command)
            if handler is None:
                response: dict[str, Any] = {"status": "error", "message": f"Unknown command: {command!r}"}
            else:
                response_holder: dict[str, Any] = {}
                done_event = threading.Event()
                _command_queue.put((handler, params, response_holder, done_event))
                done_event.wait(timeout=60.0)
                response = response_holder.get(
                    "response",
                    {"status": "error", "message": "Command timed out on Blender main thread."},
                )

            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
    except Exception as e:  # noqa: BLE001
        try:
            err = {"status": "error", "message": f"Server error: {type(e).__name__}: {e}"}
            conn.sendall((json.dumps(err) + "\n").encode("utf-8"))
        except Exception:  # noqa: BLE001
            pass


def _server_loop(host: str, port: int) -> None:
    """Accept-loop running in a background daemon thread."""
    global _server_socket, _server_running
    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind((host, port))
    _server_socket.listen(5)
    _server_socket.settimeout(1.0)
    print(f"[MCP Bridge] Listening on {host}:{port}")

    while _server_running:
        try:
            conn, _addr = _server_socket.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=_handle_client, args=(conn,), daemon=True).start()

    if _server_socket:
        _server_socket.close()
    _server_socket = None
    print("[MCP Bridge] Server stopped.")


def start_server(host: str = "127.0.0.1", port: int = 9876) -> None:
    global _server_thread, _server_running
    if _server_running:
        return
    _server_running = True
    _server_thread = threading.Thread(target=_server_loop, args=(host, port), daemon=True)
    _server_thread.start()
    bpy.app.timers.register(_drain_command_queue, persistent=True)


def stop_server() -> None:
    global _server_running, _server_socket
    _server_running = False
    if _server_socket:
        try:
            _server_socket.close()
        except Exception:  # noqa: BLE001
            pass
    if bpy.app.timers.is_registered(_drain_command_queue):
        bpy.app.timers.unregister(_drain_command_queue)


# ---------------------------------------------------------------------------
# Blender UI — operators + N-panel
# ---------------------------------------------------------------------------


class MCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "mcp.start_server"
    bl_label = "Start MCP Bridge"
    bl_description = "Start the MCP bridge TCP server"

    def execute(self, context: bpy.types.Context) -> set[str]:
        prefs = context.scene.mcp_bridge_settings
        start_server(prefs.host, prefs.port)
        self.report({"INFO"}, f"MCP Bridge started on {prefs.host}:{prefs.port}")
        return {"FINISHED"}


class MCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "mcp.stop_server"
    bl_label = "Stop MCP Bridge"
    bl_description = "Stop the MCP bridge TCP server"

    def execute(self, context: bpy.types.Context) -> set[str]:
        stop_server()
        self.report({"INFO"}, "MCP Bridge stopped")
        return {"FINISHED"}


class MCP_PT_Panel(bpy.types.Panel):
    bl_label = "MCP Blender Bridge v0.2.0"
    bl_idname = "MCP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        prefs = context.scene.mcp_bridge_settings

        col = layout.column(align=True)
        col.prop(prefs, "host")
        col.prop(prefs, "port")

        row = layout.row(align=True)
        if _server_running:
            row.label(text="Status: Running", icon="CHECKMARK")
            layout.operator("mcp.stop_server", icon="PAUSE")
        else:
            row.label(text="Status: Stopped", icon="X")
            layout.operator("mcp.start_server", icon="PLAY")

        layout.separator()
        layout.label(text=f"Tools: {len(COMMAND_HANDLERS)}", icon="INFO")


class MCPBridgeSettings(bpy.types.PropertyGroup):
    host: bpy.props.StringProperty(name="Host", default="127.0.0.1")  # type: ignore[assignment]
    port: bpy.props.IntProperty(name="Port", default=9876, min=1024, max=65535)  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_classes = (MCPBridgeSettings, MCP_OT_StartServer, MCP_OT_StopServer, MCP_PT_Panel)


def register() -> None:
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mcp_bridge_settings = bpy.props.PointerProperty(type=MCPBridgeSettings)


def unregister() -> None:
    stop_server()
    del bpy.types.Scene.mcp_bridge_settings
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
