"""Blender client - communicates with the Blender addon via TCP socket.

This module provides a thin client that sends JSON commands to a running
Blender instance (via the companion Blender addon) and returns the response.

Two modes:

* **Per-call (default)** — open a new TCP connection for every command and
  close it immediately. Simple, robust, slightly slower for chatty workloads.
* **Persistent** — open one connection on first use and reuse it for all
  subsequent commands. Faster (no TCP handshake per call) and matches the
  way modern MCP clients tend to drive the bridge. Reconnects automatically
  on broken pipe / reset, and serializes concurrent callers with a lock.

Mode is selected via ``BlenderClient(persistent=True)`` or the
``BLENDER_BRIDGE_PERSISTENT`` environment variable read in ``server.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

BRIDGE_PROTOCOL_VERSION = "1.0"

# Default connection settings (overridable via environment variables / config)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9876
DEFAULT_TIMEOUT = 30.0  # seconds


class BlenderConnectionError(Exception):
    """Raised when we cannot connect to or communicate with Blender."""


class BlenderClient:
    """Async TCP client for the Blender bridge addon.

    The companion Blender addon listens on a TCP socket and accepts
    newline-delimited JSON commands of the form:

        {"command": "<name>", "params": {...}}

    and returns:

        {"status": "success", "result": ...}
        {"status": "error", "message": "..."}
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        *,
        persistent: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.persistent = persistent

        # Persistent-mode state. Unused when persistent=False.
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Open the persistent connection. No-op in per-call mode or if already open."""
        if not self.persistent:
            return
        if self._writer is not None and not self._writer.is_closing():
            return
        await self._open()

    async def close(self) -> None:
        """Close the persistent connection if one is open."""
        await self._teardown()

    async def _open(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, limit=64 * 1024 * 1024),
                timeout=self.timeout,
            )
        except (OSError, asyncio.TimeoutError) as e:
            self._reader = None
            self._writer = None
            raise BlenderConnectionError(
                f"Could not connect to Blender at {self.host}:{self.port}. "
                f"Make sure Blender is running and the MCP-Blender-Bridge addon is "
                f"enabled and started. Original error: {e}"
            ) from e

    async def _teardown(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        with contextlib.suppress(Exception):
            writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    async def send_command(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a command to Blender and return the parsed response.

        Args:
            command: The command name registered in the Blender addon.
            params: Optional parameters dict for the command.
            timeout: Override the instance default timeout for this call only.
                Useful for long-running operations like rendering.

        Returns:
            The parsed JSON response from Blender as a dict.

        Raises:
            BlenderConnectionError: If we cannot reach Blender or it returns an error.
        """
        if self.persistent:
            return await self._send_persistent(command, params, timeout=timeout)
        return await self._send_per_call(command, params, timeout=timeout)

    async def _send_per_call(
        self,
        command: str,
        params: dict[str, Any] | None,
        *,
        timeout: float | None,
    ) -> dict[str, Any]:
        t = timeout if timeout is not None else self.timeout
        payload = json.dumps({"command": command, "params": params or {}}) + "\n"

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port, limit=64 * 1024 * 1024),
                timeout=t,
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise BlenderConnectionError(
                f"Could not connect to Blender at {self.host}:{self.port}. "
                f"Make sure Blender is running and the MCP-Blender-Bridge addon is "
                f"enabled and started. Original error: {e}"
            ) from e

        try:
            writer.write(payload.encode("utf-8"))
            await writer.drain()

            raw = await asyncio.wait_for(reader.readline(), timeout=t)

            if not raw:
                raise BlenderConnectionError(
                    "Blender closed the connection without sending a response."
                )

            response: dict[str, Any] = json.loads(raw.decode("utf-8").strip())
            return response
        except asyncio.TimeoutError as e:
            raise BlenderConnectionError(
                f"Blender did not respond within {t}s. "
                "For renders, increase timeout_seconds in the tool parameters."
            ) from e
        except json.JSONDecodeError as e:
            raise BlenderConnectionError(f"Received invalid JSON from Blender: {e}") from e
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _send_persistent(
        self,
        command: str,
        params: dict[str, Any] | None,
        *,
        timeout: float | None,
    ) -> dict[str, Any]:
        t = timeout if timeout is not None else self.timeout
        payload = json.dumps({"command": command, "params": params or {}}) + "\n"
        encoded = payload.encode("utf-8")

        async with self._lock:
            for attempt in (0, 1):
                if self._writer is None or self._writer.is_closing():
                    await self._open()

                assert self._reader is not None and self._writer is not None

                try:
                    self._writer.write(encoded)
                    await asyncio.wait_for(self._writer.drain(), timeout=t)
                    raw = await asyncio.wait_for(self._reader.readline(), timeout=t)
                except (ConnectionResetError, BrokenPipeError, OSError) as e:
                    logger.warning(
                        "Persistent connection lost (%s) — reconnecting (attempt %d).",
                        e,
                        attempt + 1,
                    )
                    await self._teardown()
                    if attempt == 0:
                        continue
                    raise BlenderConnectionError(
                        f"Persistent connection to Blender at {self.host}:{self.port} "
                        f"was lost and could not be reestablished. Original error: {e}"
                    ) from e
                except asyncio.TimeoutError as e:
                    await self._teardown()
                    raise BlenderConnectionError(
                        f"Blender did not respond within {t}s. "
                        "For renders, increase timeout_seconds in the tool parameters."
                    ) from e

                if not raw:
                    await self._teardown()
                    if attempt == 0:
                        continue
                    raise BlenderConnectionError(
                        "Blender closed the connection without sending a response."
                    )

                try:
                    response: dict[str, Any] = json.loads(raw.decode("utf-8").strip())
                except json.JSONDecodeError as e:
                    await self._teardown()
                    raise BlenderConnectionError(f"Received invalid JSON from Blender: {e}") from e

                return response

            raise BlenderConnectionError(
                "Unreachable: persistent send loop exited without response."
            )

    async def ping(self) -> bool:
        """Check whether Blender is reachable. Returns True if reachable."""
        try:
            response = await self.send_command("ping")
            if response.get("status") != "success":
                return False
            result = response.get("result", {})
            addon_protocol = result.get("protocol_version") if isinstance(result, dict) else None
            if addon_protocol and addon_protocol != BRIDGE_PROTOCOL_VERSION:
                logger.warning(
                    "Protocol version mismatch: server=%r addon=%r — "
                    "update blender_addon/mcp_blender_bridge.py to match.",
                    BRIDGE_PROTOCOL_VERSION,
                    addon_protocol,
                )
            return True
        except BlenderConnectionError:
            return False
