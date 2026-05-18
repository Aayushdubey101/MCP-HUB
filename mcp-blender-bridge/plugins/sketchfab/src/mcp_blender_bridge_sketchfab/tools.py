"""Sketchfab tool implementations.

Four async tools registered via ``register_tools(mcp, client)``.
``SKETCHFAB_API_KEY`` is read at *call time*, not at import time, so
the server starts cleanly without the key configured.

Sketchfab API v3: https://sketchfab.com/developers/data-api/v3/
"""

from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    pass  # BlenderClient kept here only if needed

from .schemas import (
    SketchfabDownloadParams,
    SketchfabPreviewParams,
    SketchfabSearchParams,
    SketchfabStatusParams,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://api.sketchfab.com/v3"
_PLUGIN_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_api_key() -> str | None:
    """Return the Sketchfab API key from the environment, or None if unset."""
    return os.environ.get("SKETCHFAB_API_KEY")


def _get_cache_dir(uid: str) -> Path:
    """Return (and create) the cache directory for a given model UID."""
    base = os.environ.get(
        "BLENDER_BRIDGE_CACHE_DIR",
        str(Path.home() / ".cache" / "mcp-blender-bridge" / "assets" / "sketchfab"),
    )
    path = Path(base) / uid
    path.mkdir(parents=True, exist_ok=True)
    return path


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Token {api_key}"}


def _format_model(model: dict[str, Any]) -> dict[str, Any]:
    """Extract the most useful fields from a Sketchfab model record."""
    thumbnails = model.get("thumbnails", {}).get("images", [])
    thumb_url = thumbnails[0].get("url") if thumbnails else None
    return {
        "uid": model.get("uid"),
        "name": model.get("name"),
        "author": (model.get("user") or {}).get("displayName"),
        "description": (model.get("description") or "")[:200],
        "face_count": model.get("faceCount"),
        "vertex_count": model.get("vertexCount"),
        "is_downloadable": model.get("isDownloadable", False),
        "like_count": model.get("likeCount", 0),
        "view_count": model.get("viewCount", 0),
        "thumbnail_url": thumb_url,
        "sketchfab_url": f"https://sketchfab.com/models/{model.get('uid')}",
        "license": (model.get("license") or {}).get("label"),
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP, client: Any, *, read_only: bool = False) -> None:
    """Register all Sketchfab tools with the FastMCP server."""

    @mcp.tool(
        name="sketchfab_status",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def sketchfab_status(params: SketchfabStatusParams) -> dict[str, Any]:
        """Check the Sketchfab plugin status and whether the API key is configured."""
        _ = params
        api_key = _get_api_key()
        return {
            "status": "success",
            "plugin": "sketchfab",
            "version": _PLUGIN_VERSION,
            "api_key_configured": api_key is not None,
            "read_only": read_only,
            "api_docs": "https://sketchfab.com/developers/data-api/v3/",
        }

    @mcp.tool(
        name="sketchfab_search",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sketchfab_search(params: SketchfabSearchParams) -> dict[str, Any]:
        """Search the Sketchfab library for 3D models.

        Returns a list of models with metadata (uid, name, author, face count,
        thumbnail URL, download availability, etc.).

        Note: SKETCHFAB_API_KEY is optional for public search — but required
        for downloading models. Configure it in advance to unlock full workflow.
        """
        api_key = _get_api_key()
        headers = _auth_headers(api_key) if api_key else {}

        query_params: dict[str, Any] = {
            "q": params.query,
            "count": params.count,
            "sort_by": params.sort_by,
        }
        if params.downloadable:
            query_params["downloadable"] = "true"
        if params.animated is not None:
            query_params["animated"] = str(params.animated).lower()
        if params.categories:
            query_params["categories"] = params.categories

        async with httpx.AsyncClient() as http_client:
            try:
                resp = await http_client.get(
                    f"{_API_BASE}/models",
                    params=query_params,
                    headers=headers,
                    timeout=20.0,
                )
                resp.raise_for_status()
                data = resp.json()
                models = [_format_model(m) for m in data.get("results", [])]
                return {
                    "status": "success",
                    "query": params.query,
                    "total_count": data.get("count", 0),
                    "returned": len(models),
                    "models": models,
                }
            except httpx.HTTPStatusError as exc:
                return {
                    "status": "error",
                    "message": f"Sketchfab API error {exc.response.status_code}: {exc.response.text}",
                }
            except httpx.HTTPError as exc:
                return {"status": "error", "message": f"HTTP error: {exc}"}

    @mcp.tool(
        name="sketchfab_preview",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def sketchfab_preview(params: SketchfabPreviewParams) -> dict[str, Any]:
        """Get detailed metadata for a single Sketchfab model by its UID.

        Returns full model details including geometry stats, tags, license
        information, and download availability.
        """
        api_key = _get_api_key()
        headers = _auth_headers(api_key) if api_key else {}

        async with httpx.AsyncClient() as http_client:
            try:
                resp = await http_client.get(
                    f"{_API_BASE}/models/{params.uid}",
                    headers=headers,
                    timeout=15.0,
                )
                if resp.status_code == 404:
                    return {
                        "status": "error",
                        "message": f"Model '{params.uid}' not found on Sketchfab.",
                    }
                resp.raise_for_status()
                model = resp.json()
                formatted = _format_model(model)
                # Add extra preview-specific fields
                formatted["tags"] = [t.get("name") for t in model.get("tags", [])]
                formatted["categories_full"] = [
                    c.get("name") for c in model.get("categories", [])
                ]
                formatted["animated"] = model.get("isAnimated", False)
                formatted["rigged"] = model.get("isRigged", False)
                formatted["pbr"] = model.get("hasPbrMaterials", False)
                return {"status": "success", "model": formatted}
            except httpx.HTTPStatusError as exc:
                return {
                    "status": "error",
                    "message": f"Sketchfab API error {exc.response.status_code}: {exc.response.text}",
                }
            except httpx.HTTPError as exc:
                return {"status": "error", "message": f"HTTP error: {exc}"}

    @mcp.tool(
        name="sketchfab_download",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def sketchfab_download(params: SketchfabDownloadParams) -> dict[str, Any]:
        """Download a Sketchfab model as GLTF and import it into Blender.

        Downloads the GLTF package to the local cache, extracts it, then
        sends an import_3d_model command to the connected Blender instance.
        Requires SKETCHFAB_API_KEY to be set (needed for download endpoint).
        """
        if read_only:
            return {"status": "error", "message": "Cannot download models in read-only mode."}

        api_key = _get_api_key()
        if not api_key:
            return {
                "status": "error",
                "message": (
                    "SKETCHFAB_API_KEY is not set. "
                    "Get a token at https://sketchfab.com/settings#password."
                ),
            }

        async with httpx.AsyncClient() as http_client:
            try:
                # 1. Get the download URL from the Sketchfab API
                resp = await http_client.get(
                    f"{_API_BASE}/models/{params.uid}/download",
                    headers=_auth_headers(api_key),
                    timeout=20.0,
                )
                if resp.status_code == 404:
                    return {
                        "status": "error",
                        "message": f"Model '{params.uid}' not found or not downloadable.",
                    }
                if resp.status_code == 403:
                    return {
                        "status": "error",
                        "message": (
                            f"Access denied for model '{params.uid}'. "
                            "The model may not be freely downloadable."
                        ),
                    }
                resp.raise_for_status()
                dl_data = resp.json()

                # Prefer GLTF, fall back to source
                gltf_info = dl_data.get("gltf") or dl_data.get("source") or {}
                download_url: str | None = gltf_info.get("url")
                if not download_url:
                    return {
                        "status": "error",
                        "message": f"No GLTF download URL found for model '{params.uid}'.",
                    }

                # 2. Download the ZIP archive
                cache_dir = _get_cache_dir(params.uid)
                zip_path = cache_dir / "model.zip"
                glb_path = cache_dir / "model.glb"

                if not glb_path.exists():
                    logger.info("Downloading Sketchfab model %s → %s", params.uid, zip_path)
                    dl_resp = await http_client.get(download_url, timeout=120.0, follow_redirects=True)
                    dl_resp.raise_for_status()
                    zip_path.write_bytes(dl_resp.content)

                    # 3. Extract and locate the .gltf/.glb file
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(cache_dir)

                    # Find the primary model file
                    glb_candidates = list(cache_dir.rglob("*.glb")) + list(cache_dir.rglob("*.gltf"))
                    if not glb_candidates:
                        return {
                            "status": "error",
                            "message": "Downloaded archive contained no .glb or .gltf file.",
                        }
                    primary_file = glb_candidates[0]
                    # Normalize to a known filename
                    if primary_file != glb_path:
                        glb_path.write_bytes(primary_file.read_bytes())
                else:
                    logger.info("Using cached Sketchfab model at %s", glb_path)

            except httpx.HTTPStatusError as exc:
                return {
                    "status": "error",
                    "message": f"Download error {exc.response.status_code}: {exc.response.text}",
                }
            except httpx.HTTPError as exc:
                return {"status": "error", "message": f"HTTP error: {exc}"}
            except zipfile.BadZipFile:
                return {"status": "error", "message": "Downloaded file was not a valid ZIP archive."}

        # 4. Send import command to Blender
        try:
            result = await client.send_command(
                "import_3d_model",
                {
                    "file_path": str(glb_path),
                    "object_name": params.object_name,
                    "import_format": "glb",
                },
                timeout=60.0,
            )
            return result  # type: ignore[return-value]
        except Exception as exc:
            return {"status": "error", "message": f"Blender import error: {exc}"}
