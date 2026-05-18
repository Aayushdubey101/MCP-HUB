"""Tests for the SHA-256 asset cache module (Phase 8)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from blender_bridge.asset_cache import (
    content_hash,
    get_plugin_cache_dir,
    prune_sha256_cache,
    sha256_cache_path,
    store_in_sha256_cache,
)


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self) -> None:
        data = b"hello world"
        assert content_hash(data) == content_hash(data)

    def test_different_data_different_hash(self) -> None:
        assert content_hash(b"a") != content_hash(b"b")

    def test_returns_hex_string(self) -> None:
        h = content_hash(b"test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# get_plugin_cache_dir
# ---------------------------------------------------------------------------


class TestGetPluginCacheDir:
    def test_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        d = get_plugin_cache_dir("myplugin", "uid-001")
        assert d.exists()
        assert d.is_dir()
        assert d == tmp_path / "myplugin" / "uid-001"

    def test_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        d1 = get_plugin_cache_dir("plugin", "uid")
        d2 = get_plugin_cache_dir("plugin", "uid")
        assert d1 == d2


# ---------------------------------------------------------------------------
# sha256_cache_path + store_in_sha256_cache
# ---------------------------------------------------------------------------


class TestSha256Cache:
    def test_miss_returns_none_before_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        data = b"new content nobody stored yet"
        result = sha256_cache_path(data, "model.glb")
        assert result is None

    def test_hit_after_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        data = b"GLB binary content"
        stored = store_in_sha256_cache(data, "model.glb")
        assert stored.exists()
        assert stored.read_bytes() == data

        hit = sha256_cache_path(data, "model.glb")
        assert hit is not None
        assert hit == stored

    def test_store_idempotent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        data = b"repeated content"
        p1 = store_in_sha256_cache(data, "file.glb")
        mtime_before = p1.stat().st_mtime
        p2 = store_in_sha256_cache(data, "file.glb")
        assert p1 == p2
        # File should not have been rewritten
        assert p2.stat().st_mtime == mtime_before

    def test_different_filenames_separate_entries_same_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        data = b"same bytes"
        p1 = store_in_sha256_cache(data, "model.glb")
        p2 = store_in_sha256_cache(data, "model.obj")
        # Same hash dir but different filenames
        assert p1.parent == p2.parent
        assert p1 != p2

    def test_different_content_different_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        p1 = store_in_sha256_cache(b"content A", "f.glb")
        p2 = store_in_sha256_cache(b"content B", "f.glb")
        assert p1.parent != p2.parent


# ---------------------------------------------------------------------------
# prune_sha256_cache
# ---------------------------------------------------------------------------


class TestPruneSha256Cache:
    @pytest.mark.asyncio
    async def test_prune_removes_old_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))

        # Store an entry
        stored = store_in_sha256_cache(b"old content", "old.glb")

        # Backdate its mtime by 40 days
        old_time = time.time() - 40 * 86_400
        import os

        os.utime(stored, (old_time, old_time))

        removed = await prune_sha256_cache(max_age_days=30)
        assert removed == 1
        assert not stored.parent.exists()

    @pytest.mark.asyncio
    async def test_prune_keeps_fresh_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        stored = store_in_sha256_cache(b"fresh content", "fresh.glb")

        removed = await prune_sha256_cache(max_age_days=30)
        assert removed == 0
        assert stored.exists()

    @pytest.mark.asyncio
    async def test_prune_empty_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        # Create an empty dir inside sha256/
        sha_dir = tmp_path / "sha256"
        sha_dir.mkdir(parents=True)
        (sha_dir / "emptyhashdir").mkdir()

        removed = await prune_sha256_cache(max_age_days=30)
        assert removed == 1

    @pytest.mark.asyncio
    async def test_prune_no_entries_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BLENDER_BRIDGE_CACHE_DIR", str(tmp_path))
        removed = await prune_sha256_cache(max_age_days=30)
        assert removed == 0
