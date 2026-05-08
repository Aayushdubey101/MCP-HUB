# MCP-Blender-Bridge

> **Production-grade Blender automation over the Model Context Protocol.**
> Pydantic-validated • Zero telemetry • Async-native • Pytest-covered • Plugin-extensible
>
> Part of the [MCP-HUB](../README.md) project.

[![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![Tests](https://img.shields.io/badge/tests-149%20passing-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-89%25-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)]()
[![uv](https://img.shields.io/badge/managed%20by-uv-purple.svg)](https://docs.astral.sh/uv/)

---

## What this is

`mcp-blender-bridge` connects Blender 3D to any MCP-compatible AI assistant
(Claude Desktop, Claude Code, Cursor, Continue, Cline, …). After a one-time
setup, you tell the assistant what you want, and it drives Blender for you —
creating objects, applying materials, lighting the scene, framing cameras,
rendering. **The assistant takes the wheel; you watch it work.**

```
┌────────────────┐    MCP/stdio     ┌──────────────────┐    TCP/JSON    ┌──────────┐
│ Claude / IDE   │ ◄──────────────► │  Bridge server   │ ◄────────────► │ Blender  │
│ (your prompt)  │                  │  (this package)  │                │  addon   │
└────────────────┘                  └──────────────────┘                └──────────┘
```

Two halves:
- **Bridge server** (this Python package, run via `uv`) — speaks MCP to the AI client.
- **Blender addon** (`blender_addon/mcp_blender_bridge.py`) — runs inside Blender, executes commands on the main thread.

---

## Why use this instead of `ahujasid/blender-mcp`?

The `blender-mcp` project pioneered the space. We respect that. We're built
for a different audience: **studios, technical artists, and pipeline engineers
who need verifiable, auditable, production-grade tooling.**

| Dimension | `mcp-blender-bridge` (this) | `ahujasid/blender-mcp` |
|---|---|---|
| Telemetry | **None.** Zero phone-home. | Default-on Supabase telemetry |
| Input validation | Pydantic v2 with `extra="forbid"` everywhere | None — raw kwargs |
| Async runtime | Native `asyncio`, non-blocking | Synchronous `socket.recv` |
| Tests | **149 passing**, 89% coverage | None visible in repo |
| CI | GitHub Actions on Python 3.10 / 3.11 / 3.12 | None |
| Architecture | Modular package, ~8 files | Monolithic 1186-line `server.py` |
| Tool annotations | All 4 MCP hints on every tool | Mostly omitted |
| Read-only mode | `BLENDER_BRIDGE_READ_ONLY=true` | None |
| Structured logging | `BLENDER_BRIDGE_LOG_FORMAT=json` | Plain strings |
| Protocol versioning | `BRIDGE_PROTOCOL_VERSION="1.0"` enforced | None |
| Docker | `Dockerfile` + `docker-compose.yml` | None |
| Hardcoded third-party keys | **None** — bring your own | `RODIN_FREE_TRIAL_KEY` baked into source |
| Asset integrations | Plugin packages (opt-in, separately versioned) | Baked into core |

If telemetry, validation, tests, audit-ability, or air-gapped deployment matter
to you, this is the one to use.

---

## Tools (v0.3.0)

13 first-class tools, each with Pydantic-validated input and full MCP
annotations.

### Inspection (read-only)

| Tool | Purpose |
|------|---------|
| `blender_ping` | Confirm Blender + addon reachable, returns versions and protocol |
| `blender_get_scene_info` | Scene name, frame range, render engine, object count |
| `blender_list_objects` | List objects, optional filter by type (`MESH`, `LIGHT`, `CAMERA`, …) |
| `blender_get_object_info` | Full per-object detail (transform, dimensions, materials, mesh/light/camera specifics) |
| `blender_get_viewport_screenshot` | Inline PNG of the active viewport |

### Authoring (destructive — disabled in read-only mode)

| Tool | Purpose |
|------|---------|
| `blender_create_primitive` | Cube / sphere / cylinder / cone / plane / torus / monkey |
| `blender_transform_object` | Set location / rotation / scale (any subset) |
| `blender_delete_object` | Remove by name (idempotent) |
| `blender_set_material` | Principled BSDF: RGBA, metallic, roughness, optional emission |
| `blender_add_light` | POINT / SUN / SPOT / AREA with per-type parameters |
| `blender_set_camera` | Location, aim target, focal length, set-active |
| `blender_render_image` | Render a frame; returns metadata + inline PNG preview |
| `blender_execute_python` | Power-user escape hatch (`bpy` available, set `result` to return) |

---

## Quick start

### Prerequisites

- **Blender 3.0+** (3.6, 4.0, 4.2 LTS all tested)
- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** package manager
  ```powershell
  # Windows
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### 1 · Install dependencies

From `mcp-blender-bridge/`:

```bash
uv sync
```

### 2 · Install the Blender addon

1. Open Blender → **Edit → Preferences → Add-ons → Install…**
2. Pick `blender_addon/mcp_blender_bridge.py`
3. Tick the checkbox next to **"Development: MCP Blender Bridge"**
4. In the 3D viewport press **N** → **MCP** tab → **▶ Start MCP Bridge**

You should see in Blender's system console:

```
[MCP Bridge] Listening on 127.0.0.1:9876
```

### 3 · Smoke-test the server

```bash
uv run mcp-blender-bridge
```

It will block on stdin — that's correct (MCP stdio transport).
Press Ctrl-C. A clean run with no errors means you're good.

For a full interactive test, use the official inspector:

```bash
npx @modelcontextprotocol/inspector uv run mcp-blender-bridge
```

### 4 · Wire it into your AI client

Pick the one(s) you use. Restart the client after editing config.

#### Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json` (Windows) or
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

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

#### Claude Code (CLI)

`~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uv",
      "args": ["--directory", "C:/claude_work/MCP-HUB/mcp-blender-bridge", "run", "mcp-blender-bridge"]
    }
  }
}
```

Or one-shot register:

```bash
claude mcp add blender -- uv --directory C:/claude_work/MCP-HUB/mcp-blender-bridge run mcp-blender-bridge
```

#### Cursor

`.cursor/mcp.json` in your workspace (or global at `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "blender": {
      "command": "uv",
      "args": ["--directory", "C:/claude_work/MCP-HUB/mcp-blender-bridge", "run", "mcp-blender-bridge"]
    }
  }
}
```

#### Continue / Cline / any other MCP client

Same shape — `command: uv`, `args: [--directory <path>, run, mcp-blender-bridge]`. See your client's MCP docs for the exact config file.

### 5 · Drive Blender with natural language

With Blender open, addon enabled, **Start MCP Bridge** running, and your AI
client restarted — just ask. The assistant will pick the right tools, validate
inputs, and execute. You sit back.

```
You: Build a still-life scene. Put a glossy red sphere on a matte grey plane,
     light it with a warm key light from the right and a cool rim from behind,
     frame a 50mm camera looking down at 30°, then render at 720p with EEVEE.
```

The assistant will call, in order:
`blender_ping` → `blender_create_primitive(plane)` → `blender_set_material(plane, grey)` →
`blender_create_primitive(sphere)` → `blender_set_material(sphere, red, roughness=0.1)` →
`blender_add_light(spot, warm)` → `blender_add_light(area, cool)` →
`blender_set_camera(loc, target, lens=50)` → `blender_render_image(engine=EEVEE)`.

---

## Configuration

Every option is an environment variable. None are required; all have
sensible defaults. Copy `.env.example` to `.env` to customize.

| Variable | Default | Purpose |
|---|---|---|
| `BLENDER_BRIDGE_HOST` | `127.0.0.1` | Where the Blender addon is listening |
| `BLENDER_BRIDGE_PORT` | `9876` | Same — match the N-panel value |
| `BLENDER_BRIDGE_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `BLENDER_BRIDGE_LOG_FORMAT` | `text` | `text` for humans, `json` for log infra |
| `BLENDER_BRIDGE_READ_ONLY` | `false` | `true` disables every destructive tool |

### Read-only mode (safe demos)

```bash
BLENDER_BRIDGE_READ_ONLY=true uv run mcp-blender-bridge
```

`blender_create_primitive`, `blender_render_image`, `blender_execute_python`, etc.
will all return a structured "read-only mode" error. Inspection tools still work.

### JSON logging (log infra)

```bash
BLENDER_BRIDGE_LOG_FORMAT=json uv run mcp-blender-bridge
```

Each line is a single JSON object — ship straight to Loki / Datadog / CloudWatch.

---

## Docker

For headless / render-farm setups. The container talks to a Blender instance
running on the host:

```bash
docker compose up --build
```

The Blender addon must be running on the host (`host.docker.internal:9876`
inside the container). On Linux the compose file already maps
`host.docker.internal` to `host-gateway`.

---

## Project layout

```
mcp-blender-bridge/
├── src/blender_bridge/
│   ├── server.py              # MCP entry point; env-var configuration
│   ├── client.py              # Async TCP client + protocol versioning
│   ├── schemas.py             # Pydantic v2 input models
│   ├── utils.py               # format_error / format_success / read-only guard
│   ├── _log_formatter.py      # JSON log formatter (separate to avoid import-time setup)
│   └── tools/
│       ├── scene.py           # 5 read-only tools
│       ├── objects.py         # 6 destructive object/material/light/camera tools
│       ├── render.py          # blender_render_image
│       └── code.py            # blender_execute_python (escape hatch)
├── blender_addon/
│   └── mcp_blender_bridge.py  # Install this in Blender
├── tests/                     # 149 tests, 89% coverage
├── docs/
│   └── ARCHITECTURE.md        # Process model, threading, response shape, extensibility
├── examples/
│   └── direct_client_test.py  # Drive the bridge without an MCP client
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml             # uv / build configuration
├── .env.example
├── CHANGELOG.md
├── TASK.md                    # Roadmap to plugin-rich v1.0
└── README.md
```

For deeper internals see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Development

```bash
uv sync --extra dev          # install dev deps
uv run pytest                # 149 tests, ~2s
uv run pytest --cov=src      # with coverage
uv run ruff check src/       # lint
uv run ruff format src/      # format
uv run mypy src/             # type-check
```

CI runs the same matrix on every push (Python 3.10 / 3.11 / 3.12).

---

## Roadmap

The full plan lives in [`TASK.md`](TASK.md). High level:

- **v0.4.0** — Persistent socket + reconnect, plugin loader, PolyHaven plugin.
- **v0.5.0** — Hyper3D Rodin plugin (BYO key), Sketchfab plugin, streamable HTTP transport.
- **v0.6.0** — Headless / `--background` Blender control, asset cache.
- **v1.0.0** — All 22 competitor tools matched (core + plugins), comparison-table green on every row.

---

## Troubleshooting

**"Could not connect to Blender at 127.0.0.1:9876"**
Open Blender, Preferences → Add-ons, enable *MCP Blender Bridge*, then in the
3D viewport's N-panel → MCP tab → click **▶ Start MCP Bridge**.

**"Port already in use"**
Change the port in the addon N-panel and set
`BLENDER_BRIDGE_PORT` to match.

**"Tools don't show up in Claude Desktop"**
Verify the absolute path in `claude_desktop_config.json`, then fully quit and
relaunch Claude Desktop (Cmd-Q / right-click tray icon → Quit).

**"Render timed out"**
Pass `timeout_seconds=600` (or higher) on the `blender_render_image` call for
heavy Cycles renders. Default is 300s.

**"Protocol version mismatch"**
Re-install `blender_addon/mcp_blender_bridge.py` in Blender — your addon and
server are out of sync.

---

## License

MIT — see the parent [MCP-HUB LICENSE](../LICENSE).
