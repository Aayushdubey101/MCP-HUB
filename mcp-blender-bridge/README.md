# MCP-Blender-Bridge

> **Bridge Blender 3D with AI assistants via the Model Context Protocol.**
> Part of the [MCP-HUB](../README.md) project.

[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)]()
[![Package Manager](https://img.shields.io/badge/uv-managed-purple.svg)]()
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)]()

---

## What is this?

`mcp-blender-bridge` lets AI assistants (Claude Desktop, Claude Code, etc.) control Blender 3D through natural language. It has two halves:

1. **MCP server** (this Python package) — speaks the Model Context Protocol to the AI client.
2. **Blender addon** (`blender_addon/mcp_blender_bridge.py`) — runs inside Blender and executes the commands.

They communicate over a local TCP socket.

```
┌──────────────┐      MCP/stdio      ┌──────────────┐    TCP/JSON    ┌──────────┐
│ Claude / IDE │ ◄─────────────────► │  This server │ ◄────────────► │ Blender  │
└──────────────┘                     └──────────────┘                └──────────┘
```

---

## Available Tools (v0.1.0)

| Tool | Purpose |
|------|---------|
| `blender_ping` | Check that Blender + addon are reachable |
| `blender_get_scene_info` | Scene name, frame range, object count, render engine |
| `blender_list_objects` | List objects (optionally filtered by type) |
| `blender_create_primitive` | Add cube / sphere / cylinder / cone / plane / torus / monkey |
| `blender_transform_object` | Set location / rotation / scale of an object |
| `blender_delete_object` | Remove an object by name |
| `blender_execute_python` | Run arbitrary `bpy` code (advanced escape hatch) |

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** package manager — install with:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- **Blender 3.0+**

### 1. Install dependencies

From the `mcp-blender-bridge/` directory:

```bash
uv sync
```

This creates `.venv/` and installs everything from `pyproject.toml`.

### 2. Install the Blender addon

1. Open Blender → **Edit → Preferences → Add-ons → Install...**
2. Select `blender_addon/mcp_blender_bridge.py`
3. Enable the checkbox next to **"Development: MCP Blender Bridge"**
4. In the 3D Viewport, press **N** to open the sidebar → **MCP** tab
5. Click **▶ Start MCP Bridge**

You should see `[MCP Bridge] Listening on 127.0.0.1:9876` in Blender's system console.

### 3. Test the server locally

```bash
uv run mcp-blender-bridge
```

Or with the official MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run mcp-blender-bridge
```

### 4. Connect to Claude Desktop

Add this to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "blender": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\claude_work\\MCP-HUB\\mcp-blender-bridge",
        "run",
        "mcp-blender-bridge"
      ]
    }
  }
}
```

Restart Claude Desktop. You should see the Blender tools appear.

---

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `BLENDER_BRIDGE_HOST` | `127.0.0.1` | Host where Blender addon listens |
| `BLENDER_BRIDGE_PORT` | `9876` | Port where Blender addon listens |
| `BLENDER_BRIDGE_LOG_LEVEL` | `INFO` | Python logging level |

---

## Project Layout

```
mcp-blender-bridge/
├── src/blender_bridge/
│   ├── __init__.py
│   ├── server.py           # MCP server entry point + tool definitions
│   ├── client.py           # Async TCP client for the Blender addon
│   ├── schemas.py          # Pydantic input models
│   ├── utils.py            # Response formatting + error handling
│   └── tools/              # (reserved for future modular tool packages)
├── blender_addon/
│   └── mcp_blender_bridge.py  # Install this inside Blender
├── tests/                  # Pytest suite
├── docs/                   # Architecture, API docs
├── examples/               # Usage examples
├── pyproject.toml          # uv / build configuration
├── .python-version         # uv pins Python 3.11
└── README.md
```

---

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Lint
uv run ruff check src/

# Format
uv run ruff format src/

# Type check
uv run mypy src/

# Run tests
uv run pytest
```

---

## Roadmap (per MCP-HUB schedule)

- [x] **v0.1.0** — Foundation: 7 core tools, Blender addon, stdio transport
- [ ] **v0.2.0** — Materials & shaders, lighting setup, camera control
- [ ] **v0.3.0** — Render job submission and monitoring
- [ ] **v0.4.0** — Asset library integration
- [ ] **v0.5.0** — Animation timeline manipulation
- [ ] **v1.0.0** — Production-ready release (Q2 2026)

---

## Troubleshooting

**"Cannot reach Blender"** — Open Blender, install/enable the addon, click *Start MCP Bridge* in the N-panel.

**Port already in use** — Change the port in the addon's N-panel and set `BLENDER_BRIDGE_PORT` to match.

**Tools not showing in Claude Desktop** — Verify the absolute path in `claude_desktop_config.json` and restart Claude Desktop completely.

---

## License

MIT — see the parent [MCP-HUB LICENSE](../LICENSE).
