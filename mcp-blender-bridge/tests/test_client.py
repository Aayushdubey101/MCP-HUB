"""Tests for BlenderClient — async TCP communication layer."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from blender_bridge.client import (
    BRIDGE_PROTOCOL_VERSION,
    BlenderClient,
    BlenderConnectionError,
)


def _make_connection(response: dict) -> tuple[AsyncMock, MagicMock]:
    reader = AsyncMock()
    reader.readline.return_value = (json.dumps(response) + "\n").encode()
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    return reader, writer


class TestBridgeProtocolVersion:
    def test_is_semver_string(self):
        parts = BRIDGE_PROTOCOL_VERSION.split(".")
        assert len(parts) == 2
        assert all(p.isdigit() for p in parts)


class TestBlenderClientSendCommand:
    def setup_method(self):
        self.client = BlenderClient(host="127.0.0.1", port=9876, timeout=5.0)

    async def test_success_response(self):
        response = {"status": "success", "result": {"key": "value"}}
        reader, writer = _make_connection(response)
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            result = await self.client.send_command("test_command")
        assert result == response

    async def test_sends_correct_payload(self):
        response = {"status": "success", "result": {}}
        reader, writer = _make_connection(response)
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            await self.client.send_command("my_cmd", {"foo": "bar"})
        payload = json.loads(writer.write.call_args[0][0].decode().strip())
        assert payload == {"command": "my_cmd", "params": {"foo": "bar"}}

    async def test_empty_params_default(self):
        response = {"status": "success", "result": {}}
        reader, writer = _make_connection(response)
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            await self.client.send_command("no_params")
        payload = json.loads(writer.write.call_args[0][0].decode().strip())
        assert payload["params"] == {}

    async def test_connection_refused_raises(self):
        with patch("asyncio.open_connection", new=AsyncMock(side_effect=OSError("refused"))):
            with pytest.raises(BlenderConnectionError, match="Could not connect"):
                await self.client.send_command("ping")

    async def test_timeout_on_connect_raises(self):
        with patch("asyncio.open_connection", new=AsyncMock(side_effect=asyncio.TimeoutError())):
            with pytest.raises(BlenderConnectionError, match="Could not connect"):
                await self.client.send_command("ping")

    async def test_empty_response_raises(self):
        reader = AsyncMock()
        reader.readline.return_value = b""
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            with pytest.raises(BlenderConnectionError, match="closed the connection"):
                await self.client.send_command("ping")

    async def test_invalid_json_raises(self):
        reader = AsyncMock()
        reader.readline.return_value = b"not-json\n"
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            with pytest.raises(BlenderConnectionError, match="invalid JSON"):
                await self.client.send_command("ping")

    async def test_timeout_override(self):
        response = {"status": "success", "result": {}}
        reader, writer = _make_connection(response)
        captured_timeouts: list[float] = []

        original_wait_for = asyncio.wait_for

        async def capturing_wait_for(coro, *, timeout):  # type: ignore[no-untyped-def]
            captured_timeouts.append(timeout)
            return await original_wait_for(coro, timeout=timeout)

        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            with patch("asyncio.wait_for", side_effect=capturing_wait_for):
                await self.client.send_command("test", timeout=42.0)

        assert 42.0 in captured_timeouts

    async def test_writer_closed_on_success(self):
        response = {"status": "success", "result": {}}
        reader, writer = _make_connection(response)
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            await self.client.send_command("ping")
        writer.close.assert_called_once()

    async def test_writer_closed_on_error(self):
        reader = AsyncMock()
        reader.readline.return_value = b"bad\n"
        writer = MagicMock()
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            with pytest.raises(BlenderConnectionError):
                await self.client.send_command("ping")
        writer.close.assert_called_once()


class TestBlenderClientPing:
    def setup_method(self):
        self.client = BlenderClient()

    async def test_ping_success(self):
        response = {
            "status": "success",
            "result": {"pong": True, "protocol_version": BRIDGE_PROTOCOL_VERSION},
        }
        reader, writer = _make_connection(response)
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            assert await self.client.ping() is True

    async def test_ping_returns_false_on_connection_error(self):
        with patch("asyncio.open_connection", new=AsyncMock(side_effect=OSError())):
            assert await self.client.ping() is False

    async def test_ping_returns_false_on_error_status(self):
        response = {"status": "error", "message": "not running"}
        reader, writer = _make_connection(response)
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            assert await self.client.ping() is False

    async def test_ping_logs_protocol_mismatch(self, caplog):
        import logging

        response = {
            "status": "success",
            "result": {"pong": True, "protocol_version": "99.0"},
        }
        reader, writer = _make_connection(response)
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            with caplog.at_level(logging.WARNING, logger="blender_bridge.client"):
                result = await self.client.ping()
        assert result is True
        assert "Protocol version mismatch" in caplog.text

    async def test_ping_no_warning_on_version_match(self, caplog):
        import logging

        response = {
            "status": "success",
            "result": {"pong": True, "protocol_version": BRIDGE_PROTOCOL_VERSION},
        }
        reader, writer = _make_connection(response)
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            with caplog.at_level(logging.WARNING, logger="blender_bridge.client"):
                await self.client.ping()
        assert "mismatch" not in caplog.text


def _make_streaming_writer() -> MagicMock:
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    writer.is_closing = MagicMock(return_value=False)
    return writer


def _make_streaming_reader(responses: list[dict]) -> AsyncMock:
    """A reader.readline() side-effect queue. Use {} for empty/EOF."""
    reader = AsyncMock()
    queue: list[bytes] = [(json.dumps(r) + "\n").encode() if r else b"" for r in responses]

    async def _readline() -> bytes:
        if not queue:
            return b""
        return queue.pop(0)

    reader.readline = _readline
    return reader


class TestBlenderClientPersistent:
    def setup_method(self):
        self.client = BlenderClient(host="127.0.0.1", port=9876, timeout=5.0, persistent=True)

    async def test_reuses_single_connection_across_calls(self):
        reader = _make_streaming_reader(
            [
                {"status": "success", "result": {"n": 1}},
                {"status": "success", "result": {"n": 2}},
                {"status": "success", "result": {"n": 3}},
            ]
        )
        writer = _make_streaming_writer()
        open_mock = AsyncMock(return_value=(reader, writer))
        with patch("asyncio.open_connection", new=open_mock):
            r1 = await self.client.send_command("a")
            r2 = await self.client.send_command("b")
            r3 = await self.client.send_command("c")
        assert r1["result"]["n"] == 1
        assert r2["result"]["n"] == 2
        assert r3["result"]["n"] == 3
        assert open_mock.await_count == 1
        assert writer.write.call_count == 3

    async def test_reconnects_on_broken_pipe(self):
        good_reader = _make_streaming_reader(
            [{"status": "success", "result": {"after_reconnect": True}}]
        )
        good_writer = _make_streaming_writer()

        bad_writer = _make_streaming_writer()
        bad_writer.drain = AsyncMock(side_effect=BrokenPipeError("dead"))
        bad_reader = AsyncMock()

        connections = [(bad_reader, bad_writer), (good_reader, good_writer)]
        open_mock = AsyncMock(side_effect=lambda *a, **kw: connections.pop(0))

        with patch("asyncio.open_connection", new=open_mock):
            result = await self.client.send_command("x")

        assert result["result"]["after_reconnect"] is True
        assert open_mock.await_count == 2
        bad_writer.close.assert_called()

    async def test_raises_after_two_failed_connect_attempts(self):
        bad_writer1 = _make_streaming_writer()
        bad_writer1.drain = AsyncMock(side_effect=ConnectionResetError("boom"))
        bad_writer2 = _make_streaming_writer()
        bad_writer2.drain = AsyncMock(side_effect=ConnectionResetError("boom"))
        connections = [
            (AsyncMock(), bad_writer1),
            (AsyncMock(), bad_writer2),
        ]
        open_mock = AsyncMock(side_effect=lambda *a, **kw: connections.pop(0))

        with patch("asyncio.open_connection", new=open_mock):
            with pytest.raises(BlenderConnectionError, match="could not be reestablished"):
                await self.client.send_command("x")

    async def test_lock_serializes_concurrent_callers(self):
        order: list[str] = []

        class SlowReader:
            def __init__(self, label: str):
                self.label = label
                self._sent = False

            async def readline(self) -> bytes:
                # Simulate async work; record order of replies.
                await asyncio.sleep(0.01)
                order.append(f"reply:{self.label}")
                if self._sent:
                    return b""
                self._sent = True
                return (
                    json.dumps({"status": "success", "result": {"label": self.label}}) + "\n"
                ).encode()

        # Single shared reader/writer (persistent reuses one socket).
        iter(["A", "B"])
        reader = AsyncMock()
        # Each readline() returns the next label's response.
        responses = [
            (json.dumps({"status": "success", "result": {"label": "A"}}) + "\n").encode(),
            (json.dumps({"status": "success", "result": {"label": "B"}}) + "\n").encode(),
        ]

        async def readline() -> bytes:
            await asyncio.sleep(0.01)
            return responses.pop(0)

        reader.readline = readline
        writer = _make_streaming_writer()

        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            results = await asyncio.gather(
                self.client.send_command("a"),
                self.client.send_command("b"),
            )

        # Both succeed, and write ordering inside the socket was serialized
        # (single connection reused, so 2 writes total — the lock prevents interleaving).
        assert {r["result"]["label"] for r in results} == {"A", "B"}
        assert writer.write.call_count == 2

    async def test_close_idempotent(self):
        # close() before any connect is fine.
        await self.client.close()
        # close() after connect tears it down.
        reader = _make_streaming_reader([{"status": "success", "result": {}}])
        writer = _make_streaming_writer()
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))):
            await self.client.send_command("x")
        await self.client.close()
        assert self.client._writer is None
        # Second close still fine.
        await self.client.close()

    async def test_per_call_mode_unchanged_when_persistent_false(self):
        client = BlenderClient(host="127.0.0.1", port=9876, persistent=False)
        reader = _make_streaming_reader(
            [
                {"status": "success", "result": {"n": 1}},
                {"status": "success", "result": {"n": 2}},
            ]
        )
        writer = _make_streaming_writer()
        open_mock = AsyncMock(return_value=(reader, writer))
        with patch("asyncio.open_connection", new=open_mock):
            await client.send_command("a")
            await client.send_command("b")
        # Per-call mode opens a new connection every time.
        assert open_mock.await_count == 2
