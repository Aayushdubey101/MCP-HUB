"""Tests for the response formatting utilities."""

from __future__ import annotations

import json

import pytest

from blender_bridge.client import BlenderConnectionError
from blender_bridge.utils import (
    format_error,
    format_success,
    handle_blender_error,
    parse_blender_response,
)


class TestFormatError:
    def test_returns_json_string(self):
        result = format_error("something broke")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["message"] == "something broke"

    def test_empty_message(self):
        result = format_error("")
        data = json.loads(result)
        assert data["message"] == ""


class TestFormatSuccess:
    def test_simple_result(self):
        result = format_success({"key": "value"})
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["result"] == {"key": "value"}
        assert "message" not in data

    def test_with_message(self):
        result = format_success(42, message="done")
        data = json.loads(result)
        assert data["result"] == 42
        assert data["message"] == "done"

    def test_none_result(self):
        result = format_success(None)
        data = json.loads(result)
        assert data["result"] is None

    def test_list_result(self):
        result = format_success([1, 2, 3])
        data = json.loads(result)
        assert data["result"] == [1, 2, 3]

    def test_non_serializable_uses_str(self):
        class Unserializable:
            def __repr__(self) -> str:
                return "custom_repr"

        result = format_success(Unserializable())
        data = json.loads(result)
        assert "custom_repr" in data["result"]


class TestParseBlenderResponse:
    def test_success_response(self):
        response = {"status": "success", "result": {"name": "Cube"}}
        assert parse_blender_response(response) == {"name": "Cube"}

    def test_error_response_raises(self):
        response = {"status": "error", "message": "Object not found"}
        with pytest.raises(BlenderConnectionError, match="Object not found"):
            parse_blender_response(response)

    def test_missing_message_uses_fallback(self):
        response = {"status": "error"}
        with pytest.raises(BlenderConnectionError, match="unknown error"):
            parse_blender_response(response)

    def test_none_result(self):
        response = {"status": "success", "result": None}
        assert parse_blender_response(response) is None


class TestHandleBlenderError:
    def test_connection_error_gives_actionable_message(self):
        exc = BlenderConnectionError("refused")
        result = handle_blender_error(exc)
        data = json.loads(result)
        assert data["status"] == "error"
        assert "Blender" in data["message"]
        assert "addon" in data["message"].lower()

    def test_generic_exception(self):
        exc = RuntimeError("unexpected")
        result = handle_blender_error(exc)
        data = json.loads(result)
        assert data["status"] == "error"
        assert "RuntimeError" in data["message"]
        assert "unexpected" in data["message"]
