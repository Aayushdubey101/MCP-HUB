"""Blender client - communicates with the Blender addon via TCP socket.

This module provides a thin client that sends JSON commands to a running
Blender instance (via the companion Blender addon) and returns the response.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

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
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

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
        t = timeout if timeout is not None else self.timeout
        payload = json.dumps({"command": command, "params": params or {}}) + "\n"

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
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

            # Read response (expects newline-delimited JSON)
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
            raise BlenderConnectionError(
                f"Received invalid JSON from Blender: {e}"
            ) from e
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def ping(self) -> bool:
        """Check whether Blender is reachable. Returns True if reachable."""
        try:
            response = await self.send_command("ping")
            return bool(response.get("status") == "success")
        except BlenderConnectionError:
            return False
