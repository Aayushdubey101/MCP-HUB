"""Integration tests for Sketchfab tools using respx + httpx mocks."""

from __future__ import annotations

import os
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from mcp_blender_bridge_sketchfab.schemas import (
    SketchfabDownloadParams,
    SketchfabPreviewParams,
    SketchfabSearchParams,
    SketchfabStatusParams,
)

_API_BASE = "https://api.sketchfab.com/v3"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_tools(
    api_key: str | None = "test-api-key",
    read_only: bool = False,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    from mcp_blender_bridge_sketchfab.tools import register_tools

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
        env["SKETCHFAB_API_KEY"] = api_key
    if cache_dir:
        env["BLENDER_BRIDGE_CACHE_DIR"] = cache_dir

    with patch.dict(os.environ, env, clear=False):
        register_tools(FakeMCP(), client, read_only=read_only)  # type: ignore[arg-type]

    return tools


def _make_fake_zip() -> bytes:
    """Create a minimal valid ZIP containing a .glb file."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("model.glb", b"GLBDATA")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# sketchfab_status
# ---------------------------------------------------------------------------


class TestSketchfabStatus:
    @pytest.mark.asyncio
    async def test_key_configured(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("SKETCHFAB_API_KEY", "my-key")
        tools = _make_tools(api_key="my-key")
        result = await tools["sketchfab_status"](SketchfabStatusParams())
        assert result["status"] == "success"
        assert result["api_key_configured"] is True
        assert result["plugin"] == "sketchfab"

    @pytest.mark.asyncio
    async def test_key_not_configured(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("SKETCHFAB_API_KEY", raising=False)
        tools = _make_tools(api_key=None)
        result = await tools["sketchfab_status"](SketchfabStatusParams())
        assert result["status"] == "success"
        assert result["api_key_configured"] is False

    @pytest.mark.asyncio
    async def test_read_only_reflected(self) -> None:
        tools = _make_tools(read_only=True)
        result = await tools["sketchfab_status"](SketchfabStatusParams())
        assert result["read_only"] is True


# ---------------------------------------------------------------------------
# sketchfab_search
# ---------------------------------------------------------------------------


class TestSketchfabSearch:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_model_list(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("SKETCHFAB_API_KEY", "test-api-key")
        respx.get(f"{_API_BASE}/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "count": 2,
                    "results": [
                        {
                            "uid": "uid-001",
                            "name": "Wooden Chair",
                            "user": {"displayName": "Artist1"},
                            "isDownloadable": True,
                            "likeCount": 42,
                            "viewCount": 1000,
                            "faceCount": 5000,
                            "vertexCount": 2500,
                            "thumbnails": {"images": [{"url": "https://cdn.sf.com/thumb1.jpg"}]},
                            "description": "A nice chair.",
                            "license": {"label": "CC BY 4.0"},
                        },
                        {
                            "uid": "uid-002",
                            "name": "Metal Table",
                            "user": {"displayName": "Artist2"},
                            "isDownloadable": False,
                            "likeCount": 10,
                            "viewCount": 200,
                            "faceCount": 1000,
                            "vertexCount": 500,
                            "thumbnails": {},
                            "description": "",
                            "license": None,
                        },
                    ],
                },
            )
        )
        tools = _make_tools()
        result = await tools["sketchfab_search"](SketchfabSearchParams(query="furniture"))
        assert result["status"] == "success"
        assert result["returned"] == 2
        assert result["total_count"] == 2
        assert result["models"][0]["uid"] == "uid-001"
        assert result["models"][0]["name"] == "Wooden Chair"

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_error_returns_error(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("SKETCHFAB_API_KEY", "test-api-key")
        respx.get(f"{_API_BASE}/models").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        tools = _make_tools()
        result = await tools["sketchfab_search"](SketchfabSearchParams(query="chair"))
        assert result["status"] == "error"
        assert "500" in result["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_works_without_api_key(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Search can work without a key (public endpoint)."""
        monkeypatch.delenv("SKETCHFAB_API_KEY", raising=False)
        respx.get(f"{_API_BASE}/models").mock(
            return_value=httpx.Response(200, json={"count": 0, "results": []})
        )
        tools = _make_tools(api_key=None)
        result = await tools["sketchfab_search"](SketchfabSearchParams(query="test"))
        assert result["status"] == "success"
        assert result["returned"] == 0


# ---------------------------------------------------------------------------
# sketchfab_preview
# ---------------------------------------------------------------------------


class TestSketchfabPreview:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_model_details(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("SKETCHFAB_API_KEY", "test-api-key")
        uid = "preview-uid-001"
        respx.get(f"{_API_BASE}/models/{uid}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uid": uid,
                    "name": "Detailed Chair",
                    "user": {"displayName": "Author"},
                    "isDownloadable": True,
                    "likeCount": 5,
                    "viewCount": 50,
                    "faceCount": 1000,
                    "vertexCount": 500,
                    "thumbnails": {},
                    "description": "Very detailed.",
                    "license": {"label": "CC BY 4.0"},
                    "tags": [{"name": "furniture"}, {"name": "chair"}],
                    "categories": [{"name": "Furniture"}],
                    "isAnimated": False,
                    "isRigged": False,
                    "hasPbrMaterials": True,
                },
            )
        )
        tools = _make_tools()
        result = await tools["sketchfab_preview"](SketchfabPreviewParams(uid=uid))
        assert result["status"] == "success"
        model = result["model"]
        assert model["uid"] == uid
        assert model["tags"] == ["furniture", "chair"]
        assert model["pbr"] is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_not_found_returns_error(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("SKETCHFAB_API_KEY", "test-api-key")
        uid = "doesnotexist"
        respx.get(f"{_API_BASE}/models/{uid}").mock(
            return_value=httpx.Response(404)
        )
        tools = _make_tools()
        result = await tools["sketchfab_preview"](SketchfabPreviewParams(uid=uid))
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ---------------------------------------------------------------------------
# sketchfab_download
# ---------------------------------------------------------------------------


class TestSketchfabDownload:
    @pytest.mark.asyncio
    async def test_read_only_blocked(self) -> None:
        tools = _make_tools(read_only=True)
        result = await tools["sketchfab_download"](SketchfabDownloadParams(uid="x"))
        assert result["status"] == "error"
        assert "read-only" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("SKETCHFAB_API_KEY", raising=False)
        tools = _make_tools(api_key=None)
        result = await tools["sketchfab_download"](SketchfabDownloadParams(uid="x"))
        assert result["status"] == "error"
        assert "SKETCHFAB_API_KEY" in result["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_download_url(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("SKETCHFAB_API_KEY", "test-api-key")
        uid = "missing-uid"
        respx.get(f"{_API_BASE}/models/{uid}/download").mock(
            return_value=httpx.Response(404)
        )
        tools = _make_tools()
        result = await tools["sketchfab_download"](SketchfabDownloadParams(uid=uid))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_403_forbidden(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("SKETCHFAB_API_KEY", "test-api-key")
        uid = "paid-uid"
        respx.get(f"{_API_BASE}/models/{uid}/download").mock(
            return_value=httpx.Response(403)
        )
        tools = _make_tools()
        result = await tools["sketchfab_download"](SketchfabDownloadParams(uid=uid))
        assert result["status"] == "error"
        assert "Access denied" in result["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_full_download_and_import(
        self,
        monkeypatch,  # type: ignore[no-untyped-def]
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("SKETCHFAB_API_KEY", "test-api-key")
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))

        uid = "download-uid-001"
        fake_download_url = "https://cdn.sketchfab.com/archives/model.zip"

        respx.get(f"{_API_BASE}/models/{uid}/download").mock(
            return_value=httpx.Response(
                200,
                json={"gltf": {"url": fake_download_url, "size": 12345}},
            )
        )
        respx.get(fake_download_url).mock(
            return_value=httpx.Response(200, content=_make_fake_zip())
        )

        client_mock = MagicMock()
        client_mock.send_command = AsyncMock(
            return_value={"status": "success", "imported_objects": ["SketchfabMesh"]}
        )

        from mcp_blender_bridge_sketchfab.tools import register_tools

        tools: dict[str, Any] = {}

        class FakeMCP:
            def tool(self, *, name: str, annotations: dict) -> Any:  # type: ignore[type-arg]
                def decorator(fn: Any) -> Any:
                    tools[name] = fn
                    return fn
                return decorator

        with patch.dict(os.environ, {
            "SKETCHFAB_API_KEY": "test-api-key",
            "BLENDER_BRIDGE_CACHE_DIR": str(tmp_path),
        }):
            register_tools(FakeMCP(), client_mock)  # type: ignore[arg-type]

        result = await tools["sketchfab_download"](SketchfabDownloadParams(uid=uid))

        # model.glb should exist in the cache
        glb_path = tmp_path / uid / "model.glb"
        assert glb_path.exists()

        # Blender import_3d_model was called
        client_mock.send_command.assert_awaited_once()
        cmd_name = client_mock.send_command.call_args[0][0]
        assert cmd_name == "import_3d_model"

        assert result["status"] == "success"
