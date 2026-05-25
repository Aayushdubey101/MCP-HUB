"""Google Gemini provider."""

from __future__ import annotations

import json
from typing import AsyncIterator

from ..tool_format import _inline_refs
from .base import ChatEvent, Message, Provider, Stop, TextDelta, ToolSpec, ToolUseArgs, ToolUseEnd, ToolUseStart


class GeminiProvider(Provider):
    def __init__(self, api_key: str) -> None:
        from google import genai  # type: ignore[import-untyped]

        self._client = genai.Client(api_key=api_key)

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
        from google.genai import types  # type: ignore[import-untyped]

        function_declarations = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": _inline_refs(t.input_schema),
            }
            for t in tools
        ]

        # Convert messages to Gemini format (roles: user / model)
        gemini_contents = []
        for m in messages:
            if m.role == "tool":
                # Tool result
                for block in m.content:
                    gemini_contents.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    function_response=types.FunctionResponse(
                                        name=block.get("name", ""),
                                        response={"result": block.get("content", "")},
                                    )
                                )
                            ],
                        )
                    )
            else:
                role = "model" if m.role == "assistant" else "user"
                parts = []
                for block in m.content:
                    if isinstance(block, str):
                        parts.append(types.Part(text=block))
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(types.Part(text=block["text"]))
                gemini_contents.append(types.Content(role=role, parts=parts))

        config_kwargs: dict = {
            "tools": [types.Tool(function_declarations=function_declarations)],
        }
        if system:
            config_kwargs["system_instruction"] = system

        config = types.GenerateContentConfig(**config_kwargs)

        active_tool_id: str | None = None
        active_tool_name: str | None = None
        active_tool_args: str = ""

        async for chunk in await self._client.aio.models.generate_content_stream(
            model=model,
            contents=gemini_contents,
            config=config,
        ):
            if not chunk.candidates:
                continue

            for part in chunk.candidates[0].content.parts:
                if part.text:
                    # Flush any pending tool accumulation
                    if active_tool_id:
                        yield ToolUseEnd(id=active_tool_id)
                        active_tool_id = None
                        active_tool_name = None
                        active_tool_args = ""
                    yield TextDelta(text=part.text)

                elif part.function_call:
                    fc = part.function_call
                    tool_id = f"gemini_{fc.name}_{id(fc)}"
                    if active_tool_id and active_tool_id != tool_id:
                        yield ToolUseEnd(id=active_tool_id)

                    active_tool_id = tool_id
                    active_tool_name = fc.name
                    args_str = json.dumps(dict(fc.args)) if fc.args else "{}"
                    yield ToolUseStart(id=tool_id, name=fc.name)
                    yield ToolUseArgs(id=tool_id, partial_json=args_str)

            finish = chunk.candidates[0].finish_reason if chunk.candidates else None
            if finish and str(finish) not in ("", "FINISH_REASON_UNSPECIFIED"):
                if active_tool_id:
                    yield ToolUseEnd(id=active_tool_id)
                    active_tool_id = None
                reason = "tool_use" if active_tool_name else "end_turn"
                yield Stop(reason=reason)

    @staticmethod
    def make_tool_result_message(tool_name: str, result: str) -> Message:
        return Message(
            role="tool",
            content=[{"name": tool_name, "content": result}],
        )
