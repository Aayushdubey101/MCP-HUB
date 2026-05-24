"""Tests for modal tool _impl functions and dispatcher registry.

bpy is not available in test environment — all Blender calls are mocked.
Tests verify: schema validation, correct command name sent to client,
correct params forwarded, read_only guard, error propagation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from blender_bridge.schemas import (
    ModalBevelInput,
    ModalExtrudeInput,
    ModalKnifeCutInput,
    ModalLoopCutInput,
    ModalSculptInput,
)
from blender_bridge.tools.modal import (
    _modal_bevel_impl,
    _modal_extrude_impl,
    _modal_knife_cut_impl,
    _modal_loop_cut_impl,
    _modal_sculpt_impl,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(result: dict | None = None) -> MagicMock:
    client = MagicMock()
    response_payload = {"status": "success", "result": result or {}}
    client.send_command = AsyncMock(return_value=response_payload)
    return client


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_extrude_rejects_bad_direction(self):
        with pytest.raises(Exception):
            ModalExtrudeInput(object_name="Cube", direction="diagonal", distance=1.0)

    def test_extrude_rejects_too_large_distance(self):
        with pytest.raises(Exception):
            ModalExtrudeInput(object_name="Cube", direction="z", distance=9999.0)

    def test_loop_cut_rejects_zero_cuts(self):
        with pytest.raises(Exception):
            ModalLoopCutInput(object_name="Cube", edge_index=0, cuts=0)

    def test_loop_cut_rejects_too_many_cuts(self):
        with pytest.raises(Exception):
            ModalLoopCutInput(object_name="Cube", edge_index=0, cuts=65)

    def test_knife_requires_at_least_2_points(self):
        with pytest.raises(Exception):
            ModalKnifeCutInput(object_name="Cube", points=[(0.0, 0.0)])

    def test_knife_rejects_too_many_points(self):
        with pytest.raises(Exception):
            ModalKnifeCutInput(object_name="Cube", points=[(float(i), 0.0) for i in range(33)])

    def test_bevel_rejects_zero_width(self):
        with pytest.raises(Exception):
            ModalBevelInput(object_name="Cube", width=0.0)

    def test_bevel_rejects_too_many_segments(self):
        with pytest.raises(Exception):
            ModalBevelInput(object_name="Cube", width=0.1, segments=17)

    def test_sculpt_rejects_strength_above_1(self):
        with pytest.raises(Exception):
            ModalSculptInput(object_name="Cube", strength=1.1)

    def test_object_name_cannot_be_empty(self):
        with pytest.raises(Exception):
            ModalExtrudeInput(object_name="", direction="z", distance=1.0)


# ---------------------------------------------------------------------------
# _impl: correct command name forwarded to client
# ---------------------------------------------------------------------------


class TestCommandRouting:
    def test_extrude_sends_modal_extrude(self):
        client = _make_client({"object_name": "Cube"})
        params = ModalExtrudeInput(object_name="Cube", direction="z", distance=2.0)
        run(_modal_extrude_impl(params, client))
        client.send_command.assert_called_once()
        cmd, _ = client.send_command.call_args[0]
        assert cmd == "modal_extrude"

    def test_loop_cut_sends_modal_loop_cut(self):
        client = _make_client({"object_name": "Cube"})
        params = ModalLoopCutInput(object_name="Cube", edge_index=2, cuts=2)
        run(_modal_loop_cut_impl(params, client))
        cmd, _ = client.send_command.call_args[0]
        assert cmd == "modal_loop_cut"

    def test_knife_sends_modal_knife_cut(self):
        client = _make_client({"object_name": "Cube"})
        params = ModalKnifeCutInput(object_name="Cube", points=[(0.0, 0.0), (1.0, 1.0)])
        run(_modal_knife_cut_impl(params, client))
        cmd, _ = client.send_command.call_args[0]
        assert cmd == "modal_knife_cut"

    def test_bevel_sends_modal_bevel(self):
        client = _make_client({"object_name": "Cube"})
        params = ModalBevelInput(object_name="Cube", width=0.05, segments=2)
        run(_modal_bevel_impl(params, client))
        cmd, _ = client.send_command.call_args[0]
        assert cmd == "modal_bevel"

    def test_sculpt_sends_modal_sculpt(self):
        client = _make_client({"object_name": "Cube"})
        params = ModalSculptInput(object_name="Cube", brush="SMOOTH", strength=0.3)
        run(_modal_sculpt_impl(params, client))
        cmd, _ = client.send_command.call_args[0]
        assert cmd == "modal_sculpt"


# ---------------------------------------------------------------------------
# _impl: correct params forwarded
# ---------------------------------------------------------------------------


class TestParamForwarding:
    def test_extrude_params(self):
        client = _make_client()
        params = ModalExtrudeInput(object_name="Sphere", direction="x", distance=-0.5)
        run(_modal_extrude_impl(params, client))
        _, sent = client.send_command.call_args[0]
        assert sent["object_name"] == "Sphere"
        assert sent["direction"] == "x"
        assert sent["distance"] == pytest.approx(-0.5)

    def test_loop_cut_params(self):
        client = _make_client()
        params = ModalLoopCutInput(object_name="Plane", edge_index=5, cuts=3, factor=0.25)
        run(_modal_loop_cut_impl(params, client))
        _, sent = client.send_command.call_args[0]
        assert sent["edge_index"] == 5
        assert sent["cuts"] == 3
        assert sent["factor"] == pytest.approx(0.25)

    def test_knife_points_serialised_as_lists(self):
        client = _make_client()
        params = ModalKnifeCutInput(object_name="Cube", points=[(0.1, 0.2), (0.9, 0.8)])
        run(_modal_knife_cut_impl(params, client))
        _, sent = client.send_command.call_args[0]
        assert isinstance(sent["points"][0], list)
        assert sent["points"][0] == pytest.approx([0.1, 0.2])

    def test_bevel_params(self):
        client = _make_client()
        params = ModalBevelInput(object_name="Monkey", width=0.2, segments=4)
        run(_modal_bevel_impl(params, client))
        _, sent = client.send_command.call_args[0]
        assert sent["width"] == pytest.approx(0.2)
        assert sent["segments"] == 4

    def test_sculpt_params(self):
        client = _make_client()
        params = ModalSculptInput(object_name="Suzanne", brush="INFLATE", strength=0.8)
        run(_modal_sculpt_impl(params, client))
        _, sent = client.send_command.call_args[0]
        assert sent["brush"] == "INFLATE"
        assert sent["strength"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# read_only guard
# ---------------------------------------------------------------------------


class TestReadOnlyGuard:
    def test_extrude_blocked_in_read_only(self):
        client = _make_client()
        params = ModalExtrudeInput(object_name="Cube", direction="z", distance=1.0)
        result = run(_modal_extrude_impl(params, client, read_only=True))
        client.send_command.assert_not_called()
        assert "read" in result.lower() or "only" in result.lower() or "error" in result.lower()

    def test_bevel_blocked_in_read_only(self):
        client = _make_client()
        params = ModalBevelInput(object_name="Cube")
        result = run(_modal_bevel_impl(params, client, read_only=True))
        client.send_command.assert_not_called()
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_client_error_returns_format_error(self):
        client = MagicMock()
        client.send_command = AsyncMock(side_effect=ConnectionError("Blender not running"))
        params = ModalExtrudeInput(object_name="Cube", direction="z", distance=1.0)
        result = run(_modal_extrude_impl(params, client))
        assert "error" in result.lower() or "blender" in result.lower()

    def test_bevel_client_error(self):
        client = MagicMock()
        client.send_command = AsyncMock(side_effect=RuntimeError("operator failed"))
        params = ModalBevelInput(object_name="Cube", width=0.1)
        result = run(_modal_bevel_impl(params, client))
        assert len(result) > 0
        assert "error" in result.lower() or "operator" in result.lower()


# ---------------------------------------------------------------------------
# Dispatcher registry integration
# ---------------------------------------------------------------------------


class TestDispatcherRegistry:
    def test_modal_tools_in_registry(self):
        from chat_panel.tool_dispatcher import _REGISTRY

        expected = {
            "blender_modal_extrude",
            "blender_modal_loop_cut",
            "blender_modal_knife_cut",
            "blender_modal_bevel",
            "blender_modal_sculpt",
        }
        assert expected.issubset(set(_REGISTRY.keys()))

    def test_registry_entries_have_schema(self):
        from chat_panel.tool_dispatcher import _REGISTRY

        for name in ("blender_modal_extrude", "blender_modal_bevel", "blender_modal_sculpt"):
            _, schema_cls = _REGISTRY[name]
            assert schema_cls is not None

    def test_dispatch_unknown_tool_returns_error(self):
        from chat_panel.tool_dispatcher import dispatch

        result = run(dispatch("blender_modal_nonexistent", {}, MagicMock()))
        assert "error" in result.lower() or "unknown" in result.lower()
