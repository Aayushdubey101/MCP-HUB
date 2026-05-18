"""Tests for render tool (render.py)."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

from mcp.server.fastmcp import FastMCP, Image

from blender_bridge.client import BlenderClient, BlenderConnectionError
from blender_bridge.schemas import RenderImageInput
from blender_bridge.tools import render as render_tools


def _make_mcp(read_only: bool = False):
    mcp = FastMCP("test-render")
    client = AsyncMock(spec=BlenderClient)
    render_tools.register(mcp, client, read_only=read_only)
    return mcp, client


def _get_tool(mcp: FastMCP, name: str):
    return mcp._tool_manager._tools[name].fn


def _fake_image_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _success_with_image() -> dict:
    return {
        "status": "success",
        "result": {
            "frame": 1,
            "engine": "EEVEE",
            "render_time_seconds": 0.5,
            "resolution": [1920, 1080],
            "output_path": None,
            "image_data": base64.b64encode(_fake_image_bytes()).decode(),
        },
    }


class TestRenderImage:
    def setup_method(self):
        self.mcp, self.client = _make_mcp()
        self.fn = _get_tool(self.mcp, "blender_render_image")

    async def test_calls_client_with_correct_command(self):
        self.client.send_command.return_value = _success_with_image()
        await self.fn(RenderImageInput())
        self.client.send_command.assert_called_once()
        cmd_name = self.client.send_command.call_args[0][0]
        assert cmd_name == "render_image"

    async def test_returns_list_with_metadata_and_image(self):
        self.client.send_command.return_value = _success_with_image()
        result = await self.fn(RenderImageInput())
        assert isinstance(result, list)
        assert len(result) == 2
        meta = json.loads(result[0])
        assert meta["status"] == "success"
        assert isinstance(result[1], Image)

    async def test_engine_value_sent(self):
        self.client.send_command.return_value = _success_with_image()
        await self.fn(RenderImageInput(engine="CYCLES"))
        sent = self.client.send_command.call_args[0][1]
        assert sent["engine"] == "CYCLES"

    async def test_no_engine_sends_none(self):
        self.client.send_command.return_value = _success_with_image()
        await self.fn(RenderImageInput())
        sent = self.client.send_command.call_args[0][1]
        assert sent["engine"] is None

    async def test_timeout_passed_to_send_command(self):
        self.client.send_command.return_value = _success_with_image()
        await self.fn(RenderImageInput(timeout_seconds=600.0))
        kwargs = self.client.send_command.call_args[1]
        assert kwargs.get("timeout") == 600.0

    async def test_read_only_blocks_call(self):
        mcp_ro, client_ro = _make_mcp(read_only=True)
        fn = _get_tool(mcp_ro, "blender_render_image")
        result = await fn(RenderImageInput())
        client_ro.send_command.assert_not_called()
        assert isinstance(result, list)
        data = json.loads(result[0])
        assert data["status"] == "error"
        assert "read-only" in data["message"].lower()

    async def test_connection_error_returns_error_list(self):
        self.client.send_command.side_effect = BlenderConnectionError("err")
        result = await self.fn(RenderImageInput())
        assert isinstance(result, list)
        assert json.loads(result[0])["status"] == "error"
