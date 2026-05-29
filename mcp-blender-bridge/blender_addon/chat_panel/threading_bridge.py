"""Main-thread / worker-thread bridge via queues.

Design:
  Worker thread (asyncio event loop):
    - Calls provider.chat() in a multi-turn loop
    - Puts text chunks on _text_q (str)
    - Puts _ToolCall namedtuples on _tool_q when a tool completes
    - Blocks on _response_q waiting for main-thread tool result
    - Puts Stop on _stop_q when LLM turn ends

  Main thread (_main_thread_tick, 50 ms bpy.app.timers callback):
    - Drains _text_q → appends to PropertyGroup history[-1].content
    - Drains _tool_q → calls tool_dispatcher → puts result on _response_q
    - Drains _stop_q → clears is_streaming flag

CRITICAL: no bpy.* calls are ever made from the worker thread.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from dataclasses import dataclass
from typing import Any

from .providers.base import Message, Provider, Stop, TextDelta, ToolSpec, ToolUseArgs, ToolUseEnd, ToolUseStart

# ---------------------------------------------------------------------------
# Module-level queues
# ---------------------------------------------------------------------------

_text_q: queue.Queue[str] = queue.Queue()
_tool_q: queue.Queue["_ToolCall"] = queue.Queue()
_response_q: queue.Queue[str] = queue.Queue()
_stop_q: queue.Queue[Stop] = queue.Queue()

_active_state: Any = None  # PropertyGroup; set by run_chat_in_background
_active_client: Any = None  # BlenderClient; set by run_chat_in_background


@dataclass
class _ToolCall:
    id: str
    name: str
    args: dict


# ---------------------------------------------------------------------------
# Worker (off-thread)
# ---------------------------------------------------------------------------


def run_chat_in_background(
    messages: list[Message],
    tools: list[ToolSpec],
    provider: Provider,
    model: str,
    system: str | None,
    client: Any,
    state: Any,
) -> None:
    global _active_state, _active_client
    _active_state = state
    _active_client = client
    thread = threading.Thread(
        target=_worker,
        args=(messages, tools, provider, model, system),
        daemon=True,
    )
    thread.start()


def _worker(
    messages: list[Message],
    tools: list[ToolSpec],
    provider: Provider,
    model: str,
    system: str | None,
) -> None:
    asyncio.run(_async_worker(messages, tools, provider, model, system))


async def _async_worker(
    messages: list[Message],
    tools: list[ToolSpec],
    provider: Provider,
    model: str,
    system: str | None,
) -> None:
    """Never calls bpy.*. Only touches queues and the provider."""
    while True:
        pending: dict[str, dict] = {}  # tool_id → {name, args_buf}

        async for event in provider.chat(messages=messages, tools=tools, model=model, system=system):
            if isinstance(event, ToolUseStart):
                pending[event.id] = {"name": event.name, "args_buf": ""}

            elif isinstance(event, ToolUseArgs):
                if event.id in pending:
                    pending[event.id]["args_buf"] += event.partial_json

            elif isinstance(event, TextDelta):
                _text_q.put(event.text)

            elif isinstance(event, ToolUseEnd):
                info = pending.pop(event.id, {})
                args_json = info.get("args_buf", "{}")
                try:
                    args = json.loads(args_json) if args_json else {}
                except json.JSONDecodeError:
                    args = {}
                _tool_q.put(_ToolCall(id=event.id, name=info.get("name", ""), args=args))
                result = _response_q.get(timeout=30)
                messages = [*messages, Message(role="tool", content=[{"tool_use_id": event.id, "content": result}])]

            elif isinstance(event, Stop):
                _stop_q.put(event)
                if event.reason != "tool_use":
                    return
                break  # re-enter outer while for next turn


# ---------------------------------------------------------------------------
# Main-thread tick (bpy.app.timers callback)
# ---------------------------------------------------------------------------


def _main_thread_tick() -> float:
    """Registered as bpy.app.timers persistent callback. Main thread only."""
    try:
        import bpy  # noqa: PLC0415
    except ImportError:
        _drain_queues_no_bpy()
        return 0.05

    from . import tool_dispatcher  # noqa: PLC0415

    state = _active_state
    client = _active_client

    # Drain text → PropertyGroup
    while True:
        try:
            text = _text_q.get_nowait()
            if state and state.history:
                state.history[-1].content += text
        except queue.Empty:
            break

    # Dispatch tool calls → result
    while True:
        try:
            call = _tool_q.get_nowait()
            try:
                result = asyncio.run(tool_dispatcher.dispatch(call.name, call.args, client))
            except Exception as exc:
                from blender_bridge.utils import format_error  # noqa: PLC0415
                result = format_error(str(exc))
            _response_q.put(result)
        except queue.Empty:
            break

    # Handle stop
    while True:
        try:
            stop = _stop_q.get_nowait()
            if state:
                state.is_streaming = False
            del stop
        except queue.Empty:
            break

    return 0.05


def _drain_queues_no_bpy() -> None:
    """Used in test environments: drain queues without bpy access."""
    for q in (_text_q, _stop_q):
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                break
