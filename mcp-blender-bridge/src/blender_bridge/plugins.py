"""Plugin discovery and registration for MCP-Blender-Bridge.

Plugins are separately-installable Python packages that register additional
MCP tools (e.g. PolyHaven asset import, Hyper3D Rodin generation, Sketchfab).
They are discovered at server startup via the standard
``importlib.metadata.entry_points`` mechanism on the
``blender_bridge.plugins`` group.

A plugin package's ``pyproject.toml`` declares its entry point:

.. code-block:: toml

    [project.entry-points."blender_bridge.plugins"]
    polyhaven = "mcp_blender_bridge_polyhaven:plugin"

Where ``mcp_blender_bridge_polyhaven.plugin`` is an object that satisfies
the :class:`BlenderBridgePlugin` protocol.

This loader is *opt-in by package install*: the core server ships with
zero plugins. A plugin only runs if its package is installed in the same
Python environment as the server.
"""

from __future__ import annotations

import logging
from importlib.metadata import EntryPoint, entry_points
from typing import Protocol, runtime_checkable

from mcp.server.fastmcp import FastMCP

from .client import BlenderClient

logger = logging.getLogger(__name__)

PLUGIN_GROUP = "blender_bridge.plugins"


@runtime_checkable
class BlenderBridgePlugin(Protocol):
    """Contract every plugin must satisfy.

    Attributes:
        name: Short identifier shown in logs and ``--list-plugins`` output.
        version: SemVer string of the plugin package.

    Methods:
        register: Register the plugin's MCP tools on the supplied ``mcp``
            instance, using the shared ``client`` to talk to Blender. The
            ``read_only`` flag mirrors the server's ``BLENDER_BRIDGE_READ_ONLY``
            env var; plugins must refuse to register destructive tools when
            it is True.
    """

    name: str
    version: str

    def register(
        self,
        mcp: FastMCP,
        client: BlenderClient,
        *,
        read_only: bool = False,
    ) -> None: ...


def _iter_entry_points() -> list[EntryPoint]:
    """Return all entry points under :data:`PLUGIN_GROUP`.

    Wrapped in a helper so tests can patch it cleanly.
    """
    eps = entry_points()
    # importlib.metadata API differs across Python versions; both branches return
    # an iterable of EntryPoint objects.
    if hasattr(eps, "select"):
        return list(eps.select(group=PLUGIN_GROUP))
    return list(eps.get(PLUGIN_GROUP, []))  # type: ignore[attr-defined]


def discover_plugins() -> list[BlenderBridgePlugin]:
    """Load every installed plugin without registering it. Returns the plugin objects.

    Plugins that fail to load (import error, missing attributes, wrong type)
    are logged and skipped — one bad plugin must never bring the server down.
    """
    loaded: list[BlenderBridgePlugin] = []
    for ep in _iter_entry_points():
        try:
            obj = ep.load()
        except Exception as e:  # noqa: BLE001 — we genuinely want to swallow plugin import failures
            logger.error("Failed to load plugin %r: %s", ep.name, e)
            continue

        if not isinstance(obj, BlenderBridgePlugin):
            logger.error(
                "Entry point %r does not satisfy BlenderBridgePlugin protocol "
                "(missing name/version/register). Skipping.",
                ep.name,
            )
            continue

        loaded.append(obj)
    return loaded


def load_plugins(
    mcp: FastMCP,
    client: BlenderClient,
    *,
    read_only: bool = False,
) -> list[tuple[str, str]]:
    """Discover and register every installed plugin.

    Returns:
        List of ``(name, version)`` tuples for plugins that registered cleanly.
        Plugins whose ``register`` raises are logged and skipped.
    """
    registered: list[tuple[str, str]] = []
    for plugin in discover_plugins():
        try:
            plugin.register(mcp, client, read_only=read_only)
        except Exception as e:  # noqa: BLE001
            logger.error("Plugin %r failed during register(): %s", plugin.name, e)
            continue
        logger.info("Loaded plugin %s v%s", plugin.name, plugin.version)
        registered.append((plugin.name, plugin.version))
    return registered


def list_plugins_text() -> str:
    """Human-readable listing for the ``--list-plugins`` CLI flag."""
    plugins = discover_plugins()
    if not plugins:
        return "No plugins installed.\n"
    lines = ["Installed plugins:"]
    for p in plugins:
        lines.append(f"  - {p.name} v{p.version}")
    return "\n".join(lines) + "\n"
