"""Tests for object manipulation tools (objects.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from mcp.server.fastmcp import FastMCP

from blender_bridge.client import BlenderClient, BlenderConnectionError
from blender_bridge.schemas import (
    AddLightInput,
    CreatePrimitiveInput,
    DeleteObjectInput,
    LightType,
    SetCameraInput,
    SetMaterialInput,
    TransformObjectInput,
)
from blender_bridge.tools import objects as object_tools


def _make_mcp(read_only: bool = False):
    mcp = FastMCP("test-objects")
    client = AsyncMock(spec=BlenderClient)
    object_tools.register(mcp, client, read_only=read_only)
    return mcp, client


def _get_tool(mcp: FastMCP, name: str):
    return mcp._tool_manager._tools[name].fn


def _success(result: dict) -> dict:
    return {"status": "success", "result": result}


# ---------------------------------------------------------------------------
# blender_create_primitive
# ---------------------------------------------------------------------------


class TestCreatePrimitive:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_create_primitive")

    async def test_calls_client_with_correct_params(self):
        self.client.send_command.return_value = _success({"name": "Cube", "type": "MESH"})
        params = CreatePrimitiveInput(
            primitive_type="cube", name="MyCube", location=(1, 2, 3), size=4.0
        )
        result = await self.fn(params)
        self.client.send_command.assert_called_once_with(
            "create_primitive",
            {"primitive_type": "cube", "name": "MyCube", "location": [1, 2, 3], "size": 4.0},
        )
        data = json.loads(result)
        assert data["status"] == "success"

    async def test_success_contains_object_name(self):
        self.client.send_command.return_value = _success({"name": "Sphere.001", "type": "MESH"})
        result = await self.fn(CreatePrimitiveInput(primitive_type="sphere"))
        data = json.loads(result)
        assert "Sphere.001" in data.get("message", "")

    async def test_connection_error_returns_error_json(self):
        self.client.send_command.side_effect = BlenderConnectionError("not running")
        result = await self.fn(CreatePrimitiveInput(primitive_type="cube"))
        data = json.loads(result)
        assert data["status"] == "error"

    async def test_read_only_blocks_call(self):
        mcp_ro, client_ro = _make_mcp(read_only=True)
        fn = _get_tool(mcp_ro, "blender_create_primitive")
        result = await fn(CreatePrimitiveInput(primitive_type="cube"))
        client_ro.send_command.assert_not_called()
        data = json.loads(result)
        assert data["status"] == "error"
        assert "read-only" in data["message"].lower()


# ---------------------------------------------------------------------------
# blender_transform_object
# ---------------------------------------------------------------------------


class TestTransformObject:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_transform_object")

    async def test_calls_client_with_location(self):
        self.client.send_command.return_value = _success({"name": "Cube", "location": [1, 0, 0]})
        params = TransformObjectInput(name="Cube", location=(1.0, 0.0, 0.0))
        result = await self.fn(params)
        self.client.send_command.assert_called_once()
        data = json.loads(result)
        assert data["status"] == "success"

    async def test_returns_error_when_no_transforms_given(self):
        params = TransformObjectInput(name="Cube")
        result = await self.fn(params)
        self.client.send_command.assert_not_called()
        data = json.loads(result)
        assert data["status"] == "error"
        assert "location" in data["message"]

    async def test_read_only_blocks_call(self):
        mcp_ro, client_ro = _make_mcp(read_only=True)
        fn = _get_tool(mcp_ro, "blender_transform_object")
        result = await fn(TransformObjectInput(name="Cube", location=(0, 0, 1)))
        client_ro.send_command.assert_not_called()
        assert json.loads(result)["status"] == "error"

    async def test_connection_error(self):
        self.client.send_command.side_effect = BlenderConnectionError("err")
        result = await self.fn(TransformObjectInput(name="Cube", location=(0, 0, 0)))
        assert json.loads(result)["status"] == "error"


# ---------------------------------------------------------------------------
# blender_delete_object
# ---------------------------------------------------------------------------


class TestDeleteObject:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_delete_object")

    async def test_calls_client(self):
        self.client.send_command.return_value = _success({"deleted": True, "name": "Cube"})
        result = await self.fn(DeleteObjectInput(name="Cube"))
        self.client.send_command.assert_called_once_with("delete_object", {"name": "Cube"})
        assert json.loads(result)["status"] == "success"

    async def test_read_only_blocks_call(self):
        mcp_ro, client_ro = _make_mcp(read_only=True)
        fn = _get_tool(mcp_ro, "blender_delete_object")
        result = await fn(DeleteObjectInput(name="Cube"))
        client_ro.send_command.assert_not_called()
        assert json.loads(result)["status"] == "error"

    async def test_connection_error(self):
        self.client.send_command.side_effect = BlenderConnectionError("err")
        result = await self.fn(DeleteObjectInput(name="Ghost"))
        assert json.loads(result)["status"] == "error"


# ---------------------------------------------------------------------------
# blender_set_material
# ---------------------------------------------------------------------------


class TestSetMaterial:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_set_material")

    async def test_calls_client(self):
        self.client.send_command.return_value = _success({"object": "Cube", "material": "MCP_Cube"})
        params = SetMaterialInput(object_name="Cube", color=(1.0, 0.0, 0.0, 1.0))
        await self.fn(params)
        self.client.send_command.assert_called_once()
        cmd_args = self.client.send_command.call_args[0]
        assert cmd_args[0] == "set_material"
        assert cmd_args[1]["object_name"] == "Cube"

    async def test_emission_sent_when_specified(self):
        self.client.send_command.return_value = _success({"object": "X", "material": "M"})
        params = SetMaterialInput(
            object_name="X",
            emission_color=(1.0, 0.5, 0.0),
            emission_strength=10.0,
        )
        await self.fn(params)
        sent = self.client.send_command.call_args[0][1]
        assert sent["emission_color"] == [1.0, 0.5, 0.0]
        assert sent["emission_strength"] == 10.0

    async def test_read_only_blocks_call(self):
        mcp_ro, client_ro = _make_mcp(read_only=True)
        fn = _get_tool(mcp_ro, "blender_set_material")
        result = await fn(SetMaterialInput(object_name="Cube"))
        client_ro.send_command.assert_not_called()
        assert json.loads(result)["status"] == "error"


# ---------------------------------------------------------------------------
# blender_add_light
# ---------------------------------------------------------------------------


class TestAddLight:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_add_light")

    async def test_calls_client_point_light(self):
        self.client.send_command.return_value = _success(
            {"name": "MCP_Point", "type": "POINT", "location": [0, 0, 3]}
        )
        params = AddLightInput(light_type=LightType.POINT)
        result = await self.fn(params)
        sent = self.client.send_command.call_args[0][1]
        assert sent["light_type"] == "POINT"
        assert json.loads(result)["status"] == "success"

    async def test_read_only_blocks_call(self):
        mcp_ro, client_ro = _make_mcp(read_only=True)
        fn = _get_tool(mcp_ro, "blender_add_light")
        result = await fn(AddLightInput(light_type=LightType.SUN))
        client_ro.send_command.assert_not_called()
        assert json.loads(result)["status"] == "error"

    async def test_connection_error(self):
        self.client.send_command.side_effect = BlenderConnectionError("err")
        result = await self.fn(AddLightInput(light_type=LightType.AREA))
        assert json.loads(result)["status"] == "error"


# ---------------------------------------------------------------------------
# blender_set_camera
# ---------------------------------------------------------------------------


class TestSetCamera:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_set_camera")

    async def test_calls_client(self):
        self.client.send_command.return_value = _success(
            {"name": "Camera", "location": [5, -5, 3], "lens": 50.0, "is_active_camera": True}
        )
        params = SetCameraInput(location=(5, -5, 3), lens=50.0)
        result = await self.fn(params)
        sent = self.client.send_command.call_args[0][1]
        assert sent["lens"] == 50.0
        assert json.loads(result)["status"] == "success"

    async def test_read_only_blocks_call(self):
        mcp_ro, client_ro = _make_mcp(read_only=True)
        fn = _get_tool(mcp_ro, "blender_set_camera")
        result = await fn(SetCameraInput(lens=35.0))
        client_ro.send_command.assert_not_called()
        assert json.loads(result)["status"] == "error"

    async def test_connection_error(self):
        self.client.send_command.side_effect = BlenderConnectionError("err")
        result = await self.fn(SetCameraInput())
        assert json.loads(result)["status"] == "error"
