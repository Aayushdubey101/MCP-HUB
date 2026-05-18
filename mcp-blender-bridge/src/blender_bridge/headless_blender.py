"""Headless Blender process management.

Provides helpers to locate a Blender executable and launch it in
``--background`` mode with the MCP addon auto-loaded.

Usage::

    uv run mcp-blender-bridge --launch-blender
    uv run mcp-blender-bridge --launch-blender --blender-path /opt/blender/blender
    uv run mcp-blender-bridge --launch-blender --blender-addon-port 9876

The server will:
1. Discover the Blender executable (from ``--blender-path``, then
   ``BLENDER_PATH`` env var, then common install locations).
2. Launch ``blender --background --python <bootstrap_script>`` as a
   subprocess, passing the addon path and bridge port as arguments.
3. Wait up to ``BLENDER_LAUNCH_TIMEOUT`` seconds for the addon to begin
   listening on the expected TCP port.
4. Start the normal MCP server. When the MCP process exits, the Blender
   subprocess is terminated cleanly.

This is primarily useful for automated pipelines, render-farm agents, and
CI-based Blender automation where no GUI is required.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
import textwrap
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# How long (seconds) to wait for Blender to start listening before giving up
BLENDER_LAUNCH_TIMEOUT = float(os.getenv("BLENDER_LAUNCH_TIMEOUT", "30"))

# Common install locations searched when BLENDER_PATH is not set
_CANDIDATE_PATHS_WINDOWS = [
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 3.5\blender.exe",
]
_CANDIDATE_PATHS_UNIX = [
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/snap/bin/blender",
    "/Applications/Blender.app/Contents/MacOS/Blender",
]


def find_blender(explicit_path: Optional[str] = None) -> Path:
    """Return the path to the Blender executable.

    Search order:
    1. *explicit_path* argument (from ``--blender-path`` CLI flag)
    2. ``BLENDER_PATH`` environment variable
    3. Platform-specific common install directories
    4. ``blender`` on ``$PATH``

    Raises ``FileNotFoundError`` if nothing is found.
    """
    candidates: list[str] = []

    if explicit_path:
        candidates.append(explicit_path)

    env_path = os.getenv("BLENDER_PATH")
    if env_path:
        candidates.append(env_path)

    if sys.platform == "win32":
        candidates.extend(_CANDIDATE_PATHS_WINDOWS)
    else:
        candidates.extend(_CANDIDATE_PATHS_UNIX)

    for candidate in candidates:
        p = Path(candidate)
        if p.is_file():
            return p

    # Last resort: check PATH
    import shutil

    found = shutil.which("blender")
    if found:
        return Path(found)

    raise FileNotFoundError(
        "Could not locate the Blender executable. "
        "Set BLENDER_PATH or pass --blender-path <path>."
    )


def _addon_path() -> Path:
    """Return the path to the bundled Blender addon script."""
    # The addon lives at mcp-blender-bridge/blender_addon/mcp_blender_bridge.py
    # When installed as a package the source root is not guaranteed to be on disk,
    # but for local `uv run` / editable installs it will be.
    here = Path(__file__).parent
    candidate = here.parent.parent / "blender_addon" / "mcp_blender_bridge.py"
    if candidate.exists():
        return candidate

    # Fallback: look relative to CWD (useful when running directly from repo root)
    cwd_candidate = Path.cwd() / "blender_addon" / "mcp_blender_bridge.py"
    if cwd_candidate.exists():
        return cwd_candidate

    raise FileNotFoundError(
        f"Could not find blender_addon/mcp_blender_bridge.py "
        f"(searched {candidate} and {cwd_candidate})"
    )


def _make_bootstrap_script(addon_path: Path, bridge_port: int) -> str:
    """Return a Python script that Blender will execute on startup to enable the addon."""
    return textwrap.dedent(
        f"""\
        import bpy
        import sys

        # Load the addon from the source tree (not from Blender's user prefs)
        addon_path = r\"{addon_path}\"
        if addon_path not in sys.path:
            sys.path.insert(0, str(__import__("pathlib").Path(addon_path).parent))

        bpy.ops.preferences.addon_install(filepath=addon_path, overwrite=True)
        bpy.ops.preferences.addon_enable(module="mcp_blender_bridge")

        # Configure the port if the addon supports it
        try:
            prefs = bpy.context.preferences.addons["mcp_blender_bridge"].preferences
            prefs.port = {bridge_port}
        except Exception:
            pass

        # Start the bridge server
        bpy.ops.mcp_bridge.start_server()
        print("[MCP Bootstrap] Bridge started on port {bridge_port}")
        """
    )


async def _wait_for_port(host: str, port: int, timeout: float) -> bool:
    """Return True when a TCP listener is detected on *host*:*port* within *timeout* seconds."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=1.0,
            )
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
            return True
        except (OSError, asyncio.TimeoutError):
            await asyncio.sleep(1.0)
    return False


async def launch_blender(
    blender_path: Optional[str],
    bridge_host: str,
    bridge_port: int,
) -> asyncio.subprocess.Process:
    """Launch Blender in ``--background`` mode with the MCP addon loaded.

    Waits up to ``BLENDER_LAUNCH_TIMEOUT`` seconds for the addon to start
    listening on *bridge_port*.

    Returns the running ``asyncio.Process`` so the caller can await or
    terminate it later.

    Raises:
        FileNotFoundError: If the Blender executable or addon cannot be found.
        RuntimeError: If Blender starts but the addon never opens the port.
    """
    blender_exe = find_blender(blender_path)
    addon = _addon_path()
    bootstrap_src = _make_bootstrap_script(addon, bridge_port)

    # Write bootstrap script to a temp file (Blender --python requires a file path)
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="mcp_bridge_bootstrap_"
    ) as tf:
        tf.write(bootstrap_src)
        bootstrap_file = tf.name

    cmd = [
        str(blender_exe),
        "--background",
        "--python",
        bootstrap_file,
    ]

    logger.info("Launching Blender: %s", " ".join(cmd))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    logger.info("Blender PID=%d — waiting up to %.0fs for addon port %d …",
                process.pid, BLENDER_LAUNCH_TIMEOUT, bridge_port)

    ready = await _wait_for_port(bridge_host, bridge_port, BLENDER_LAUNCH_TIMEOUT)
    if not ready:
        process.terminate()
        raise RuntimeError(
            f"Blender started (PID={process.pid}) but the MCP addon never "
            f"opened port {bridge_port} within {BLENDER_LAUNCH_TIMEOUT}s. "
            "Check Blender's console for errors."
        )

    logger.info("Blender addon ready on %s:%d.", bridge_host, bridge_port)
    return process
