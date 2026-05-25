"""OpenAI-compatible provider — covers GPT, LM Studio, Ollama, vLLM, Together, Groq."""

from __future__ import annotations

import json
from typing import AsyncIterator

from .base import ChatEvent, Message, Provider, Stop, TextDelta, ToolSpec, ToolUseArgs, ToolUseEnd, ToolUseStart

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatProvider(Provider):
    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL) -> None:
        from openai import AsyncOpenAI  # type: ignore[import-untyped]

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

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
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

        openai_messages: list[dict] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        for m in messages:
            if m.role == "tool":
                # Already formatted as tool result dicts — pass through
                for block in m.content:
                    openai_messages.append(block)
            else:
                role = "assistant" if m.role == "assistant" else "user"
                openai_messages.append({"role": role, "content": m.content})

        # Accumulate tool_call argument deltas keyed by index
        tool_call_buffers: dict[int, dict] = {}

        stream = await self._client.chat.completions.create(
            model=model,
            messages=openai_messages,
            tools=openai_tools if openai_tools else None,
            stream=True,
        )

        finish_reason: str | None = None

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            delta = choice.delta
            finish_reason = choice.finish_reason or finish_reason

            if delta.content:
                yield TextDelta(text=delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function else "",
                            "args": "",
                        }
                        if tc.id:
                            yield ToolUseStart(id=tc.id, name=tc.function.name or "")
                    else:
                        if tc.id and not tool_call_buffers[idx]["id"]:
                            tool_call_buffers[idx]["id"] = tc.id
                        if tc.function and tc.function.name and not tool_call_buffers[idx]["name"]:
                            tool_call_buffers[idx]["name"] = tc.function.name

                    if tc.function and tc.function.arguments:
                        tool_call_buffers[idx]["args"] += tc.function.arguments
                        yield ToolUseArgs(
                            id=tool_call_buffers[idx]["id"],
                            partial_json=tc.function.arguments,
                        )

        # Emit ToolUseEnd for all accumulated tool calls
        for buf in tool_call_buffers.values():
            yield ToolUseEnd(id=buf["id"])

        yield Stop(reason=_map_finish_reason(finish_reason))

    @staticmethod
    def make_tool_result_message(tool_call_id: str, name: str, result: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }


def _map_finish_reason(reason: str | None) -> str:
    mapping = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
        None: "end_turn",
    }
    return mapping.get(reason, "end_turn")
