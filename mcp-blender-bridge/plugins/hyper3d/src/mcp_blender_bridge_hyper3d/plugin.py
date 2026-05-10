"""Hyper3D Rodin plugin class."""

from __future__ import annotations


class Hyper3DPlugin:
    """MCP-Blender-Bridge plugin for Hyper3D Rodin AI 3D generation."""

    name = "hyper3d"
    version = "0.1.0"

    def register(self, mcp, client, *, read_only: bool = False) -> None:
        """Register Hyper3D tools with the MCP server."""
        from .tools import register_tools

        register_tools(mcp, client, read_only=read_only)
