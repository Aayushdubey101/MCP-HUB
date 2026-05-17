"""Asset cache management with SHA-256 keyed entries and stale pruning.

Shared across all plugins. Provides a deterministic, content-addressable
cache directory structure:

    <BLENDER_BRIDGE_CACHE_DIR>/
        sha256/
            <sha256-hex>/       ← one entry per unique content hash
                <filename>
        <plugin-name>/
            <uid>/              ← raw plugin cache (kept for backward compat)
                <filename>

On each call to ``get_cache_dir()`` the ``sha256/`` tree is lightly pruned:
entries whose underlying file is older than ``max_age_days`` are removed.
The prune scan is O(n) in cache entries and runs in a thread to avoid blocking
the event loop.

Usage (plugin code example)::

    from blender_bridge.asset_cache import get_plugin_cache_dir, sha256_cache_path

    cache_dir = get_plugin_cache_dir("hyper3d", "task-uuid-001")
    # → ~/.cache/mcp-blender-bridge/assets/hyper3d/task-uuid-001/

    sha_path = sha256_cache_path(data_bytes, filename="model.glb")
    if sha_path is None:
        # Not in SHA cache yet — download and store
        sha_path = store_in_sha256_cache(data_bytes, filename="model.glb")
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_BASE = str(
    Path.home() / ".cache" / "mcp-blender-bridge" / "assets"
)
_MAX_AGE_DAYS = 30  # default: prune entries older than this


def _cache_base() -> Path:
    """Return the root cache directory, honouring BLENDER_BRIDGE_CACHE_DIR."""
    return Path(os.environ.get("BLENDER_BRIDGE_CACHE_DIR", _DEFAULT_CACHE_BASE))


def get_plugin_cache_dir(plugin_name: str, uid: str) -> Path:
    """Return (and create) the per-plugin, per-uid cache directory."""
    path = _cache_base() / plugin_name / uid
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha256_dir() -> Path:
    """Return the root SHA-256 cache directory."""
    d = _cache_base() / "sha256"
    d.mkdir(parents=True, exist_ok=True)
    return d


def content_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def sha256_cache_path(data: bytes, filename: str) -> Optional[Path]:
    """Return the cached file path if *data* is already in the SHA-256 cache.

    Returns ``None`` if the content has never been stored.
    """
    digest = content_hash(data)
    candidate = _sha256_dir() / digest / filename
    if candidate.exists():
        return candidate
    return None


def store_in_sha256_cache(data: bytes, filename: str) -> Path:
    """Write *data* to the SHA-256 cache and return the path.

    If the entry already exists it is left untouched (idempotent).
    """
    digest = content_hash(data)
    entry_dir = _sha256_dir() / digest
    entry_dir.mkdir(parents=True, exist_ok=True)
    dest = entry_dir / filename
    if not dest.exists():
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.rename(dest)
        logger.debug("SHA256 cache STORE %s → %s", digest[:8], dest)
    else:
        logger.debug("SHA256 cache HIT   %s → %s", digest[:8], dest)
    return dest


def _prune_sha256_cache_sync(max_age_days: int = _MAX_AGE_DAYS) -> int:
    """Remove SHA-256 cache entries older than *max_age_days*.

    Returns the number of entries removed. Called synchronously inside a thread.
    """
    import time

    cutoff = time.time() - max_age_days * 86_400
    sha_dir = _sha256_dir()
    removed = 0

    for entry in sha_dir.iterdir():
        if not entry.is_dir():
            continue
        # Check the mtime of any file inside the entry directory
        files = list(entry.iterdir())
        if not files:
            # Empty dir — remove it
            try:
                entry.rmdir()
                removed += 1
            except OSError:
                pass
            continue

        oldest_mtime = min(f.stat().st_mtime for f in files if f.is_file())
        if oldest_mtime < cutoff:
            try:
                shutil.rmtree(entry, ignore_errors=True)
                logger.info(
                    "SHA256 cache PRUNE %s (%.0f days old)",
                    entry.name[:8],
                    (time.time() - oldest_mtime) / 86_400,
                )
                removed += 1
            except OSError as exc:
                logger.warning("SHA256 cache prune failed for %s: %s", entry, exc)

    return removed


async def prune_sha256_cache(max_age_days: int = _MAX_AGE_DAYS) -> int:
    """Async wrapper: prune stale SHA-256 cache entries in a thread.

    Returns the number of entries removed.
    """
    return await asyncio.to_thread(_prune_sha256_cache_sync, max_age_days)
