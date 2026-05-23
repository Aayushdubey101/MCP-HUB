# MCP-Blender-Bridge PolyHaven Plugin

This is the PolyHaven asset library plugin for [MCP-Blender-Bridge](../../mcp-blender-bridge/).

It provides 5 free, no-auth asset tools to search and import CC0 assets directly from PolyHaven into your Blender scenes.

## Installation

Install this plugin into the same environment where your `mcp-blender-bridge` server is running:

```bash
uv add mcp-blender-bridge-polyhaven
```

## Configuration

The plugin caches downloaded textures and models to avoid re-downloading identical assets.

- **`BLENDER_BRIDGE_CACHE_DIR`**: Optional. Sets the directory where assets are cached. Defaults to `~/.cache/mcp-blender-bridge/assets/polyhaven/`.

## Provided Tools

1. `polyhaven_status`: Confirm plugin loaded, get version + cache directory.
2. `polyhaven_categories`: List asset categories per asset type (`hdris` / `textures` / `models`).
3. `polyhaven_search`: Search PolyHaven assets.
4. `polyhaven_download`: Download an asset to the cache directory.
5. `polyhaven_apply_texture`: Apply a downloaded PolyHaven texture (diffuse, normal, roughness) to an object in Blender as a Principled BSDF material.

## Attribution

Assets provided by [PolyHaven](https://polyhaven.com). All assets are available under the CC0 license.
