"""Tests for macro_recorder.py — start/stop, step recording, schema inference, persistence."""

from __future__ import annotations

import json
import pathlib
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from chat_panel.macro_recorder import (
    MacroStep,
    _diff_snapshots,
    infer_schema,
    is_recording,
    list_macros,
    load,
    record_step,
    register_as_tool,
    save,
    start,
    stop,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_state():
    """Ensure recorder is clean before and after each test."""
    # Stop any leftover recording without side effects
    import chat_panel.macro_recorder as mr
    mr._active = None
    mr._snapshot_before = {}
    yield
    mr._active = None
    mr._snapshot_before = {}


@pytest.fixture()
def tmp_macros_dir(tmp_path, monkeypatch):
    """Redirect macro storage to a temp directory."""
    import chat_panel.macro_recorder as mr

    monkeypatch.setattr(mr, "_macros_dir", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# start / stop / is_recording
# ---------------------------------------------------------------------------


class TestStartStop:
    def test_is_recording_false_initially(self):
        assert not is_recording()

    def test_start_sets_recording(self):
        with patch("chat_panel.macro_recorder._HAS_BPY", False):
            start("test")
        assert is_recording()

    def test_stop_returns_empty_when_no_steps(self):
        with patch("chat_panel.macro_recorder._HAS_BPY", False):
            start("test")
        steps = stop()
        assert steps == []
        assert not is_recording()

    def test_stop_without_start_returns_empty(self):
        steps = stop()
        assert steps == []

    def test_start_clears_previous_state(self):
        with patch("chat_panel.macro_recorder._HAS_BPY", False):
            start("first")
            record_step("op_a", {"x": 1})
            start("second")  # restart
        steps = stop()
        assert steps == []  # second recording had no steps


# ---------------------------------------------------------------------------
# record_step
# ---------------------------------------------------------------------------


class TestRecordStep:
    def test_record_step_while_recording(self):
        with patch("chat_panel.macro_recorder._HAS_BPY", False):
            start("macro")
        record_step("transform_object", {"name": "Cube", "location": (1, 2, 3)})
        steps = stop()
        assert len(steps) == 1
        assert steps[0].op_name == "transform_object"
        assert steps[0].params["name"] == "Cube"

    def test_record_step_ignored_when_not_recording(self):
        record_step("transform_object", {"name": "Cube"})
        assert not is_recording()

    def test_multiple_steps_preserved_in_order(self):
        with patch("chat_panel.macro_recorder._HAS_BPY", False):
            start("seq")
        record_step("create_object", {"name": "A"})
        record_step("transform_object", {"name": "A", "location": (1, 0, 0)})
        record_step("delete_object", {"name": "A"})
        steps = stop()
        assert [s.op_name for s in steps] == ["create_object", "transform_object", "delete_object"]


# ---------------------------------------------------------------------------
# _diff_snapshots
# ---------------------------------------------------------------------------


class TestDiffSnapshots:
    def _obj(self, loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), typ="MESH"):
        return {"location": loc, "rotation_euler": rot, "scale": scale, "type": typ}

    def test_added_object_creates_create_step(self):
        before = {}
        after = {"Cube": self._obj()}
        steps = _diff_snapshots(before, after)
        assert any(s.op_name == "create_object" and s.params["name"] == "Cube" for s in steps)

    def test_removed_object_creates_delete_step(self):
        before = {"Cube": self._obj()}
        after = {}
        steps = _diff_snapshots(before, after)
        assert any(s.op_name == "delete_object" and s.params["name"] == "Cube" for s in steps)

    def test_moved_object_creates_transform_step(self):
        before = {"Cube": self._obj(loc=(0.0, 0.0, 0.0))}
        after = {"Cube": self._obj(loc=(1.0, 0.0, 0.0))}
        steps = _diff_snapshots(before, after)
        assert any(s.op_name == "transform_object" and "location" in s.params for s in steps)

    def test_unchanged_object_produces_no_step(self):
        obj = self._obj()
        steps = _diff_snapshots({"Cube": obj}, {"Cube": obj})
        assert steps == []

    def test_empty_snapshots_no_steps(self):
        assert _diff_snapshots({}, {}) == []


# ---------------------------------------------------------------------------
# infer_schema
# ---------------------------------------------------------------------------


class TestInferSchema:
    def test_empty_steps_returns_empty_schema(self):
        schema = infer_schema([])
        assert schema["type"] == "object"
        assert schema["properties"] == {}

    def test_string_param_inferred(self):
        steps = [MacroStep(timestamp=0, op_name="op", params={"name": "Cube"})]
        schema = infer_schema(steps)
        assert schema["properties"]["name"]["type"] == "string"

    def test_float_param_inferred(self):
        steps = [MacroStep(timestamp=0, op_name="op", params={"strength": 0.5})]
        schema = infer_schema(steps)
        assert schema["properties"]["strength"]["type"] == "number"

    def test_int_param_inferred(self):
        steps = [MacroStep(timestamp=0, op_name="op", params={"count": 3})]
        schema = infer_schema(steps)
        assert schema["properties"]["count"]["type"] == "integer"

    def test_name_field_is_required(self):
        steps = [MacroStep(timestamp=0, op_name="op", params={"name": "X", "val": 1.0})]
        schema = infer_schema(steps)
        assert "name" in schema["required"]

    def test_duplicate_keys_not_duplicated(self):
        steps = [
            MacroStep(timestamp=0, op_name="op", params={"name": "A"}),
            MacroStep(timestamp=1, op_name="op", params={"name": "B"}),
        ]
        schema = infer_schema(steps)
        assert len(schema["properties"]) == 1

    def test_no_additional_properties(self):
        schema = infer_schema([])
        assert schema.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Persistence (save / load / list_macros)
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_save_creates_json_file(self, tmp_macros_dir):
        steps = [MacroStep(timestamp=1.0, op_name="create_object", params={"name": "Cube"})]
        path = save("test_macro", steps)
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_load_roundtrip(self, tmp_macros_dir):
        steps = [
            MacroStep(timestamp=1.0, op_name="create_object", params={"name": "Cube"}),
            MacroStep(timestamp=2.0, op_name="transform_object", params={"name": "Cube", "location": [1, 2, 3]}),
        ]
        save("roundtrip", steps)
        loaded_steps, schema = load("roundtrip")
        assert len(loaded_steps) == 2
        assert loaded_steps[0].op_name == "create_object"
        assert loaded_steps[1].params["name"] == "Cube"

    def test_save_embeds_schema(self, tmp_macros_dir):
        steps = [MacroStep(timestamp=1.0, op_name="op", params={"name": "X", "val": 0.5})]
        path = save("schema_test", steps)
        data = json.loads(path.read_text())
        assert "schema" in data
        assert "properties" in data["schema"]

    def test_list_macros_returns_names(self, tmp_macros_dir):
        save("alpha", [MacroStep(timestamp=0, op_name="op", params={})])
        save("beta", [MacroStep(timestamp=0, op_name="op", params={})])
        names = list_macros()
        assert "alpha" in names
        assert "beta" in names

    def test_list_macros_empty_dir(self, tmp_macros_dir):
        assert list_macros() == []


# ---------------------------------------------------------------------------
# register_as_tool
# ---------------------------------------------------------------------------


class TestRegisterAsTool:
    def test_register_calls_mcp_tool(self):
        mcp = MagicMock()
        client = MagicMock()
        steps = [MacroStep(timestamp=0, op_name="create_object", params={"name": "Cube"})]
        register_as_tool("my_macro", steps, mcp, client)
        mcp.tool.assert_called()

    def test_register_no_steps_still_registers(self):
        mcp = MagicMock()
        client = MagicMock()
        register_as_tool("empty_macro", [], mcp, client)
        mcp.tool.assert_called()
