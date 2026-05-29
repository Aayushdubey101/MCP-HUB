"""Convert Pydantic models to per-provider tool schema formats."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def pydantic_to_anthropic(name: str, model: type[BaseModel], description: str) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": model.model_json_schema(),
    }


def pydantic_to_openai(name: str, model: type[BaseModel], description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": model.model_json_schema(),
        },
    }


def pydantic_to_gemini(name: str, model: type[BaseModel], description: str) -> dict:
    schema = _inline_refs(model.model_json_schema())
    return {
        "name": name,
        "description": description,
        "parameters": schema,
    }


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively replace $ref with referenced definition. Removes $defs."""
    defs = schema.get("$defs", {})
    return _resolve(schema, defs)  # type: ignore[return-value]


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            ref_name = node["$ref"].split("/")[-1]
            return _resolve(defs[ref_name], defs)
        return {k: _resolve(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_resolve(i, defs) for i in node]
    return node
