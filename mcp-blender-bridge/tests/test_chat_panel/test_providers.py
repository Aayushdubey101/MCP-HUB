"""Tests for provider implementations — mocked SDKs, verify ChatEvent stream normalization."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_panel.providers.anthropic import AnthropicProvider
from chat_panel.providers.base import (
    Message,
    Stop,
    TextDelta,
    ToolUseArgs,
    ToolUseEnd,
    ToolUseStart,
)
from chat_panel.providers.gemini import GeminiProvider
from chat_panel.providers.openai_compat import OpenAICompatProvider


async def collect(aiter) -> list:
    return [item async for item in aiter]


# ---------------------------------------------------------------------------
# Fake async stream helpers
# ---------------------------------------------------------------------------


class _FakeAnthropicStream:
    """Async context manager + async iterator that mimics anthropic streaming."""

    def __init__(self, events: list, final_msg: object) -> None:
        self._iter = iter(events)
        self._final = final_msg

    async def __aenter__(self) -> "_FakeAnthropicStream":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    def __aiter__(self) -> "_FakeAnthropicStream":
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def get_final_message(self) -> object:
        return self._final


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    def _make_events(self) -> list:
        events = []

        e1 = MagicMock()
        e1.type = "content_block_start"
        e1.content_block = MagicMock(type="text")

        e2 = MagicMock()
        e2.type = "content_block_delta"
        e2.delta = MagicMock(type="text_delta", text="Hello!")

        e3 = MagicMock()
        e3.type = "content_block_start"
        e3.content_block = MagicMock()
        e3.content_block.type = "tool_use"
        e3.content_block.id = "tu_01"
        e3.content_block.name = "blender_ping"

        e4 = MagicMock()
        e4.type = "content_block_delta"
        e4.delta = MagicMock(type="input_json_delta", partial_json="{}")

        e5 = MagicMock()
        e5.type = "content_block_stop"

        e6 = MagicMock()
        e6.type = "message_stop"

        return [e1, e2, e3, e4, e5, e6]

    @pytest.mark.asyncio
    async def test_stream_normalizes_events(self) -> None:
        final_msg = MagicMock()
        final_msg.stop_reason = "end_turn"
        final_msg.usage = MagicMock(input_tokens=10, output_tokens=5)

        fake_stream = _FakeAnthropicStream(self._make_events(), final_msg)

        mock_messages = MagicMock()
        mock_messages.stream = MagicMock(return_value=fake_stream)

        mock_client = MagicMock()
        mock_client.messages = mock_messages

        provider = AnthropicProvider.__new__(AnthropicProvider)
        provider._client = mock_client

        events = await collect(
            provider.chat(
                messages=[Message(role="user", content=[{"type": "text", "text": "hi"}])],
                tools=[],
                model="claude-opus-4-7",
            )
        )

        text_ev = [e for e in events if isinstance(e, TextDelta)]
        tool_start = [e for e in events if isinstance(e, ToolUseStart)]
        tool_args = [e for e in events if isinstance(e, ToolUseArgs)]
        tool_end = [e for e in events if isinstance(e, ToolUseEnd)]
        stop_ev = [e for e in events if isinstance(e, Stop)]

        assert len(text_ev) == 1
        assert text_ev[0].text == "Hello!"
        assert len(tool_start) == 1
        assert tool_start[0].id == "tu_01"
        assert tool_start[0].name == "blender_ping"
        assert len(tool_args) == 1
        assert tool_args[0].partial_json == "{}"
        assert len(tool_end) == 1
        assert tool_end[0].id == "tu_01"
        assert len(stop_ev) == 1
        assert stop_ev[0].reason == "end_turn"

    def test_make_tool_result_message(self) -> None:
        msg = AnthropicProvider.make_tool_result_message("tu_01", '{"status":"success"}')
        assert msg.role == "user"
        assert msg.content[0]["type"] == "tool_result"
        assert msg.content[0]["tool_use_id"] == "tu_01"


# ---------------------------------------------------------------------------
# OpenAICompatProvider
# ---------------------------------------------------------------------------


class TestOpenAICompatProvider:
    def _make_chunks(self) -> list:
        # Chunk 1: text delta
        c1 = MagicMock()
        c1.choices = [MagicMock()]
        c1.choices[0].delta = MagicMock(content="Hi there", tool_calls=None)
        c1.choices[0].finish_reason = None

        # Chunk 2: tool call start
        tc1 = MagicMock()
        tc1.index = 0
        tc1.id = "call_abc"
        tc1.function = MagicMock()
        tc1.function.name = "blender_ping"
        tc1.function.arguments = ""

        c2 = MagicMock()
        c2.choices = [MagicMock()]
        c2.choices[0].delta = MagicMock(content=None, tool_calls=[tc1])
        c2.choices[0].finish_reason = None

        # Chunk 3: tool args + finish
        tc2 = MagicMock()
        tc2.index = 0
        tc2.id = None
        tc2.function = MagicMock()
        tc2.function.name = None
        tc2.function.arguments = "{}"

        c3 = MagicMock()
        c3.choices = [MagicMock()]
        c3.choices[0].delta = MagicMock(content=None, tool_calls=[tc2])
        c3.choices[0].finish_reason = "tool_calls"

        return [c1, c2, c3]

    @pytest.mark.asyncio
    async def test_stream_text_and_tool(self) -> None:
        chunks = self._make_chunks()

        async def fake_stream():
            for c in chunks:
                yield c

        mock_completions = MagicMock()
        mock_completions.create = AsyncMock(return_value=fake_stream())

        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = mock_completions

        provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
        provider._client = mock_client

        events = await collect(
            provider.chat(
                messages=[Message(role="user", content=[])],
                tools=[],
                model="gpt-4o",
            )
        )

        assert any(isinstance(e, TextDelta) and e.text == "Hi there" for e in events)
        assert any(isinstance(e, ToolUseStart) and e.name == "blender_ping" for e in events)
        assert any(isinstance(e, ToolUseEnd) for e in events)
        stop = next(e for e in events if isinstance(e, Stop))
        assert stop.reason == "tool_use"


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------


class TestGeminiProvider:
    def test_make_tool_result_message(self) -> None:
        msg = GeminiProvider.make_tool_result_message("blender_ping", '{"status":"success"}')
        assert msg.role == "tool"
        assert msg.content[0]["name"] == "blender_ping"
