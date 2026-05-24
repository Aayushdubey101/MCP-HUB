"""Tests for tool_format.py — Pydantic → per-provider schema conversion."""

from __future__ import annotations

from enum import Enum

import pytest
from pydantic import BaseModel, Field

from chat_panel.tool_format import (
    _inline_refs,
    pydantic_to_anthropic,
    pydantic_to_gemini,
    pydantic_to_openai,
)


class SimpleInput(BaseModel):
    name: str = Field(description="Object name")
    size: float = Field(default=1.0, gt=0)


class Kind(str, Enum):
    A = "a"
    B = "b"


class NestedEnum(BaseModel):
    kind: Kind


# ---------------------------------------------------------------------------
# pydantic_to_anthropic
# ---------------------------------------------------------------------------


def test_anthropic_structure():
    result = pydantic_to_anthropic("my_tool", SimpleInput, "Does a thing")
    assert result["name"] == "my_tool"
    assert result["description"] == "Does a thing"
    assert "input_schema" in result
    assert result["input_schema"]["type"] == "object"


def test_anthropic_preserves_field_descriptions():
    result = pydantic_to_anthropic("my_tool", SimpleInput, "desc")
    props = result["input_schema"]["properties"]
    assert props["name"]["description"] == "Object name"


# ---------------------------------------------------------------------------
# pydantic_to_openai
# ---------------------------------------------------------------------------


def test_openai_structure():
    result = pydantic_to_openai("my_tool", SimpleInput, "Does a thing")
    assert result["type"] == "function"
    fn = result["function"]
    assert fn["name"] == "my_tool"
    assert fn["description"] == "Does a thing"
    assert "parameters" in fn
    assert fn["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# pydantic_to_gemini
# ---------------------------------------------------------------------------


def test_gemini_structure():
    result = pydantic_to_gemini("my_tool", SimpleInput, "Does a thing")
    assert result["name"] == "my_tool"
    assert "parameters" in result
    assert "$defs" not in result["parameters"]


def test_gemini_no_dollar_ref():
    result = pydantic_to_gemini("my_tool", NestedEnum, "desc")
    schema_str = str(result)
    assert "$ref" not in schema_str
    assert "$defs" not in schema_str


# ---------------------------------------------------------------------------
# _inline_refs
# ---------------------------------------------------------------------------


def test_inline_refs_simple_passthrough():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    assert _inline_refs(schema) == schema


def test_inline_refs_resolves_ref():
    schema = {
        "$defs": {"MyType": {"type": "string", "enum": ["a", "b"]}},
        "type": "object",
        "properties": {"val": {"$ref": "#/$defs/MyType"}},
    }
    result = _inline_refs(schema)
    assert "$defs" not in result
    assert result["properties"]["val"] == {"type": "string", "enum": ["a", "b"]}


def test_inline_refs_nested():
    schema = {
        "$defs": {
            "Inner": {"type": "object", "properties": {"x": {"type": "integer"}}},
        },
        "properties": {
            "inner": {"$ref": "#/$defs/Inner"},
        },
    }
    result = _inline_refs(schema)
    assert result["properties"]["inner"]["properties"]["x"]["type"] == "integer"


def test_inline_refs_list_items():
    schema = {
        "$defs": {"Item": {"type": "string"}},
        "type": "array",
        "items": {"$ref": "#/$defs/Item"},
    }
    result = _inline_refs(schema)
    assert result["items"] == {"type": "string"}
