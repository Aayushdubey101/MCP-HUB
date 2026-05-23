# mcp-blender-bridge-hyper3d

Hyper3D Rodin AI 3D generation plugin for [MCP-Blender-Bridge](https://github.com/Aayushdubey101/MCP-HUB).

Generate 3D models from text prompts or reference images using the [Hyper3D Rodin](https://hyper3d.ai) API and import them directly into Blender via Claude.

---

## Installation

Install alongside `mcp-blender-bridge` in the same virtualenv:

```bash
pip install mcp-blender-bridge-hyper3d
```

Set your API key (**never hardcoded** — always via env var):

```bash
export HYPER3D_API_KEY="your-key-here"
```

Get a key by signing up at **https://hyper3d.ai**.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `HYPER3D_API_KEY` | Yes (at call time) | — | Bearer token for the Rodin API |
| `BLENDER_BRIDGE_CACHE_DIR` | No | `~/.cache/mcp-blender-bridge/assets/hyper3d` | Local cache root for downloaded models |

---

## Available Tools

| Tool | Description |
|---|---|
| `hyper3d_status` | Check plugin status and whether the API key is configured |
| `hyper3d_generate_text` | Generate a 3D model from a text prompt |
| `hyper3d_generate_image` | Generate a 3D model from a reference image |
| `hyper3d_poll` | Poll generation status with exponential backoff |
| `hyper3d_import` | Download completed model and import it into Blender |

### Typical workflow

```
1. hyper3d_generate_text(prompt="a wooden chair with curved legs")
   → returns task_uuid

2. hyper3d_poll(task_uuid=..., max_wait=300)
   → polls until done

3. hyper3d_import(task_uuid=..., import_format="glb")
   → downloads GLB + imports into active Blender scene
```

---

## Notes

- This plugin has **zero telemetry**. No usage data is sent anywhere except the Rodin API.
- The API key is checked at **call time**, not at server startup, so the bridge can start without the key and display a clear error when a generation tool is invoked.
- Downloaded models are cached locally. Re-importing the same `task_uuid` reuses the cached file.
