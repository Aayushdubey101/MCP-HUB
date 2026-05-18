"""Tests for the Hyper3DPlugin class."""

from __future__ import annotations

from unittest.mock import MagicMock

from mcp_blender_bridge_hyper3d.plugin import Hyper3DPlugin


class TestHyper3DPlugin:
    def test_name(self) -> None:
        assert Hyper3DPlugin.name == "hyper3d"

    def test_version(self) -> None:
        assert Hyper3DPlugin.version == "0.1.0"

    def test_register_delegates_to_register_tools(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """register() should call register_tools without raising, even without an API key."""
        import mcp_blender_bridge_hyper3d.plugin as plugin_module

        called_with: list[tuple] = []

        def fake_register_tools(mcp, client, *, read_only: bool = False) -> None:
            called_with.append((mcp, client, read_only))

        monkeypatch.setattr(
            "mcp_blender_bridge_hyper3d.tools.register_tools",
            fake_register_tools,
        )

        mcp_mock = MagicMock()
        client_mock = MagicMock()
        plugin = Hyper3DPlugin()
        plugin.register(mcp_mock, client_mock, read_only=True)

        assert len(called_with) == 1
        _, _, ro = called_with[0]
        assert ro is True

    def test_module_exports_plugin_singleton(self) -> None:
        import mcp_blender_bridge_hyper3d as pkg

        assert isinstance(pkg.plugin, Hyper3DPlugin)
