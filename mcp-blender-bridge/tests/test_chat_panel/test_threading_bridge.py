"""Tests for threading_bridge.py — verify queue discipline and no bpy access from worker."""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from chat_panel.providers.base import Message, Stop, TextDelta, ToolSpec, ToolUseArgs, ToolUseEnd, ToolUseStart
from chat_panel import threading_bridge as tb


# ---------------------------------------------------------------------------
# Provider stubs
# ---------------------------------------------------------------------------


class TextOnlyProvider:
    """Streams two text deltas then stops."""

    async def chat(self, messages, tools, model, system=None):
        yield TextDelta(text="Hello ")
        yield TextDelta(text="world")
        yield Stop(reason="end_turn", usage=None)


class ToolUseProvider:
    """Streams one tool call then stops."""

    def __init__(self, tool_result_fn):
        self._fn = tool_result_fn

    async def chat(self, messages, tools, model, system=None):
        yield ToolUseStart(id="tc_01", name="blender_ping")
        yield ToolUseArgs(id="tc_01", partial_json="{}")
        yield ToolUseEnd(id="tc_01")
        # Second iteration (with tool result in messages) → text + stop
        if any(m.role == "tool" for m in messages):
            yield TextDelta(text="done")
            yield Stop(reason="end_turn", usage=None)
        else:
            # First call — stop with tool_use reason so outer loop continues
            yield Stop(reason="tool_use", usage=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_queues() -> None:
    for q in (tb._text_q, tb._tool_q, tb._response_q, tb._stop_q):
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break


def _drain_tick_no_bpy(state=None) -> None:
    """Simulate _main_thread_tick without bpy."""
    while True:
        try:
            text = tb._text_q.get_nowait()
            if state and hasattr(state, "history") and state.history:
                state.history[-1]["content"] += text
        except queue.Empty:
            break

    while True:
        try:
            call = tb._tool_q.get_nowait()
            result = '{"result":"ok"}'
            tb._response_q.put(result)
        except queue.Empty:
            break

    while True:
        try:
            stop = tb._stop_q.get_nowait()
            if state:
                state.is_streaming = False
            del stop
        except queue.Empty:
            break


# ---------------------------------------------------------------------------
# Test 1: Worker never imports bpy
# ---------------------------------------------------------------------------


def test_worker_never_imports_bpy():
    """Worker thread must not access bpy module."""
    _reset_queues()

    imported_in_worker = []

    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def tracking_import(name, *args, **kwargs):
        if name == "bpy" and threading.current_thread() is not threading.main_thread():
            imported_in_worker.append(name)
        return original_import(name, *args, **kwargs)

    provider = TextOnlyProvider()
    messages = [Message(role="user", content=[{"type": "text", "text": "hi"}])]
    tools: list[ToolSpec] = []

    with patch("builtins.__import__", side_effect=tracking_import):
        thread = threading.Thread(
            target=tb._worker,
            args=(messages, tools, provider, "test-model", None),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=5)

    assert not imported_in_worker, f"bpy was imported from worker thread: {imported_in_worker}"


# ---------------------------------------------------------------------------
# Test 2: Text deltas arrive on _text_q in order
# ---------------------------------------------------------------------------


def test_text_deltas_on_queue_in_order():
    _reset_queues()

    provider = TextOnlyProvider()
    messages = [Message(role="user", content=[{"type": "text", "text": "hi"}])]

    thread = threading.Thread(
        target=tb._worker,
        args=(messages, [], provider, "m", None),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=5)

    collected = []
    while True:
        try:
            collected.append(tb._text_q.get_nowait())
        except queue.Empty:
            break

    assert collected == ["Hello ", "world"]

    stop = tb._stop_q.get_nowait()
    assert stop.reason == "end_turn"


# ---------------------------------------------------------------------------
# Test 3: Tool calls go via _tool_q, not executed directly in worker
# ---------------------------------------------------------------------------


def test_tool_calls_go_through_queue():
    _reset_queues()

    tool_executed_in = []

    class SpyProvider:
        async def chat(self, messages, tools, model, system=None):
            if not any(m.role == "tool" for m in messages):
                yield ToolUseStart(id="tc_01", name="blender_ping")
                yield ToolUseArgs(id="tc_01", partial_json="{}")
                yield ToolUseEnd(id="tc_01")
                yield Stop(reason="tool_use", usage=None)
            else:
                yield Stop(reason="end_turn", usage=None)

    provider = SpyProvider()
    messages = [Message(role="user", content=[{"type": "text", "text": "hi"}])]

    # Pre-load a response so the worker doesn't block forever
    tb._response_q.put('{"result":"ok"}')

    thread = threading.Thread(
        target=tb._worker,
        args=(messages, [], provider, "m", None),
        daemon=True,
    )
    thread.start()

    # Give worker time to push the tool call then wait for the response
    deadline = time.time() + 5
    while tb._tool_q.empty() and time.time() < deadline:
        time.sleep(0.01)

    call = tb._tool_q.get_nowait()
    assert call.name == "blender_ping"
    assert call.id == "tc_01"

    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Test 4: Text accumulates without race conditions (multiple deltas)
# ---------------------------------------------------------------------------


def test_text_accumulates_correctly():
    _reset_queues()

    class MultiTextProvider:
        async def chat(self, messages, tools, model, system=None):
            for ch in list("abcde"):
                yield TextDelta(text=ch)
            yield Stop(reason="end_turn", usage=None)

    provider = MultiTextProvider()
    thread = threading.Thread(
        target=tb._worker,
        args=([Message(role="user", content=[])], [], provider, "m", None),
        daemon=True,
    )
    thread.start()
    thread.join(timeout=5)

    collected = []
    while True:
        try:
            collected.append(tb._text_q.get_nowait())
        except queue.Empty:
            break

    assert "".join(collected) == "abcde"
