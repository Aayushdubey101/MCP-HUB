"""Tests for the headless Blender launcher (Phase 9).

We can't run a real Blender binary in CI, so we test all the logic that
doesn't require the actual executable:
- find_blender: explicit path, env var, PATH fallback, not-found error
- _addon_path: path resolution
- _make_bootstrap_script: output structure
- _wait_for_port: mock TCP server
- launch_blender: mock subprocess + port-wait integration
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blender_bridge.headless_blender import (
    BLENDER_LAUNCH_TIMEOUT,
    _make_bootstrap_script,
    _wait_for_port,
    find_blender,
)


# ---------------------------------------------------------------------------
# find_blender
# ---------------------------------------------------------------------------


class TestFindBlender:
    def test_explicit_path_wins(self, tmp_path: Path) -> None:
        exe = tmp_path / "blender.exe"
        exe.touch()
        result = find_blender(str(exe))
        assert result == exe

    def test_env_var_used_when_no_explicit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exe = tmp_path / "blender"
        exe.touch()
        monkeypatch.setenv("BLENDER_PATH", str(exe))
        # No explicit path → should pick up env var
        monkeypatch.delenv("BLENDER_PATH", raising=False)
        monkeypatch.setenv("BLENDER_PATH", str(exe))
        result = find_blender(None)
        assert result == exe

    def test_not_found_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BLENDER_PATH", raising=False)
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="Could not locate"):
                find_blender(None)

    def test_path_shutil_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exe = tmp_path / "blender"
        exe.touch()
        monkeypatch.delenv("BLENDER_PATH", raising=False)
        with patch("shutil.which", return_value=str(exe)):
            result = find_blender(None)
        assert result == exe

    def test_explicit_path_not_file_falls_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BLENDER_PATH", raising=False)
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError):
                # Passing a path that doesn't exist as file
                find_blender(str(tmp_path / "nonexistent.exe"))


# ---------------------------------------------------------------------------
# _make_bootstrap_script
# ---------------------------------------------------------------------------


class TestMakeBootstrapScript:
    def test_contains_addon_path(self, tmp_path: Path) -> None:
        addon = tmp_path / "mcp_blender_bridge.py"
        script = _make_bootstrap_script(addon, 9876)
        assert str(addon) in script

    def test_contains_port(self, tmp_path: Path) -> None:
        addon = tmp_path / "mcp_blender_bridge.py"
        script = _make_bootstrap_script(addon, 12345)
        assert "12345" in script

    def test_contains_start_server_call(self, tmp_path: Path) -> None:
        addon = tmp_path / "mcp_blender_bridge.py"
        script = _make_bootstrap_script(addon, 9876)
        assert "start_server" in script

    def test_is_valid_python_syntax(self, tmp_path: Path) -> None:
        import ast

        addon = tmp_path / "mcp_blender_bridge.py"
        script = _make_bootstrap_script(addon, 9876)
        # Should not raise
        ast.parse(script)


# ---------------------------------------------------------------------------
# _wait_for_port
# ---------------------------------------------------------------------------


class TestWaitForPort:
    @pytest.mark.asyncio
    async def test_returns_true_when_port_opens(self) -> None:
        """Start a dummy TCP server, then verify _wait_for_port detects it."""
        server = await asyncio.start_server(
            lambda r, w: w.close(), "127.0.0.1", 0
        )
        addr = server.sockets[0].getsockname()
        host, port = addr[0], addr[1]

        try:
            result = await _wait_for_port(host, port, timeout=5.0)
            assert result is True
        finally:
            server.close()
            await server.wait_closed()

    @pytest.mark.asyncio
    async def test_returns_false_when_nothing_listens(self) -> None:
        # Port 1 is almost certainly closed and unprivileged-inaccessible
        # Use a very short timeout to keep the test fast
        result = await _wait_for_port("127.0.0.1", 1, timeout=0.5)
        assert result is False


# ---------------------------------------------------------------------------
# launch_blender (mocked subprocess)
# ---------------------------------------------------------------------------


class TestLaunchBlender:
    @pytest.mark.asyncio
    async def test_raises_if_blender_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BLENDER_PATH", raising=False)
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError):
                from blender_bridge.headless_blender import launch_blender

                await launch_blender(None, "127.0.0.1", 9876)

    @pytest.mark.asyncio
    async def test_raises_runtime_error_if_port_never_opens(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If Blender starts but addon never listens, raise RuntimeError."""
        exe = tmp_path / "blender"
        exe.touch()
        addon = tmp_path / "mcp_blender_bridge.py"
        addon.touch()

        fake_proc = MagicMock()
        fake_proc.pid = 9999
        fake_proc.terminate = MagicMock()

        with (
            patch("blender_bridge.headless_blender.find_blender", return_value=exe),
            patch("blender_bridge.headless_blender._addon_path", return_value=addon),
            patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=fake_proc),
            ),
            patch(
                "blender_bridge.headless_blender._wait_for_port",
                new=AsyncMock(return_value=False),
            ),
        ):
            from blender_bridge.headless_blender import launch_blender

            with pytest.raises(RuntimeError, match="never.*opened port"):
                await launch_blender(str(exe), "127.0.0.1", 9876)

        fake_proc.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_process_when_port_opens(
        self, tmp_path: Path
    ) -> None:
        """Happy path: process returned when addon port opens."""
        exe = tmp_path / "blender"
        exe.touch()
        addon = tmp_path / "mcp_blender_bridge.py"
        addon.touch()

        fake_proc = MagicMock()
        fake_proc.pid = 1234

        with (
            patch("blender_bridge.headless_blender.find_blender", return_value=exe),
            patch("blender_bridge.headless_blender._addon_path", return_value=addon),
            patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=fake_proc),
            ),
            patch(
                "blender_bridge.headless_blender._wait_for_port",
                new=AsyncMock(return_value=True),
            ),
        ):
            from blender_bridge.headless_blender import launch_blender

            proc = await launch_blender(str(exe), "127.0.0.1", 9876)
            assert proc is fake_proc
