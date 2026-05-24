# Architecture — MCP-Blender-Bridge

> Internal design reference. Covers process topology, wire protocol, tool
> organisation, and the decisions that differentiate us from `ahujasid/blender-mcp`.

---

## Process topology

```
┌─────────────────────────────────┐
│  Claude Desktop / Claude Code   │  ← MCP client
└────────────────┬────────────────┘
                 │  stdio (MCP protocol, JSON-RPC 2.0)
                 ▼
┌─────────────────────────────────┐
│  mcp-blender-bridge             │  ← this package
│  src/blender_bridge/server.py   │
│  FastMCP + async tool handlers  │
└────────────────┬────────────────┘
                 │  TCP 127.0.0.1:9876
                 │  newline-delimited JSON
                 ▼
┌─────────────────────────────────┐
│  Blender 3.0+                   │
│  blender_addon/                 │
│  mcp_blender_bridge.py          │
│  (daemon TCP thread + bpy ops)  │
└─────────────────────────────────┘
```

Two separate processes, one TCP socket between them. The MCP server speaks to
Claude via stdio; the Blender addon listens on TCP inside Blender's process.

---

## Package layout

```
src/blender_bridge/
├── server.py              # Entry point — env-var config, registers tool groups, mcp.run()
├── client.py              # BlenderClient — async TCP, per-call and persistent modes
├── schemas.py             # All Pydantic input models (single source of truth)
├── utils.py               # format_success / format_error / parse_blender_response / check_read_only
├── asset_cache.py         # SHA-256 content-addressable cache + stale pruning (Phase 8)
├── headless_blender.py    # Blender --background launcher + port-readiness wait (Phase 9)
├── plugins.py             # Plugin loader via importlib.metadata entry points
├── _log_formatter.py      # JsonFormatter — structured JSON log output
└── tools/
    ├── __init__.py           # Exports scene, objects, render, code modules
    ├── scene.py              # 5 read-only tools (ping, scene info, list, object info, screenshot)
    ├── objects.py            # 6 write tools (create, transform, delete, material, light, camera)
    ├── render.py             # 1 render tool (render_image — inline PNG preview)
    └── code.py               # 1 escape-hatch tool (execute_python)

blender_addon/
└── mcp_blender_bridge.py   # Single-file Blender addon (drag-and-drop install)

plugins/
├── polyhaven/              # mcp-blender-bridge-polyhaven (5 tools, no key needed)
├── hyper3d/               # mcp-blender-bridge-hyper3d (5 tools, HYPER3D_API_KEY)
└── sketchfab/             # mcp-blender-bridge-sketchfab (4 tools, SKETCHFAB_API_KEY)

tests/                      # 204 core tests
├── test_schemas.py         # Schema validation (no Blender required)
├── test_utils.py           # Utils + read-only helpers
├── test_client.py          # Async TCP client (mocked asyncio)
├── test_server_features.py # JsonFormatter, env-var parsing
├── test_transport.py       # HTTP transport + AuthMiddleware
├── test_asset_cache.py     # SHA-256 cache (Phase 8)
├── test_headless_blender.py # Headless launcher (Phase 9)
├── test_tools_objects.py   # 20 object tool tests
├── test_tools_scene.py     # 18 scene tool tests
├── test_tools_render.py    # 7 render tool tests
└── test_tools_code.py      # 6 code tool tests
```

Each `tools/*.py` exposes one function: `register(mcp, client, *, read_only=False)`. `server.py`
calls all four. Adding a new tool group = add a file, call `register`.

---

## Wire protocol

### MCP layer (server ↔ Claude)

Standard MCP over stdio. FastMCP handles serialisation. Tools return either:
- `str` — rendered as `TextContent`
- `Image` — rendered as `ImageContent` (used by `blender_get_viewport_screenshot`)

### Bridge layer (server ↔ addon)

Newline-delimited JSON over a plain TCP socket.

**Request** (server → addon):
```json
{"command": "get_object_info", "params": {"name": "Cube"}}
```

**Success response** (addon → server):
```json
{"status": "success", "result": {"name": "Cube", "type": "MESH", ...}}
```

**Error response** (addon → server):
```json
{"status": "error", "message": "ValueError: Object 'Cube' not found in scene."}
```

The server's `parse_blender_response()` in `utils.py` unpacks the envelope and
raises `BlenderConnectionError` on error, keeping tool handlers clean.

### Connection model

`BlenderClient.send_command()` opens a fresh TCP connection for every call:

```
open_connection → write request → readline response → close
```

**Why per-call instead of persistent?** Persistent connections are faster but
require reconnection logic, heartbeats, and state tracking. For v0.2.0 the
overhead is negligible (loopback TCP). A `BlenderClientPool` keyed by
`host:port` is planned for v0.3.0 when render-farm multi-instance support lands.

**Timeout**: 30 s default per command; render tool accepts `timeout_seconds` per-call (default 300 s, configurable up to 3600 s). Competitor hardcodes 180 s with no way to shorten it.

---

## Blender addon threading model

Blender's `bpy` API is single-threaded — all ops must run on the main thread.
The addon bridges that constraint with a queue + timer pattern:

```
Background daemon thread          Blender main thread
──────────────────────            ───────────────────
accept() loop
  │
  └─ per-client thread
       │
       ├─ parse JSON
       ├─ _command_queue.put(     ←──────────────────────────────┐
       │    handler, params,                                      │
       │    response_holder,      every 50 ms:                    │
       │    done_event)           bpy.app.timers fires            │
       │                         _drain_command_queue()           │
       └─ done_event.wait(60s)        │                           │
            │                        ├─ dequeue item  ───────────┘
            │                        ├─ call handler(params)
            │                        └─ response_holder["response"] = ...
            │                             done_event.set()
            ▼
       send JSON response
```

This is the only correct approach for bpy from threads. The competitor uses the
same pattern (`bpy.app.timers.register`) but dispatches per-command instead of
draining a queue — functionally equivalent, marginally more timer overhead.

---

## Input validation

Every tool input is a `StrictModel(BaseModel)` subclass:

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,   # strips accidental whitespace
        validate_assignment=True,    # validates on mutation too
        extra="forbid",             # rejects unknown fields immediately
    )
```

Field-level constraints (enforced before the command ever reaches Blender):

| Schema | Key constraints |
|--------|----------------|
| `CreatePrimitiveInput` | `size: float` gt=0, le=1000; `name` max 63 chars |
| `TransformObjectInput` | at least one of location/rotation/scale must be non-None (checked in tool) |
| `SetMaterialInput` | metallic/roughness ge=0, le=1; emission_strength le=1,000,000 |
| `AddLightInput` | energy gt=0; spot_size ge=1, le=180 (degrees, validated before radians conversion) |
| `SetCameraInput` | lens ge=1, le=5000 mm |
| `ViewportScreenshotInput` | max_size ge=64, le=4096 |
| `ExecutePythonInput` | code max 20,000 chars |

The competitor accepts raw kwargs with no constraints. Sending `size=0` or
`metallic=99` reaches Blender and fails with an opaque bpy exception. Ours
fails at the schema layer with a structured, actionable error before any socket
traffic occurs.

---

## Tool annotations

Every tool declares all four MCP hints:

```python
@mcp.tool(
    name="blender_delete_object",
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,   # MCP client can warn user
        "idempotentHint": True,    # safe to retry; missing object → success
        "openWorldHint": False,
    },
)
```

This lets Claude Desktop, Claude Code, and any MCP client:
- Show a confirmation prompt before destructive tools
- Safely retry idempotent tools on transient failure
- Filter read-only tools for safe/demo modes

The competitor's tools have no annotations — clients must assume worst-case.

---

## Zero-telemetry guarantee

No analytics, tracking, or phone-home code exists anywhere in this package.
Verify yourself:

```bash
grep -r "telemetry\|analytics\|track\|supabase\|mixpanel\|segment" src/
# Expected: no output
```

The competitor wraps every tool with `@telemetry_tool("name")` and sends
usage data (including prompts and code) to Supabase by default. Their telemetry
can be disabled via `DISABLE_TELEMETRY=true` but is opt-out, not opt-in.

Studios under NDA, government contractors, and regulated industries cannot use
default-on telemetry. MCP-Blender-Bridge has nothing to disable.

---

## Comparison table

| Dimension | `ahujasid/blender-mcp` v1.5.5 | `MCP-Blender-Bridge` v0.3.1 |
|-----------|-------------------------------|------------------------------|
| **Telemetry** | Default-on (Supabase) | Zero — no code exists |
| **Input validation** | None (raw kwargs) | Pydantic v2, `extra="forbid"` |
| **Tool annotations** | None | All 4 hints on every tool |
| **Tests** | 0 | 204 core + 92 plugin = **296 total** |
| **CI** | None | GitHub Actions, Python 3.10/3.11/3.12 |
| **Async** | Synchronous `def` | `async def` throughout |
| **Architecture** | 1 file × 1185 lines | Modular package, no file > 250 lines |
| **Blender addon** | 1 file × 2635 lines | 1 file × ~430 lines |
| **Hardcoded secrets** | `RODIN_FREE_TRIAL_KEY` in source | None — BYO keys via env vars |
| **Error format** | English string `"Error: ..."` | Structured JSON `{"status":"error","message":"..."}` |
| **Tool count** | 22 (heavy on 3rd-party AI gen) | 13 core + 14 plugin (27 total) |
| **Material tool** | None (buried in PolyHaven) | `blender_set_material` (Principled BSDF) |
| **Light tool** | None | `blender_add_light` (POINT/SUN/SPOT/AREA) |
| **Camera tool** | None | `blender_set_camera` (aim-at-target) |
| **Viewport screenshot** | Yes | Yes (inline `Image` content) |
| **Object inspection** | Yes | Yes (mesh/light/camera type-specific) |
| **Render submission** | No | `blender_render_image` (EEVEE/CYCLES, inline preview) |
| **Read-only mode** | No | `BLENDER_BRIDGE_READ_ONLY=true` disables all writes |
| **Structured logging** | No | `BLENDER_BRIDGE_LOG_FORMAT=json` |
| **Protocol versioning** | No | `BRIDGE_PROTOCOL_VERSION="1.0"` — mismatch warns on ping |
| **Plugin architecture** | Baked-in integrations | Entry-point system — 3 plugins shipped |
| **Asset cache** | None | SHA-256 content-addressable, stale pruning on startup |
| **HTTP transport** | stdio only | `--transport http` with Bearer auth |
| **Headless Blender** | None | `--launch-blender` auto-starts `blender --background` |
| **PolyHaven** | Baked-in | `pip install mcp-blender-bridge-polyhaven` (5 tools) |
| **Hyper3D/Rodin** | Baked-in (free trial key) | `pip install mcp-blender-bridge-hyper3d` (BYO key) |
| **Sketchfab** | None | `pip install mcp-blender-bridge-sketchfab` (4 tools) |

---

## Read-only mode

Set `BLENDER_BRIDGE_READ_ONLY=true` (or `1` or `yes`) to disable all destructive
tools at startup. The server still registers them — they return an actionable error
rather than being hidden — so tool discovery works normally.

```python
# utils.py — all destructive tools call this at the top of their handler
if err := check_read_only(read_only):
    return err  # {"status": "error", "message": "Server is in read-only mode..."}
```

Useful for: demo environments, CI pipelines that only need inspection tools,
shared Blender instances where writes should be gated.

---

## Protocol versioning

`BRIDGE_PROTOCOL_VERSION = "1.0"` is defined in both `client.py` and
`blender_addon/mcp_blender_bridge.py`. On `blender_ping`, the addon returns the
version it was built with:

```json
{"status": "success", "result": {"pong": true, "protocol_version": "1.0", ...}}
```

If the server's version ≠ addon's version, `blender_ping` returns an error
directing the user to update the addon. Old addons that predate versioning return
`"protocol_version": "legacy"` (treated as a soft warning, not a hard failure).

---

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `BLENDER_BRIDGE_HOST` | `127.0.0.1` | Blender addon TCP address |
| `BLENDER_BRIDGE_PORT` | `9876` | Blender addon TCP port |
| `BLENDER_BRIDGE_LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| `BLENDER_BRIDGE_LOG_FORMAT` | `text` | Set to `json` for structured log output (log aggregators, CI) |
| `BLENDER_BRIDGE_READ_ONLY` | `false` | Set to `true`/`1`/`yes` — disables all destructive tools |
| `BLENDER_BRIDGE_PERSISTENT` | `false` | Reuse a single TCP connection across all calls (faster, reconnects on drop) |
| `BLENDER_BRIDGE_AUTH_TOKEN` | — | **Required** when using `--transport http`. Bearer token for all requests. |
| `BLENDER_BRIDGE_CACHE_DIR` | `~/.cache/mcp-blender-bridge/assets` | Shared asset cache for all plugins. |
| `BLENDER_LAUNCH_TIMEOUT` | `30` | Seconds to wait for Blender addon to open port when `--launch-blender` is used. |
| `BLENDER_PATH` | — | Override Blender executable location for `--launch-blender`. |
| `HYPER3D_API_KEY` | — | API key for Hyper3D Rodin plugin (BYO, never embedded). |
| `SKETCHFAB_API_KEY` | — | API token for Sketchfab plugin downloads. |
| `MCPHUB_READ_ONLY` | — | Short alias for `BLENDER_BRIDGE_READ_ONLY`. |
| `MCPHUB_HOST` | — | Short alias — overrides `BLENDER_BRIDGE_HOST` if set. |
| `MCPHUB_PORT` | — | Short alias — overrides `BLENDER_BRIDGE_PORT` if set. |
| `MCPHUB_MODAL_TOOLS` | `true` | Set to `false`/`0` to disable the 5 modal mesh-editing tools. |

---

## v0.5 additions (Sprint 1–6)

### Chat Panel (`blender_addon/chat_panel/`)

A multi-provider in-Blender chat panel, shipping as a sub-package of the Blender addon:

| Module | Purpose |
|--------|---------|
| `providers/base.py` | ABC `Provider` + `ChatEvent` union (TextDelta, ToolUseStart/Args/End, Stop) |
| `providers/anthropic.py` | Anthropic SDK streaming wrapper |
| `providers/openai_compat.py` | OpenAI SDK wrapper (also covers GPT-4o, LM Studio, Ollama) |
| `providers/gemini.py` | google-genai SDK streaming wrapper |
| `providers/registry.py` | `get_provider(name, api_key, base_url)` factory |
| `tool_format.py` | `pydantic_to_{anthropic,openai,gemini}` — convert StrictModel → provider schema |
| `properties.py` | `ChatMessage` + `ChatState` Blender PropertyGroups |
| `preferences.py` | `MCPHUBPreferences` AddonPreferences (provider, model, key, realtime mode) |
| `panel.py` | `MCPHUB_PT_chat` N-panel in VIEW_3D sidebar |
| `operators.py` | Send / Clear / StartRecording / StopRecording operators |
| `threading_bridge.py` | Queue-based worker↔main-thread bridge; `_main_thread_tick` timer |
| `tool_dispatcher.py` | Routes `tool_use` events to `_impl` functions; ghost cursor integration |
| `depsgraph_listener.py` | Buffers scene diffs (200-entry deque); `flush_diffs()` / `format_diffs()` |
| `ghost_cursor.py` | GPU draw handler — translucent ring at active tool target |
| `macro_recorder.py` | Start/stop recording; depsgraph diff→steps; `infer_schema()`; persist JSON |
| `realtime_monitor.py` | Optional continuous scene-polling timer; cost estimate in prefs |

### Threading invariant

```
Worker thread (asyncio):          Main thread (bpy.app.timers @50ms):
  provider.chat() stream            Drain _text_q → history[-1].content
  ↓ TextDelta → _text_q            Drain _tool_q → asyncio.run(dispatch())
  ↓ ToolUseEnd → _tool_q                           ↓ send_command() (TCP)
  block on _response_q ←───────── put result on _response_q
  ↓ Stop(tool_use) → loop again   Drain _stop_q → clear is_streaming
  ↓ Stop(end_turn) → done
```

`bpy.*` is **never** accessed from the worker thread.

### Modal tools (`src/blender_bridge/tools/modal.py`)

Five new tools for mesh editing. EXEC_DEFAULT (deterministic): extrude, loop_cut, bevel.
INVOKE_DEFAULT (interactive, requires window): knife_cut, sculpt.
In headless/TCP mode, knife falls back to `bpy.ops.mesh.bisect`.

---

## Adding a new tool (contributor guide)

1. **Add the input schema** to `src/blender_bridge/schemas.py` as a
   `StrictModel` subclass with field-level constraints.

2. **Add the tool function** to the appropriate `tools/*.py` module inside its
   `register()` function. Use `async def`, return `format_success()` or
   `format_error()`, annotate all 4 hints.

3. **Add the command handler** to `blender_addon/mcp_blender_bridge.py` and
   register it in `COMMAND_HANDLERS`.

4. **Add at least one test** to `tests/test_schemas.py` covering the new
   schema's validation constraints.

5. **Update the README** "Available Tools" table.

The quality gate checklist lives in `.competitive-intel/session-checklist.md`.
