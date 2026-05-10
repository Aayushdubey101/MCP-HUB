"""Hyper3D Rodin tool implementations.

All five tools are registered via ``register_tools(mcp, client)``.
The ``HYPER3D_API_KEY`` environment variable is read at *call time*, not at
import time, so the server can start without the key configured — users get a
clear error only when they actually invoke a generation tool.

Rodin API base: https://hyperhuman.deemos.com/api/v2/rodin
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from blender_bridge.client import BlenderClient

from .schemas import (
    Hyper3DGenerateImageParams,
    Hyper3DGenerateTextParams,
    Hyper3DImportParams,
    Hyper3DPollParams,
    Hyper3DStatusParams,
)

logger = logging.getLogger(__name__)

_RODIN_BASE = "https://hyperhuman.deemos.com/api/v2/rodin"
_STATUS_URL = f"{_RODIN_BASE}/status"
_PLUGIN_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_api_key() -> str | None:
    """Return the Hyper3D API key from the environment, or None if unset."""
    return os.environ.get("HYPER3D_API_KEY")


def _get_cache_dir(task_uuid: str) -> Path:
    """Return (and create) the cache directory for a given task UUID."""
    base = os.environ.get(
        "BLENDER_BRIDGE_CACHE_DIR",
        str(Path.home() / ".cache" / "mcp-blender-bridge" / "assets" / "hyper3d"),
    )
    path = Path(base) / task_uuid
    path.mkdir(parents=True, exist_ok=True)
    return path


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


async def _poll_until_done(
    http_client: httpx.AsyncClient,
    task_uuid: str,
    api_key: str,
    max_wait: int,
) -> dict[str, Any]:
    """Poll the Rodin status endpoint with exponential backoff until done or timeout.

    Returns the final status payload dict, or raises on timeout / API error.
    """
    interval = 5  # seconds — doubles each iteration, capped at 60s
    elapsed = 0

    while elapsed < max_wait:
        resp = await http_client.get(
            f"{_STATUS_URL}/{task_uuid}",
            headers=_auth_headers(api_key),
            timeout=30.0,
        )
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()

        job_status = payload.get("status") or payload.get("jobs", {}).get("status_message", "")

        if job_status in ("Done", "Succeeded", "succeeded", "done"):
            return payload
        if job_status in ("Failed", "Error", "failed", "error"):
            return {"status": "error", "message": f"Rodin job failed: {payload}"}

        logger.info("Hyper3D task %s status=%s, waiting %ds…", task_uuid, job_status, interval)
        await asyncio.sleep(interval)
        elapsed += interval
        interval = min(interval * 2, 60)

    return {
        "status": "error",
        "message": f"Rodin task {task_uuid} did not complete within {max_wait}s.",
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP, client: Any, *, read_only: bool = False) -> None:
    """Register all Hyper3D tools with the FastMCP server."""

    @mcp.tool(
        name="hyper3d_status",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def hyper3d_status(params: Hyper3DStatusParams) -> dict[str, Any]:
        """Check the Hyper3D plugin status and whether the API key is configured."""
        _ = params  # no fields needed; kept for consistent MCP tool signature
        api_key = _get_api_key()
        return {
            "status": "success",
            "plugin": "hyper3d",
            "version": _PLUGIN_VERSION,
            "api_key_configured": api_key is not None,
            "read_only": read_only,
        }

    @mcp.tool(
        name="hyper3d_generate_text",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def hyper3d_generate_text(params: Hyper3DGenerateTextParams) -> dict[str, Any]:
        """Generate a 3D model from a text prompt using Hyper3D Rodin.

        Returns a task_uuid to track progress with hyper3d_poll or hyper3d_import.
        Requires the HYPER3D_API_KEY environment variable to be set.
        """
        if read_only:
            return {"status": "error", "message": "Cannot generate 3D models in read-only mode."}

        api_key = _get_api_key()
        if not api_key:
            return {
                "status": "error",
                "message": (
                    "HYPER3D_API_KEY is not set. "
                    "Sign up at https://hyper3d.ai and export HYPER3D_API_KEY=<your-key>."
                ),
            }

        body: dict[str, Any] = {
            "prompt": params.prompt,
            "tier": params.tier,
            "mesh_mode": params.mesh_mode,
        }
        if params.seed is not None:
            body["seed"] = params.seed

        async with httpx.AsyncClient() as http_client:
            try:
                resp = await http_client.post(
                    _RODIN_BASE,
                    json=body,
                    headers=_auth_headers(api_key),
                    timeout=30.0,
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return {
                    "status": "success",
                    "task_uuid": data.get("uuid") or data.get("task_uuid"),
                    "subscription_key": data.get("subscription_key"),
                    "raw": data,
                }
            except httpx.HTTPStatusError as exc:
                return {
                    "status": "error",
                    "message": f"Rodin API error {exc.response.status_code}: {exc.response.text}",
                }
            except httpx.HTTPError as exc:
                return {"status": "error", "message": f"HTTP error: {exc}"}

    @mcp.tool(
        name="hyper3d_generate_image",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def hyper3d_generate_image(params: Hyper3DGenerateImageParams) -> dict[str, Any]:
        """Generate a 3D model from a reference image using Hyper3D Rodin.

        Provide either image_url (publicly accessible) or image_path (local file).
        Returns a task_uuid to track progress with hyper3d_poll or hyper3d_import.
        Requires the HYPER3D_API_KEY environment variable to be set.
        """
        if read_only:
            return {"status": "error", "message": "Cannot generate 3D models in read-only mode."}

        if not params.image_url and not params.image_path:
            return {"status": "error", "message": "Provide either image_url or image_path."}

        api_key = _get_api_key()
        if not api_key:
            return {
                "status": "error",
                "message": (
                    "HYPER3D_API_KEY is not set. "
                    "Sign up at https://hyper3d.ai and export HYPER3D_API_KEY=<your-key>."
                ),
            }

        async with httpx.AsyncClient() as http_client:
            try:
                # Gather image bytes
                if params.image_path:
                    image_bytes = Path(params.image_path).read_bytes()
                    filename = Path(params.image_path).name
                else:
                    # params.image_url is guaranteed non-None here
                    img_resp = await http_client.get(params.image_url, timeout=30.0)  # type: ignore[arg-type]
                    img_resp.raise_for_status()
                    image_bytes = img_resp.content
                    filename = (params.image_url or "image").split("/")[-1] or "image.jpg"  # type: ignore[union-attr]

                files = [("images", (filename, image_bytes, "image/jpeg"))]
                data = {
                    "tier": params.tier,
                    "mesh_mode": params.mesh_mode,
                }
                if params.seed is not None:
                    data["seed"] = str(params.seed)

                resp = await http_client.post(
                    _RODIN_BASE,
                    files=files,
                    data=data,
                    headers=_auth_headers(api_key),
                    timeout=60.0,
                )
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return {
                    "status": "success",
                    "task_uuid": result.get("uuid") or result.get("task_uuid"),
                    "subscription_key": result.get("subscription_key"),
                    "raw": result,
                }
            except httpx.HTTPStatusError as exc:
                return {
                    "status": "error",
                    "message": f"Rodin API error {exc.response.status_code}: {exc.response.text}",
                }
            except httpx.HTTPError as exc:
                return {"status": "error", "message": f"HTTP error: {exc}"}
            except OSError as exc:
                return {"status": "error", "message": f"File error: {exc}"}

    @mcp.tool(
        name="hyper3d_poll",
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def hyper3d_poll(params: Hyper3DPollParams) -> dict[str, Any]:
        """Poll the status of a Hyper3D Rodin generation task.

        Uses exponential backoff (5s → 10s → 20s… capped at 60s) up to max_wait seconds.
        Returns the final status payload when the job is done or failed.
        """
        api_key = _get_api_key()
        if not api_key:
            return {
                "status": "error",
                "message": "HYPER3D_API_KEY is not set.",
            }

        async with httpx.AsyncClient() as http_client:
            try:
                result = await _poll_until_done(
                    http_client,
                    params.task_uuid,
                    api_key,
                    params.max_wait,
                )
                return result
            except httpx.HTTPStatusError as exc:
                return {
                    "status": "error",
                    "message": f"Rodin API error {exc.response.status_code}: {exc.response.text}",
                }
            except httpx.HTTPError as exc:
                return {"status": "error", "message": f"HTTP error: {exc}"}

    @mcp.tool(
        name="hyper3d_import",
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    )
    async def hyper3d_import(params: Hyper3DImportParams) -> dict[str, Any]:
        """Poll until done, download the model file, and import it into Blender.

        Downloads the generated 3D model to the local cache then sends an
        import_3d_model command to the connected Blender instance.
        Requires the HYPER3D_API_KEY environment variable to be set.
        """
        if read_only:
            return {"status": "error", "message": "Cannot import models in read-only mode."}

        api_key = _get_api_key()
        if not api_key:
            return {
                "status": "error",
                "message": (
                    "HYPER3D_API_KEY is not set. "
                    "Sign up at https://hyper3d.ai and export HYPER3D_API_KEY=<your-key>."
                ),
            }

        async with httpx.AsyncClient() as http_client:
            try:
                # 1. Poll until the job is done (max 300s default)
                status_payload = await _poll_until_done(
                    http_client,
                    params.task_uuid,
                    api_key,
                    max_wait=300,
                )
                if status_payload.get("status") == "error":
                    return status_payload

                # 2. Locate the download URL in the status payload
                #    Rodin returns download links inside jobs[].model_urls
                download_url: str | None = None
                jobs = status_payload.get("jobs", [])
                if isinstance(jobs, list):
                    for job in jobs:
                        urls = job.get("model_urls", {})
                        download_url = urls.get(params.import_format) or urls.get("glb")
                        if download_url:
                            break
                elif isinstance(jobs, dict):
                    urls = jobs.get("model_urls", {})
                    download_url = urls.get(params.import_format) or urls.get("glb")

                if not download_url:
                    return {
                        "status": "error",
                        "message": (
                            f"No download URL found for format '{params.import_format}' "
                            f"in task {params.task_uuid}. Raw payload: {status_payload}"
                        ),
                    }

                # 3. Download to cache
                cache_dir = _get_cache_dir(params.task_uuid)
                filename = f"model.{params.import_format}"
                filepath = cache_dir / filename

                if not filepath.exists():
                    logger.info("Downloading Rodin model from %s → %s", download_url, filepath)
                    dl_resp = await http_client.get(
                        download_url,
                        headers=_auth_headers(api_key),
                        timeout=120.0,
                    )
                    dl_resp.raise_for_status()
                    filepath.write_bytes(dl_resp.content)
                else:
                    logger.info("Using cached Rodin model at %s", filepath)

            except httpx.HTTPStatusError as exc:
                return {
                    "status": "error",
                    "message": f"Download error {exc.response.status_code}: {exc.response.text}",
                }
            except httpx.HTTPError as exc:
                return {"status": "error", "message": f"HTTP error: {exc}"}

        # 4. Send import command to Blender via the bridge
        try:
            result = await client.send_command(
                "import_3d_model",
                {
                    "file_path": str(filepath),
                    "object_name": params.object_name,
                    "import_format": params.import_format,
                },
                timeout=60.0,
            )
            return result  # type: ignore[return-value]
        except Exception as exc:
            return {"status": "error", "message": f"Blender import error: {exc}"}
