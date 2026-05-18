"""Tests for server-level features: read-only mode, JSON logging, utils."""

from __future__ import annotations

import json
import logging

from blender_bridge.utils import READ_ONLY_ERROR, check_read_only


class TestCheckReadOnly:
    def test_returns_error_string_when_true(self):
        result = check_read_only(True)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "read-only" in parsed["message"].lower()

    def test_returns_none_when_false(self):
        assert check_read_only(False) is None

    def test_read_only_error_constant_is_valid_json(self):
        parsed = json.loads(READ_ONLY_ERROR)
        assert parsed["status"] == "error"
        assert "BLENDER_BRIDGE_READ_ONLY" in parsed["message"]

    def test_check_read_only_returns_constant(self):
        assert check_read_only(True) == READ_ONLY_ERROR


class TestJsonFormatter:
    def _get_formatter(self):
        from blender_bridge._log_formatter import JsonFormatter

        return JsonFormatter()

    def test_format_basic_record(self):
        fmt = self._get_formatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert parsed["msg"] == "hello world"
        assert "ts" in parsed

    def test_format_with_exception(self):
        fmt = self._get_formatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="oops",
            args=(),
            exc_info=exc_info,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "exc" in parsed
        assert "ValueError" in parsed["exc"]

    def test_output_is_single_line(self):
        fmt = self._get_formatter()
        record = logging.LogRecord(
            name="t",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="line1\nline2",
            args=(),
            exc_info=None,
        )
        output = fmt.format(record)
        assert "\n" not in output


class TestReadOnlyEnvVar:
    """Test the env-var parsing logic for BLENDER_BRIDGE_READ_ONLY."""

    @staticmethod
    def _parse(val: str) -> bool:
        return val.lower() in ("1", "true", "yes")

    def test_truthy_values(self):
        for val in ("true", "1", "yes", "True", "YES"):
            assert self._parse(val), f"{val!r} should be truthy"

    def test_falsy_values(self):
        for val in ("false", "0", "no", "", "False"):
            assert not self._parse(val), f"{val!r} should be falsy"
