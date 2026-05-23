# mcp-blender-bridge-sketchfab

Sketchfab 3D model search and download plugin for [MCP-Blender-Bridge](../../README.md).

## Tools

| Tool | Description |
|---|---|
| `sketchfab_status` | Check plugin status and API key configuration |
| `sketchfab_search` | Search Sketchfab's 3D model library by keyword |
| `sketchfab_preview` | Get detailed metadata for a model by UID |
| `sketchfab_download` | Download a GLTF model and import it into Blender |

## Setup

### 1. Get a Sketchfab API Token

Sign in at [sketchfab.com](https://sketchfab.com) → **Settings** → **Password & API** → copy your token.

### 2. Set the environment variable

```bash
export SKETCHFAB_API_KEY="your-token-here"
```

### 3. Install the plugin

```bash
pip install mcp-blender-bridge-sketchfab
```

## Usage

```
Claude: Search Sketchfab for a medieval castle
→ sketchfab_search(query="medieval castle", count=10)

Claude: Get more info about that first model
→ sketchfab_preview(uid="<uid from search>")

Claude: Download it and bring it into Blender
→ sketchfab_download(uid="<uid>", object_name="Castle")
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SKETCHFAB_API_KEY` | For downloads | — | API token from Sketchfab settings |
| `BLENDER_BRIDGE_CACHE_DIR` | No | `~/.cache/mcp-blender-bridge/assets/sketchfab` | Local cache for downloaded models |

## Notes

- **Search** works without an API key (public endpoint). **Download** requires a key.
- Only freely downloadable models can be fetched. Commercial models return a clear error.
- Downloaded models are cached by UID so subsequent imports are instant.
