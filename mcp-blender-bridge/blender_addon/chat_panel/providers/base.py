"""Provider ABC and ChatEvent type definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolUseStart:
    id: str
    name: str


@dataclass
class ToolUseArgs:
    id: str
    partial_json: str


@dataclass
class ToolUseEnd:
    id: str


@dataclass
class Stop:
    reason: Literal["end_turn", "tool_use", "max_tokens", "error"]
    usage: dict | None = field(default=None)


ChatEvent = TextDelta | ToolUseStart | ToolUseArgs | ToolUseEnd | Stop


@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    content: list[dict]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict  # JSON Schema from model_json_schema()


class Provider(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        model: str,
        system: str | None = None,
    ) -> AsyncIterator[ChatEvent]: ...
