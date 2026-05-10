from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from blender_bridge.client import BlenderClient

from .schemas import (
    PolyHavenStatusParams,
    PolyHavenCategoriesParams,
    PolyHavenSearchParams,
    PolyHavenDownloadParams,
    PolyHavenApplyTextureParams,
)

logger = logging.getLogger(__name__)

def get_cache_dir() -> Path:
    cache_dir = os.environ.get(
        "BLENDER_BRIDGE_CACHE_DIR",
        str(Path.home() / ".cache" / "mcp-blender-bridge" / "assets" / "polyhaven")
    )
    path = Path(cache_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path

def register_tools(mcp: FastMCP, client: Any, *, read_only: bool = False) -> None:
    @mcp.tool(
        name="polyhaven_status",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
    )
    async def polyhaven_status() -> dict[str, Any]:
        """Check the status of the PolyHaven plugin."""
        return {
            "status": "success",
            "plugin": "polyhaven",
            "version": "0.1.0",
            "cache_dir": str(get_cache_dir()),
        }

    @mcp.tool(
        name="polyhaven_categories",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def polyhaven_categories(params: PolyHavenCategoriesParams) -> dict[str, Any]:
        """Get a list of available asset categories for a specific asset type."""
        url = f"https://api.polyhaven.com/categories/{params.type}"
        async with httpx.AsyncClient() as http_client:
            try:
                response = await http_client.get(url, timeout=10.0)
                response.raise_for_status()
                return {"status": "success", "categories": response.json()}
            except httpx.HTTPError as e:
                return {"status": "error", "message": f"PolyHaven API error: {e}"}

    @mcp.tool(
        name="polyhaven_search",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def polyhaven_search(params: PolyHavenSearchParams) -> dict[str, Any]:
        """Search for assets on PolyHaven."""
        url = "https://api.polyhaven.com/assets"
        query_params = {}
        if params.type:
            query_params["t"] = params.type
        if params.category:
            query_params["c"] = params.category
        if params.search:
            query_params["s"] = params.search

        async with httpx.AsyncClient() as http_client:
            try:
                response = await http_client.get(url, params=query_params, timeout=10.0)
                response.raise_for_status()
                assets = response.json()
                
                asset_list = []
                for asset_id, data in list(assets.items())[:50]:
                    asset_list.append({
                        "id": asset_id,
                        "name": data.get("name"),
                        "type": data.get("type"),
                        "categories": data.get("categories", []),
                    })
                    
                return {
                    "status": "success", 
                    "count": len(assets),
                    "results_truncated": len(assets) > 50,
                    "assets": asset_list
                }
            except httpx.HTTPError as e:
                return {"status": "error", "message": f"PolyHaven API error: {e}"}

    @mcp.tool(
        name="polyhaven_download",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def polyhaven_download(params: PolyHavenDownloadParams) -> dict[str, Any]:
        """Download a PolyHaven asset and its required files to the local cache."""
        url = f"https://api.polyhaven.com/files/{params.asset_id}"
        async with httpx.AsyncClient() as http_client:
            try:
                response = await http_client.get(url, timeout=10.0)
                if response.status_code == 404:
                    return {"status": "error", "message": f"Asset '{params.asset_id}' not found."}
                response.raise_for_status()
                files_data = response.json()
            except httpx.HTTPError as e:
                return {"status": "error", "message": f"PolyHaven API error: {e}"}

        if params.type == "textures":
            cache_dir = get_cache_dir() / params.asset_id / "downloaded"
            cache_dir.mkdir(parents=True, exist_ok=True)
            maps = {}
            map_types = {
                "diffuse": ["Diffuse", "diff"],
                "roughness": ["Roughness", "rough"],
                "normal": ["nor_gl", "Normal", "nor"]
            }
            
            try:
                async with httpx.AsyncClient() as dl_client:
                    for map_key, api_keys in map_types.items():
                        map_url = None
                        for api_key in api_keys:
                            if api_key in files_data:
                                res_data = files_data[api_key].get("4k") or next(iter(files_data[api_key].values()))
                                fmt_data = res_data.get("jpg") or res_data.get("png") or next(iter(res_data.values()))
                                map_url = fmt_data["url"]
                                break
                        
                        if map_url:
                            filename = map_url.split("/")[-1]
                            filepath = cache_dir / filename
                            if not filepath.exists():
                                logger.info(f"Downloading {map_url} to {filepath}")
                                resp = await dl_client.get(map_url, timeout=60.0)
                                resp.raise_for_status()
                                filepath.write_bytes(resp.content)
                            maps[map_key] = str(filepath)
                return {"status": "success", "asset_id": params.asset_id, "maps": maps, "cache_dir": str(cache_dir)}
            except Exception as e:
                return {"status": "error", "message": f"Error downloading maps: {e}"}
                
        return {"status": "error", "message": "Only texture downloads are fully supported by apply_texture currently."}

    @mcp.tool(
        name="polyhaven_apply_texture",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        }
    )
    async def polyhaven_apply_texture(params: PolyHavenApplyTextureParams) -> dict[str, Any]:
        """Download and apply a PolyHaven texture to a Blender object."""
        if read_only:
            return {"status": "error", "message": "Cannot apply texture in read-only mode."}
            
        url = f"https://api.polyhaven.com/files/{params.asset_id}"
        async with httpx.AsyncClient() as http_client:
            try:
                response = await http_client.get(url, timeout=10.0)
                if response.status_code == 404:
                    return {"status": "error", "message": f"Asset '{params.asset_id}' not found."}
                response.raise_for_status()
                files_data = response.json()
            except httpx.HTTPError as e:
                return {"status": "error", "message": f"PolyHaven API error: {e}"}

        maps = {}
        try:
            cache_dir = get_cache_dir() / params.asset_id / params.resolution
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            map_types = {
                "diffuse": ["Diffuse", "diff"],
                "roughness": ["Roughness", "rough"],
                "normal": ["nor_gl", "Normal", "nor"]
            }
            
            async with httpx.AsyncClient() as dl_client:
                for map_key, api_keys in map_types.items():
                    map_url = None
                    for api_key in api_keys:
                        if api_key in files_data:
                            res_data = files_data[api_key].get(params.resolution) or next(iter(files_data[api_key].values()))
                            fmt_data = res_data.get("jpg") or res_data.get("png") or next(iter(res_data.values()))
                            map_url = fmt_data["url"]
                            break
                    
                    if map_url:
                        filename = map_url.split("/")[-1]
                        filepath = cache_dir / filename
                        if not filepath.exists():
                            logger.info(f"Downloading {map_url} to {filepath}")
                            resp = await dl_client.get(map_url, timeout=60.0)
                            resp.raise_for_status()
                            filepath.write_bytes(resp.content)
                            
                        maps[map_key] = str(filepath)
                        
        except Exception as e:
            return {"status": "error", "message": f"Error downloading maps: {e}"}

        return await client.send_command(
            "apply_polyhaven_texture",
            {
                "object_name": params.object_name,
                "asset_id": params.asset_id,
                "maps": maps,
            },
            timeout=60.0,
        )
