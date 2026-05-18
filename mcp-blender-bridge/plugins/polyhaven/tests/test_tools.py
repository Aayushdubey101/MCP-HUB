"""Tests for PolyHaven tools using respx + the _make_tools helper pattern."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from mcp_blender_bridge_polyhaven.schemas import (
    PolyHavenApplyTextureParams,
    PolyHavenCategoriesParams,
    PolyHavenDownloadParams,
    PolyHavenSearchParams,
    PolyHavenStatusParams,
)


# ---------------------------------------------------------------------------
# Helper: build tools dict by registering against a fake FastMCP
# ---------------------------------------------------------------------------


def _make_tools(read_only: bool = False, *, client: Any = None) -> dict[str, Any]:
    """Register polyhaven tools against a fake FastMCP and return the tool map.

    Cache-dependent tests must set ``BLENDER_BRIDGE_CACHE_DIR`` via the
    ``monkeypatch`` fixture *before* awaiting any tool, since
    ``get_cache_dir()`` reads the env var at tool-invocation time
    (not at registration time).
    """
    from mcp_blender_bridge_polyhaven.tools import register_tools

    tools: dict[str, Any] = {}

    class FakeMCP:
        def tool(self, *, name: str, annotations: dict) -> Any:  # type: ignore[type-arg]
            def decorator(fn: Any) -> Any:
                tools[name] = fn
                return fn

            return decorator

    if client is None:
        client = MagicMock()

    register_tools(FakeMCP(), client, read_only=read_only)  # type: ignore[arg-type]

    return tools


# ---------------------------------------------------------------------------
# polyhaven_status
# ---------------------------------------------------------------------------


class TestPolyHavenStatus:
    @pytest.mark.asyncio
    async def test_returns_success(self) -> None:
        tools = _make_tools()
        result = await tools["polyhaven_status"]()
        assert result["status"] == "success"
        assert result["plugin"] == "polyhaven"
        assert result["version"] == "0.1.0"
        assert "cache_dir" in result

    @pytest.mark.asyncio
    async def test_no_params_needed(self) -> None:
        tools = _make_tools()
        # Should call with no arguments
        result = await tools["polyhaven_status"]()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# polyhaven_categories
# ---------------------------------------------------------------------------


class TestPolyHavenCategories:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_categories(self) -> None:
        respx.get("https://api.polyhaven.com/categories/textures").mock(
            return_value=httpx.Response(
                200, json={"wood": {"name": "Wood"}, "metal": {"name": "Metal"}}
            )
        )
        tools = _make_tools()
        result = await tools["polyhaven_categories"](
            PolyHavenCategoriesParams(type="textures")
        )
        assert result["status"] == "success"
        assert "wood" in result["categories"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_error_returns_error(self) -> None:
        respx.get("https://api.polyhaven.com/categories/textures").mock(
            return_value=httpx.Response(500)
        )
        tools = _make_tools()
        result = await tools["polyhaven_categories"](
            PolyHavenCategoriesParams(type="textures")
        )
        assert result["status"] == "error"
        assert "PolyHaven API error" in result["message"]


# ---------------------------------------------------------------------------
# polyhaven_search
# ---------------------------------------------------------------------------


class TestPolyHavenSearch:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_asset_list(self) -> None:
        respx.get("https://api.polyhaven.com/assets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "wood_floor_01": {"name": "Wood Floor 01", "type": 0, "categories": ["wood"]},
                    "concrete_wall": {"name": "Concrete Wall", "type": 0, "categories": ["concrete"]},
                },
            )
        )
        tools = _make_tools()
        result = await tools["polyhaven_search"](PolyHavenSearchParams())
        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["assets"]) == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_type_filter_sent(self) -> None:
        route = respx.get("https://api.polyhaven.com/assets").mock(
            return_value=httpx.Response(200, json={})
        )
        tools = _make_tools()
        result = await tools["polyhaven_search"](PolyHavenSearchParams(type="textures"))
        assert result["status"] == "success"
        # Verify the query param was sent
        assert "t=textures" in str(route.calls.last.request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_api_error_returns_error(self) -> None:
        respx.get("https://api.polyhaven.com/assets").mock(
            return_value=httpx.Response(503)
        )
        tools = _make_tools()
        result = await tools["polyhaven_search"](PolyHavenSearchParams())
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# polyhaven_apply_texture (read-only guard)
# ---------------------------------------------------------------------------


class TestPolyHavenApplyTexture:
    @pytest.mark.asyncio
    async def test_read_only_blocked(self) -> None:
        tools = _make_tools(read_only=True)
        result = await tools["polyhaven_apply_texture"](
            PolyHavenApplyTextureParams(asset_id="wood_floor_01", object_name="Cube")
        )
        assert result["status"] == "error"
        assert "read-only" in result["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_asset_not_found_returns_error(self) -> None:
        respx.get("https://api.polyhaven.com/files/nonexistent").mock(
            return_value=httpx.Response(404)
        )
        tools = _make_tools()
        result = await tools["polyhaven_apply_texture"](
            PolyHavenApplyTextureParams(asset_id="nonexistent", object_name="Cube")
        )
        assert result["status"] == "error"
        assert "not found" in result["message"]


# ---------------------------------------------------------------------------
# polyhaven_download — full happy path + edge cases
# ---------------------------------------------------------------------------


def _files_response(asset_id: str = "wood_floor") -> dict[str, Any]:
    """Mimic the /files/<id> Polyhaven payload shape used by download tooling."""
    return {
        "Diffuse": {
            "4k": {"jpg": {"url": f"https://cdn.polyhaven.com/{asset_id}_diff_4k.jpg"}}
        },
        "Roughness": {
            "4k": {"jpg": {"url": f"https://cdn.polyhaven.com/{asset_id}_rough_4k.jpg"}}
        },
        "nor_gl": {
            "4k": {"jpg": {"url": f"https://cdn.polyhaven.com/{asset_id}_nor_4k.jpg"}}
        },
    }


class TestPolyHavenDownload:
    @pytest.mark.asyncio
    @respx.mock
    async def test_textures_download_writes_cache(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        respx.get("https://api.polyhaven.com/files/wood_floor").mock(
            return_value=httpx.Response(200, json=_files_response("wood_floor"))
        )
        respx.get("https://cdn.polyhaven.com/wood_floor_diff_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"diffuse-bytes")
        )
        respx.get("https://cdn.polyhaven.com/wood_floor_rough_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"rough-bytes")
        )
        respx.get("https://cdn.polyhaven.com/wood_floor_nor_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"normal-bytes")
        )

        tools = _make_tools()
        result = await tools["polyhaven_download"](
            PolyHavenDownloadParams(asset_id="wood_floor", type="textures")
        )

        assert result["status"] == "success"
        assert set(result["maps"].keys()) == {"diffuse", "roughness", "normal"}
        for map_path in result["maps"].values():
            assert os.path.exists(map_path)

    @pytest.mark.asyncio
    @respx.mock
    async def test_textures_download_uses_cache_on_second_call(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        respx.get("https://api.polyhaven.com/files/wood_floor").mock(
            return_value=httpx.Response(200, json=_files_response("wood_floor"))
        )
        diff_route = respx.get("https://cdn.polyhaven.com/wood_floor_diff_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"diffuse-bytes")
        )
        respx.get("https://cdn.polyhaven.com/wood_floor_rough_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"rough-bytes")
        )
        respx.get("https://cdn.polyhaven.com/wood_floor_nor_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"normal-bytes")
        )

        tools = _make_tools()
        params = PolyHavenDownloadParams(asset_id="wood_floor", type="textures")
        await tools["polyhaven_download"](params)
        await tools["polyhaven_download"](params)

        # First call downloads (1 hit). Second call must hit the on-disk cache.
        assert diff_route.call_count == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_asset_not_found_returns_error(self) -> None:
        respx.get("https://api.polyhaven.com/files/missing").mock(
            return_value=httpx.Response(404)
        )
        tools = _make_tools()
        result = await tools["polyhaven_download"](
            PolyHavenDownloadParams(asset_id="missing", type="textures")
        )
        assert result["status"] == "error"
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_files_api_error_returns_error(self) -> None:
        respx.get("https://api.polyhaven.com/files/blah").mock(
            return_value=httpx.Response(500)
        )
        tools = _make_tools()
        result = await tools["polyhaven_download"](
            PolyHavenDownloadParams(asset_id="blah", type="textures")
        )
        assert result["status"] == "error"
        assert "PolyHaven API error" in result["message"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_non_texture_type_returns_unsupported_error(self) -> None:
        respx.get("https://api.polyhaven.com/files/sky_01").mock(
            return_value=httpx.Response(200, json={"hdri": {}})
        )
        tools = _make_tools()
        result = await tools["polyhaven_download"](
            PolyHavenDownloadParams(asset_id="sky_01", type="hdris")
        )
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# polyhaven_apply_texture — happy path including bridge call
# ---------------------------------------------------------------------------


class TestPolyHavenApplyTextureFull:
    @pytest.mark.asyncio
    @respx.mock
    async def test_apply_texture_downloads_and_calls_bridge(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        respx.get("https://api.polyhaven.com/files/wood_floor").mock(
            return_value=httpx.Response(200, json=_files_response("wood_floor"))
        )
        respx.get("https://cdn.polyhaven.com/wood_floor_diff_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"d")
        )
        respx.get("https://cdn.polyhaven.com/wood_floor_rough_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"r")
        )
        respx.get("https://cdn.polyhaven.com/wood_floor_nor_4k.jpg").mock(
            return_value=httpx.Response(200, content=b"n")
        )

        client = MagicMock()
        client.send_command = AsyncMock(return_value={"status": "success", "applied": True})
        tools = _make_tools(client=client)

        result = await tools["polyhaven_apply_texture"](
            PolyHavenApplyTextureParams(
                asset_id="wood_floor", object_name="Cube", resolution="4k"
            )
        )
        assert result == {"status": "success", "applied": True}
        client.send_command.assert_awaited_once()
        cmd_name, cmd_payload = client.send_command.call_args.args[:2]
        assert cmd_name == "apply_polyhaven_texture"
        assert cmd_payload["object_name"] == "Cube"
        assert cmd_payload["asset_id"] == "wood_floor"
        assert set(cmd_payload["maps"].keys()) == {"diffuse", "roughness", "normal"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_apply_texture_files_api_error(self) -> None:
        respx.get("https://api.polyhaven.com/files/wood_floor").mock(
            return_value=httpx.Response(503)
        )
        tools = _make_tools()
        result = await tools["polyhaven_apply_texture"](
            PolyHavenApplyTextureParams(asset_id="wood_floor", object_name="Cube")
        )
        assert result["status"] == "error"
        assert "PolyHaven API error" in result["message"]


# ---------------------------------------------------------------------------
# polyhaven_search — search filter
# ---------------------------------------------------------------------------


class TestPolyHavenSearchExtra:
    @pytest.mark.asyncio
    @respx.mock
    async def test_search_string_passed_through(self) -> None:
        route = respx.get("https://api.polyhaven.com/assets").mock(
            return_value=httpx.Response(200, json={})
        )
        tools = _make_tools()
        await tools["polyhaven_search"](
            PolyHavenSearchParams(category="wood", search="floor")
        )
        url = str(route.calls.last.request.url)
        assert "c=wood" in url
        assert "s=floor" in url
