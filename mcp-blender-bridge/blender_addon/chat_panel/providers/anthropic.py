"""Anthropic Claude provider."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, AsyncIterator

from .base import ChatEvent, Message, Provider, Stop, TextDelta, ToolSpec, ToolUseArgs, ToolUseEnd, ToolUseStart

if TYPE_CHECKING:
    pass


class AnthropicProvider(Provider):
    def __init__(self, api_key: str) -> None:
        from anthropic import AsyncAnthropic  # type: ignore[import-untyped]

        self._client = AsyncAnthropic(api_key=api_key)

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        model: str,
        system: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        return self._stream(messages, tools, model, system)

    async def _stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        model: str,
        system: str | None,
    ) -> AsyncIterator[ChatEvent]:  # type: ignore[override]
        anthropic_tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
        anthropic_messages = [
            {"role": m.role if m.role != "tool" else "user", "content": m.content}
            for m in messages
        ]

        kwargs: dict = {
            "model": model,
            "max_tokens": 8096,
            "messages": anthropic_messages,
            "tools": anthropic_tools,
        }
        if system:
            kwargs["system"] = system

        async with self._client.messages.stream(**kwargs) as stream:
            current_tool_id: str | None = None

            async for event in stream:
                etype = event.type

                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool_id = block.id
                        yield ToolUseStart(id=block.id, name=block.name)

                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield TextDelta(text=delta.text)
                    elif delta.type == "input_json_delta" and current_tool_id:
                        yield ToolUseArgs(id=current_tool_id, partial_json=delta.partial_json)

                elif etype == "content_block_stop":
                    if current_tool_id:
                        yield ToolUseEnd(id=current_tool_id)
                        current_tool_id = None

                elif etype == "message_stop":
                    msg = await stream.get_final_message()
                    usage = {
                        "input_tokens": msg.usage.input_tokens,
                        "output_tokens": msg.usage.output_tokens,
                    }
                    yield Stop(reason=msg.stop_reason or "end_turn", usage=usage)

    @staticmethod
    def make_tool_result_message(tool_use_id: str, result: str) -> Message:
        return Message(
            role="user",
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result,
                }
            ],
        )
