"""Sketchfab plugin class."""

from __future__ import annotations


class SketchfabPlugin:
    """MCP-Blender-Bridge plugin for Sketchfab 3D model search and download."""

    name = "sketchfab"
    version = "0.1.0"

    def register(self, mcp, client, *, read_only: bool = False) -> None:
        """Register Sketchfab tools with the MCP server."""
        from .tools import register_tools

        register_tools(mcp, client, read_only=read_only)
