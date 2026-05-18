"""Integration tests for Hyper3D tools using respx + httpx mocks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from mcp_blender_bridge_hyper3d.schemas import (
    Hyper3DGenerateImageParams,
    Hyper3DGenerateTextParams,
    Hyper3DImportParams,
    Hyper3DPollParams,
    Hyper3DStatusParams,
)

# ---------------------------------------------------------------------------
# Helpers to get tool callables
# ---------------------------------------------------------------------------

_RODIN_BASE = "https://hyperhuman.deemos.com/api/v2/rodin"
_STATUS_URL = f"{_RODIN_BASE}/status"


def _make_tools(
    api_key: str | None = "test-api-key",
    read_only: bool = False,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    """Build the tool functions by registering them against a mock FastMCP instance."""
    from mcp_blender_bridge_hyper3d.tools import register_tools

    tools: dict[str, Any] = {}

    class FakeMCP:
        def tool(self, *, name: str, annotations: dict) -> Any:  # type: ignore[type-arg]
            def decorator(fn: Any) -> Any:
                tools[name] = fn
                return fn

            return decorator

    client = MagicMock()
    env: dict[str, str] = {}
    if api_key:
        env["HYPER3D_API_KEY"] = api_key
    if cache_dir:
        env["BLENDER_BRIDGE_CACHE_DIR"] = cache_dir

    with patch.dict(os.environ, env, clear=False):
        register_tools(FakeMCP(), client, read_only=read_only)  # type: ignore[arg-type]

    return tools


# ---------------------------------------------------------------------------
# hyper3d_status
# ---------------------------------------------------------------------------


class TestHyper3DStatus:
    @pytest.mark.asyncio
    async def test_key_configured(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HYPER3D_API_KEY", "my-secret-key")
        tools = _make_tools(api_key="my-secret-key")
        result = await tools["hyper3d_status"](Hyper3DStatusParams())
        assert result["status"] == "success"
        assert result["api_key_configured"] is True
        assert result["plugin"] == "hyper3d"

    @pytest.mark.asyncio
    async def test_key_not_configured(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("HYPER3D_API_KEY", raising=False)
        tools = _make_tools(api_key=None)
        result = await tools["hyper3d_status"](Hyper3DStatusParams())
        assert result["status"] == "success"
        assert result["api_key_configured"] is False

    @pytest.mark.asyncio
    async def test_read_only_reflected(self) -> None:
        tools = _make_tools(api_key="k", read_only=True)
        result = await tools["hyper3d_status"](Hyper3DStatusParams())
        assert result["read_only"] is True


# ---------------------------------------------------------------------------
# hyper3d_generate_text
# ---------------------------------------------------------------------------


class TestHyper3DGenerateText:
    @pytest.mark.asyncio
    @respx.mock
    async def test_success(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HYPER3D_API_KEY", "test-api-key")
        respx.post(_RODIN_BASE).mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "task-uuid-001",
                    "subscription_key": "sub-key-001",
                },
            )
        )
        tools = _make_tools(api_key="test-api-key")
        result = await tools["hyper3d_generate_text"](
            Hyper3DGenerateTextParams(prompt="a wooden chair with curved legs")
        )
        assert result["status"] == "success"
        assert result["task_uuid"] == "task-uuid-001"
        assert result["subscription_key"] == "sub-key-001"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("HYPER3D_API_KEY", raising=False)
        tools = _make_tools(api_key=None)
        result = await tools["hyper3d_generate_text"](
            Hyper3DGenerateTextParams(prompt="some object")
        )
        assert result["status"] == "error"
        assert "HYPER3D_API_KEY" in result["message"]

    @pytest.mark.asyncio
    async def test_read_only_blocked(self) -> None:
        tools = _make_tools(read_only=True)
        result = await tools["hyper3d_generate_text"](
            Hyper3DGenerateTextParams(prompt="test")
        )
        assert result["status"] == "error"
        assert "read-only" in result["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_error_returned(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HYPER3D_API_KEY", "bad-key")
        respx.post(_RODIN_BASE).mock(
            return_value=httpx.Response(401, json={"detail": "Unauthorized"})
        )
        tools = _make_tools(api_key="bad-key")
        result = await tools["hyper3d_generate_text"](
            Hyper3DGenerateTextParams(prompt="test")
        )
        assert result["status"] == "error"
        assert "401" in result["message"]


# ---------------------------------------------------------------------------
# hyper3d_generate_image
# ---------------------------------------------------------------------------


class TestHyper3DGenerateImage:
    @pytest.mark.asyncio
    @respx.mock
    async def test_success_with_url(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HYPER3D_API_KEY", "test-api-key")
        # Mock the image fetch
        respx.get("https://example.com/photo.jpg").mock(
            return_value=httpx.Response(200, content=b"FAKEJPEG")
        )
        respx.post(_RODIN_BASE).mock(
            return_value=httpx.Response(
                200, json={"uuid": "img-task-uuid", "subscription_key": "sub-img"}
            )
        )
        tools = _make_tools(api_key="test-api-key")
        result = await tools["hyper3d_generate_image"](
            Hyper3DGenerateImageParams(image_url="https://example.com/photo.jpg")
        )
        assert result["status"] == "success"
        assert result["task_uuid"] == "img-task-uuid"

    @pytest.mark.asyncio
    async def test_no_image_source_returns_error(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HYPER3D_API_KEY", "test-api-key")
        tools = _make_tools(api_key="test-api-key")
        result = await tools["hyper3d_generate_image"](Hyper3DGenerateImageParams())
        assert result["status"] == "error"
        assert "image_url" in result["message"] or "image_path" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("HYPER3D_API_KEY", raising=False)
        tools = _make_tools(api_key=None)
        result = await tools["hyper3d_generate_image"](
            Hyper3DGenerateImageParams(image_url="https://example.com/x.jpg")
        )
        assert result["status"] == "error"
        assert "HYPER3D_API_KEY" in result["message"]


# ---------------------------------------------------------------------------
# hyper3d_poll
# ---------------------------------------------------------------------------


class TestHyper3DPoll:
    @pytest.mark.asyncio
    @respx.mock
    async def test_done_immediately(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HYPER3D_API_KEY", "test-api-key")
        respx.get(f"{_STATUS_URL}/task-001").mock(
            return_value=httpx.Response(
                200,
                json={"status": "Done", "jobs": [{"model_urls": {"glb": "https://cdn.hyper3d.ai/task-001/model.glb"}}]},
            )
        )
        tools = _make_tools(api_key="test-api-key")
        result = await tools["hyper3d_poll"](
            Hyper3DPollParams(task_uuid="task-001", max_wait=30)
        )
        assert result.get("status") == "Done"

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout_returns_error(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("HYPER3D_API_KEY", "test-api-key")
        # Always return "Processing" so we never finish
        respx.get(f"{_STATUS_URL}/task-timeout").mock(
            return_value=httpx.Response(200, json={"status": "Processing"})
        )
        tools = _make_tools(api_key="test-api-key")

        # Use a tiny max_wait and patch asyncio.sleep to avoid actual waiting
        with patch("mcp_blender_bridge_hyper3d.tools.asyncio.sleep", new_callable=AsyncMock):
            result = await tools["hyper3d_poll"](
                Hyper3DPollParams(task_uuid="task-timeout", max_wait=10)
            )
        assert result["status"] == "error"
        assert "did not complete" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("HYPER3D_API_KEY", raising=False)
        tools = _make_tools(api_key=None)
        result = await tools["hyper3d_poll"](Hyper3DPollParams(task_uuid="x", max_wait=10))
        assert result["status"] == "error"
        assert "HYPER3D_API_KEY" in result["message"]


# ---------------------------------------------------------------------------
# hyper3d_import
# ---------------------------------------------------------------------------


class TestHyper3DImport:
    @pytest.mark.asyncio
    @respx.mock
    async def test_downloads_and_sends_blender_command(
        self,
        monkeypatch,  # type: ignore[no-untyped-def]
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("HYPER3D_API_KEY", "test-api-key")
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))

        task_id = "import-task-001"
        model_url = f"https://cdn.hyper3d.ai/{task_id}/model.glb"

        # Status endpoint returns Done
        respx.get(f"{_STATUS_URL}/{task_id}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "Done",
                    "jobs": [{"model_urls": {"glb": model_url}}],
                },
            )
        )
        # Model download
        respx.get(model_url).mock(
            return_value=httpx.Response(200, content=b"GLBDATA")
        )

        # Mock the Blender client
        client_mock = MagicMock()
        client_mock.send_command = AsyncMock(
            return_value={"status": "success", "imported_objects": ["RodinMesh"]}
        )

        from mcp_blender_bridge_hyper3d.tools import register_tools

        tools: dict[str, Any] = {}

        class FakeMCP:
            def tool(self, *, name: str, annotations: dict) -> Any:  # type: ignore[type-arg]
                def decorator(fn: Any) -> Any:
                    tools[name] = fn
                    return fn
                return decorator

        with patch.dict(os.environ, {"HYPER3D_API_KEY": "test-api-key", "BLENDER_BRIDGE_CACHE_DIR": str(tmp_path)}):
            register_tools(FakeMCP(), client_mock)  # type: ignore[arg-type]

        result = await tools["hyper3d_import"](
            Hyper3DImportParams(task_uuid=task_id, import_format="glb")
        )

        # Model file should be cached
        cached_file = tmp_path / task_id / "model.glb"
        assert cached_file.exists()
        assert cached_file.read_bytes() == b"GLBDATA"

        # Blender command should have been called
        client_mock.send_command.assert_awaited_once()
        cmd_name, cmd_params = client_mock.send_command.call_args[0][:2]
        assert cmd_name == "import_3d_model"
        assert cmd_params["file_path"] == str(cached_file)
        assert cmd_params["import_format"] == "glb"

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_read_only_blocked(self) -> None:
        tools = _make_tools(read_only=True)
        result = await tools["hyper3d_import"](
            Hyper3DImportParams(task_uuid="x")
        )
        assert result["status"] == "error"
        assert "read-only" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("HYPER3D_API_KEY", raising=False)
        tools = _make_tools(api_key=None)
        result = await tools["hyper3d_import"](Hyper3DImportParams(task_uuid="x"))
        assert result["status"] == "error"
        assert "HYPER3D_API_KEY" in result["message"]
