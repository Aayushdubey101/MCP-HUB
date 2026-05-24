"""Tests for depsgraph_listener.py — buffer diffs, flush, format."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chat_panel.depsgraph_listener import (
    _diff_buffer,
    _on_depsgraph_update,
    flush_diffs,
    format_diffs,
)


def _mock_update(name: str, *, transform=False, geometry=False, shading=False) -> MagicMock:
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj.matrix_world = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]

    update = MagicMock()
    update.id = obj
    update.is_updated_transform = transform
    update.is_updated_geometry = geometry
    update.is_updated_shading = shading
    return update


def _fake_depsgraph(updates):
    dg = MagicMock()
    dg.updates = updates
    return dg


# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_buffer():
    _diff_buffer.clear()
    yield
    _diff_buffer.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_transform_update_appended():
    upd = _mock_update("Cube", transform=True)
    _on_depsgraph_update(None, _fake_depsgraph([upd]))

    assert len(_diff_buffer) == 1
    diff = _diff_buffer[0]
    assert diff["op"] == "transform"
    assert diff["name"] == "Cube"
    assert diff["matrix"] is not None


def test_geometry_update_appended():
    upd = _mock_update("Sphere", geometry=True)
    _on_depsgraph_update(None, _fake_depsgraph([upd]))

    assert len(_diff_buffer) == 1
    diff = _diff_buffer[0]
    assert diff["op"] == "geometry"
    assert diff["name"] == "Sphere"


def test_multiple_updates_all_appended():
    updates = [
        _mock_update("A", transform=True),
        _mock_update("B", geometry=True),
    ]
    _on_depsgraph_update(None, _fake_depsgraph(updates))
    assert len(_diff_buffer) == 2


def test_flush_diffs_clears_buffer():
    upd = _mock_update("Cube", transform=True)
    _on_depsgraph_update(None, _fake_depsgraph([upd]))

    diffs = flush_diffs()
    assert len(diffs) == 1
    assert len(_diff_buffer) == 0


def test_flush_diffs_returns_copy():
    upd = _mock_update("Cube", transform=True)
    _on_depsgraph_update(None, _fake_depsgraph([upd]))

    diffs = flush_diffs()
    assert diffs[0]["name"] == "Cube"
    # Buffer cleared, returned list still valid
    assert len(_diff_buffer) == 0


def test_buffer_respects_maxlen():
    scene, dg = None, None
    # Fill beyond maxlen=200
    for i in range(250):
        upd = _mock_update(f"Obj{i}", transform=True)
        _on_depsgraph_update(None, _fake_depsgraph([upd]))

    assert len(_diff_buffer) == 200


def test_format_diffs_transform():
    diffs = [{"op": "transform", "name": "Cube"}]
    text = format_diffs(diffs)
    assert "Cube" in text
    assert "moved" in text.lower() or "transform" in text.lower() or "scaled" in text.lower()


def test_format_diffs_geometry():
    diffs = [{"op": "geometry", "name": "Suzanne"}]
    text = format_diffs(diffs)
    assert "Suzanne" in text
    assert "geometry" in text.lower() or "modified" in text.lower()


def test_format_diffs_empty():
    assert format_diffs([]) == ""


def test_update_with_none_id_skipped():
    upd = MagicMock()
    upd.id = None
    upd.is_updated_transform = True
    upd.is_updated_geometry = False
    _on_depsgraph_update(None, _fake_depsgraph([upd]))
    assert len(_diff_buffer) == 0
