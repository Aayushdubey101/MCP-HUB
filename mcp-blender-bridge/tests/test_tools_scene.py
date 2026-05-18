"""Tests for scene inspection tools (scene.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from mcp.server.fastmcp import FastMCP

from blender_bridge.client import BRIDGE_PROTOCOL_VERSION, BlenderClient, BlenderConnectionError
from blender_bridge.schemas import (
    GetObjectInfoInput,
    GetSceneInfoInput,
    ListObjectsInput,
)
from blender_bridge.tools import scene as scene_tools


def _make_mcp():
    mcp = FastMCP("test-scene")
    client = AsyncMock(spec=BlenderClient)
    scene_tools.register(mcp, client)
    return mcp, client


def _get_tool(mcp: FastMCP, name: str):
    return mcp._tool_manager._tools[name].fn


def _success(result: dict) -> dict:
    return {"status": "success", "result": result}


# ---------------------------------------------------------------------------
# blender_ping
# ---------------------------------------------------------------------------


class TestBlenderPing:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_ping")

    async def test_success_returns_reachable(self):
        self.client.send_command.return_value = _success(
            {
                "pong": True,
                "blender_version": "4.1.0",
                "bridge_version": "0.2.0",
                "protocol_version": BRIDGE_PROTOCOL_VERSION,
            }
        )
        result = await self.fn()
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["result"]["reachable"] is True

    async def test_protocol_version_mismatch_returns_error(self):
        self.client.send_command.return_value = _success(
            {
                "pong": True,
                "protocol_version": "9.9",
            }
        )
        result = await self.fn()
        data = json.loads(result)
        assert data["status"] == "error"
        assert "mismatch" in data["message"].lower()

    async def test_legacy_addon_no_protocol_version(self):
        self.client.send_command.return_value = _success({"pong": True})
        result = await self.fn()
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["result"]["protocol_version"] == "legacy"

    async def test_connection_error_returns_error(self):
        self.client.send_command.side_effect = BlenderConnectionError("not running")
        result = await self.fn()
        assert json.loads(result)["status"] == "error"


# ---------------------------------------------------------------------------
# blender_get_scene_info
# ---------------------------------------------------------------------------


class TestGetSceneInfo:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_get_scene_info")

    async def test_json_format_returns_success_json(self):
        self.client.send_command.return_value = _success(
            {
                "name": "Scene",
                "engine": "CYCLES",
                "frame_start": 1,
                "frame_end": 250,
                "frame_current": 1,
                "object_count": 3,
                "active_object": "Cube",
            }
        )
        result = await self.fn(GetSceneInfoInput(response_format="json"))
        data = json.loads(result)
        assert data["status"] == "success"

    async def test_markdown_format_returns_string(self):
        self.client.send_command.return_value = _success(
            {
                "name": "MyScene",
                "engine": "EEVEE",
                "frame_start": 1,
                "frame_end": 100,
                "frame_current": 50,
                "object_count": 5,
                "active_object": "Sphere",
            }
        )
        result = await self.fn(GetSceneInfoInput(response_format="markdown"))
        assert "MyScene" in result
        assert "EEVEE" in result

    async def test_connection_error(self):
        self.client.send_command.side_effect = BlenderConnectionError("err")
        result = await self.fn(GetSceneInfoInput())
        assert json.loads(result)["status"] == "error"


# ---------------------------------------------------------------------------
# blender_list_objects
# ---------------------------------------------------------------------------


class TestListObjects:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_list_objects")

    async def test_json_format_with_objects(self):
        objects = [
            {"name": "Cube", "type": "MESH", "location": [0, 0, 0]},
            {"name": "Camera", "type": "CAMERA", "location": [5, -5, 3]},
        ]
        self.client.send_command.return_value = _success({"objects": objects})
        result = await self.fn(ListObjectsInput(response_format="json"))
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["result"]["count"] == 2

    async def test_markdown_format_with_objects(self):
        objects = [{"name": "Cube", "type": "MESH", "location": [0, 0, 0]}]
        self.client.send_command.return_value = _success({"objects": objects})
        result = await self.fn(ListObjectsInput(response_format="markdown"))
        assert "Cube" in result
        assert "MESH" in result

    async def test_empty_scene_returns_no_objects_message(self):
        self.client.send_command.return_value = _success({"objects": []})
        result = await self.fn(ListObjectsInput())
        assert "No objects" in result

    async def test_type_filter_sent_to_client(self):
        self.client.send_command.return_value = _success({"objects": []})
        await self.fn(ListObjectsInput(object_type="MESH"))
        sent = self.client.send_command.call_args[0][1]
        assert sent["object_type"] == "MESH"

    async def test_connection_error(self):
        self.client.send_command.side_effect = BlenderConnectionError("err")
        result = await self.fn(ListObjectsInput())
        assert json.loads(result)["status"] == "error"


# ---------------------------------------------------------------------------
# blender_get_object_info
# ---------------------------------------------------------------------------


class TestGetObjectInfo:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_get_object_info")

    async def test_json_format(self):
        self.client.send_command.return_value = _success(
            {
                "name": "Cube",
                "type": "MESH",
                "location": [0, 0, 0],
                "rotation_euler": [0, 0, 0],
                "scale": [1, 1, 1],
                "dimensions": [2, 2, 2],
                "visible": True,
                "materials": ["Material"],
                "mesh": {"vertices": 8, "edges": 12, "faces": 6},
            }
        )
        result = await self.fn(GetObjectInfoInput(name="Cube", response_format="json"))
        data = json.loads(result)
        assert data["status"] == "success"

    async def test_markdown_format_with_mesh(self):
        self.client.send_command.return_value = _success(
            {
                "name": "Cube",
                "type": "MESH",
                "location": [1.0, 2.0, 3.0],
                "rotation_euler": [0, 0, 0],
                "scale": [1, 1, 1],
                "dimensions": [2, 2, 2],
                "visible": True,
                "materials": [],
                "mesh": {"vertices": 8, "edges": 12, "faces": 6},
            }
        )
        result = await self.fn(GetObjectInfoInput(name="Cube"))
        assert "Cube" in result
        assert "Vertices" in result

    async def test_markdown_format_with_light(self):
        self.client.send_command.return_value = _success(
            {
                "name": "Sun",
                "type": "LIGHT",
                "location": [0, 0, 5],
                "rotation_euler": [0, 0, 0],
                "scale": [1, 1, 1],
                "dimensions": [0, 0, 0],
                "visible": True,
                "materials": [],
                "light": {"type": "SUN", "energy": 1000, "color": [1, 1, 1]},
            }
        )
        result = await self.fn(GetObjectInfoInput(name="Sun"))
        assert "Light" in result
        assert "SUN" in result

    async def test_markdown_format_with_camera(self):
        self.client.send_command.return_value = _success(
            {
                "name": "Camera",
                "type": "CAMERA",
                "location": [5, -5, 3],
                "rotation_euler": [0, 0, 0],
                "scale": [1, 1, 1],
                "dimensions": [0, 0, 0],
                "visible": True,
                "materials": [],
                "camera": {
                    "lens": 50.0,
                    "sensor_width": 36.0,
                    "clip_start": 0.1,
                    "clip_end": 100.0,
                },
            }
        )
        result = await self.fn(GetObjectInfoInput(name="Camera"))
        assert "50.0" in result
        assert "Camera" in result

    async def test_sends_correct_name(self):
        self.client.send_command.return_value = _success(
            {
                "name": "MySphere",
                "type": "MESH",
                "location": [0, 0, 0],
                "rotation_euler": [0, 0, 0],
                "scale": [1, 1, 1],
                "dimensions": [2, 2, 2],
                "visible": True,
                "materials": [],
            }
        )
        await self.fn(GetObjectInfoInput(name="MySphere"))
        sent = self.client.send_command.call_args[0][1]
        assert sent["name"] == "MySphere"

    async def test_connection_error(self):
        self.client.send_command.side_effect = BlenderConnectionError("err")
        result = await self.fn(GetObjectInfoInput(name="Ghost"))
        assert json.loads(result)["status"] == "error"
