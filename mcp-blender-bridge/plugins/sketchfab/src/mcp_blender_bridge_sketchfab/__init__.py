"""Sketchfab 3D model search and download plugin for MCP-Blender-Bridge.

Browse Sketchfab's library of 3D models, preview metadata, download GLTF
files (for downloadable models), and import them into Blender — all from
Claude or any MCP client.

Usage
-----
Install into the same virtualenv as mcp-blender-bridge::

    pip install mcp-blender-bridge-sketchfab

Set your API key::

    export SKETCHFAB_API_KEY="your-key-here"

Get a key at https://sketchfab.com/settings#password (API token section).
"""

from __future__ import annotations

from .plugin import SketchfabPlugin

plugin = SketchfabPlugin()

__all__ = ["plugin", "SketchfabPlugin"]
