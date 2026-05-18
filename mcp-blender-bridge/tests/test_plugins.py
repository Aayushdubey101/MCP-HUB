"""Tests for the plugin discovery / registration layer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from blender_bridge.client import BlenderClient
from blender_bridge.plugins import (
    BlenderBridgePlugin,
    discover_plugins,
    list_plugins_text,
    load_plugins,
)


class GoodPlugin:
    name = "good"
    version = "1.2.3"

    def __init__(self) -> None:
        self.register_calls: list[dict] = []

    def register(self, mcp, client, *, read_only: bool = False) -> None:  # noqa: ANN001
        self.register_calls.append({"mcp": mcp, "client": client, "read_only": read_only})


class BadShapePlugin:
    """Missing `version` — fails the Protocol isinstance check."""

    name = "bad_shape"

    def register(self, mcp, client, *, read_only: bool = False) -> None:  # noqa: ANN001
        pass


class RegisterRaisesPlugin:
    name = "raises"
    version = "0.0.1"

    def register(self, mcp, client, *, read_only: bool = False) -> None:  # noqa: ANN001
        raise RuntimeError("kaboom")


def _ep(name: str, return_value):
    """Build a fake EntryPoint whose .load() returns the given object."""
    ep = MagicMock()
    ep.name = name
    ep.load = MagicMock(return_value=return_value)
    return ep


class TestProtocol:
    def test_good_plugin_satisfies_protocol(self):
        assert isinstance(GoodPlugin(), BlenderBridgePlugin)

    def test_bad_shape_plugin_does_not(self):
        assert not isinstance(BadShapePlugin(), BlenderBridgePlugin)


class TestDiscoverPlugins:
    def test_returns_empty_when_none_installed(self):
        with patch("blender_bridge.plugins._iter_entry_points", return_value=[]):
            assert discover_plugins() == []

    def test_filters_out_bad_shape_plugins(self, caplog):
        good = GoodPlugin()
        bad = BadShapePlugin()
        eps = [_ep("good", good), _ep("bad_shape", bad)]
        with patch("blender_bridge.plugins._iter_entry_points", return_value=eps):
            with caplog.at_level("ERROR", logger="blender_bridge.plugins"):
                result = discover_plugins()
        assert result == [good]
        assert "does not satisfy BlenderBridgePlugin protocol" in caplog.text

    def test_swallows_import_errors(self, caplog):
        broken = MagicMock()
        broken.name = "broken"
        broken.load = MagicMock(side_effect=ImportError("missing dep"))
        good = GoodPlugin()
        eps = [broken, _ep("good", good)]
        with patch("blender_bridge.plugins._iter_entry_points", return_value=eps):
            with caplog.at_level("ERROR", logger="blender_bridge.plugins"):
                result = discover_plugins()
        assert result == [good]
        assert "Failed to load plugin 'broken'" in caplog.text


class TestLoadPlugins:
    def setup_method(self):
        self.mcp = MagicMock()
        self.client = BlenderClient()

    def test_calls_register_with_correct_args(self):
        good = GoodPlugin()
        with patch("blender_bridge.plugins._iter_entry_points", return_value=[_ep("good", good)]):
            registered = load_plugins(self.mcp, self.client, read_only=True)
        assert registered == [("good", "1.2.3")]
        assert len(good.register_calls) == 1
        assert good.register_calls[0]["read_only"] is True
        assert good.register_calls[0]["mcp"] is self.mcp
        assert good.register_calls[0]["client"] is self.client

    def test_one_plugin_failure_does_not_block_others(self, caplog):
        good = GoodPlugin()
        raiser = RegisterRaisesPlugin()
        eps = [_ep("raises", raiser), _ep("good", good)]
        with patch("blender_bridge.plugins._iter_entry_points", return_value=eps):
            with caplog.at_level("ERROR", logger="blender_bridge.plugins"):
                registered = load_plugins(self.mcp, self.client)
        assert registered == [("good", "1.2.3")]
        assert "kaboom" in caplog.text

    def test_no_plugins_returns_empty_list(self):
        with patch("blender_bridge.plugins._iter_entry_points", return_value=[]):
            assert load_plugins(self.mcp, self.client) == []


class TestListPluginsText:
    def test_empty(self):
        with patch("blender_bridge.plugins._iter_entry_points", return_value=[]):
            assert "No plugins installed" in list_plugins_text()

    def test_lists_each_plugin(self):
        eps = [_ep("polyhaven", GoodPlugin())]
        with patch("blender_bridge.plugins._iter_entry_points", return_value=eps):
            text = list_plugins_text()
        assert "good v1.2.3" in text
        assert "Installed plugins" in text


class TestServerWiresLoader:
    """Sanity check that server.py imports and calls load_plugins."""

    def test_server_module_exposes_loaded_plugins(self):
        # Import the module — it runs top-level registration including load_plugins.
        # If discovery fails for any reason, this import would already have broken.
        import blender_bridge.server as server  # noqa: PLC0415

        assert hasattr(server, "_loaded_plugins")
        assert isinstance(server._loaded_plugins, list)
