"""Hyper3D Rodin AI 3D generation plugin for MCP-Blender-Bridge.

This plugin exposes Hyper3D's Rodin API as MCP tools, enabling AI-driven
text-to-3D and image-to-3D asset generation directly from Claude/MCP clients.

Usage
-----
Install the plugin into the same virtualenv as mcp-blender-bridge::

    pip install mcp-blender-bridge-hyper3d

Then set your API key::

    export HYPER3D_API_KEY="your-key-here"

Sign up for a key at https://hyper3d.ai.
"""

from __future__ import annotations

from .plugin import Hyper3DPlugin

plugin = Hyper3DPlugin()

__all__ = ["plugin", "Hyper3DPlugin"]
