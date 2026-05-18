"""Tests for code execution tool (code.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from mcp.server.fastmcp import FastMCP

from blender_bridge.client import BlenderClient, BlenderConnectionError
from blender_bridge.schemas import ExecutePythonInput
from blender_bridge.tools import code as code_tools


def _make_mcp(read_only: bool = False):
    mcp = FastMCP("test-code")
    client = AsyncMock(spec=BlenderClient)
    code_tools.register(mcp, client, read_only=read_only)
    return mcp, client


def _get_tool(mcp: FastMCP, name: str):
    return mcp._tool_manager._tools[name].fn


def _success(result) -> dict:
    return {"status": "success", "result": result}


class TestExecutePython:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_execute_python")

    async def test_calls_client_with_code(self):
        self.client.send_command.return_value = _success({"result": 42})
        result = await self.fn(ExecutePythonInput(code="result = 42"))
        self.client.send_command.assert_called_once_with("execute_python", {"code": "result = 42"})
        assert json.loads(result)["status"] == "success"

    async def test_returns_result_value(self):
        self.client.send_command.return_value = _success({"result": ["Cube", "Sphere"]})
        result = await self.fn(
            ExecutePythonInput(code="result = [o.name for o in bpy.data.objects]")
        )
        data = json.loads(result)
        assert data["status"] == "success"

    async def test_read_only_blocks_call(self):
        mcp_ro, client_ro = _make_mcp(read_only=True)
        fn = _get_tool(mcp_ro, "blender_execute_python")
        result = await fn(ExecutePythonInput(code="bpy.ops.object.delete()"))
        client_ro.send_command.assert_not_called()
        data = json.loads(result)
        assert data["status"] == "error"
        assert "read-only" in data["message"].lower()

    async def test_connection_error_returns_error_json(self):
        self.client.send_command.side_effect = BlenderConnectionError("not running")
        result = await self.fn(ExecutePythonInput(code="result = 1"))
        assert json.loads(result)["status"] == "error"

    async def test_generic_exception_returns_error_json(self):
        self.client.send_command.side_effect = RuntimeError("unexpected")
        result = await self.fn(ExecutePythonInput(code="result = 1"))
        assert json.loads(result)["status"] == "error"

    async def test_multiline_code_sent_intact(self):
        code = "import math\nresult = math.pi"
        self.client.send_command.return_value = _success({"result": 3.14159})
        await self.fn(ExecutePythonInput(code=code))
        sent = self.client.send_command.call_args[0][1]
        assert sent["code"] == code
