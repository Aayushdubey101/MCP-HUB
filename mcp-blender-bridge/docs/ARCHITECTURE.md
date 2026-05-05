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
├── server.py          # Entry point — registers tool groups, calls mcp.run()
├── client.py          # BlenderClient — async TCP, one connection per command
├── schemas.py         # All Pydantic input models (single source of truth)
├── utils.py           # format_success / format_error / parse_blender_response
└── tools/
    ├── __init__.py    # Exports scene, objects, code modules
    ├── scene.py       # 5 read-only tools (ping, scene info, list, object info, screenshot)
    ├── objects.py     # 6 write tools (create, transform, delete, material, light, camera)
    └── code.py        # 1 escape-hatch tool (execute_python)

blender_addon/
└── mcp_blender_bridge.py   # Single-file Blender addon (drag-and-drop install)

tests/
├── test_schemas.py    # 47 schema validation tests — no Blender required
└── test_utils.py      # 12 utils tests — no Blender required
```

Each `tools/*.py` exposes one function: `register(mcp, client)`. `server.py`
calls all three. Adding a new tool group = add a file, call `register`.

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

**Timeout**: 30 s default, overridable via `BLENDER_BRIDGE_TIMEOUT` env var
(planned v0.3.0). Competitor hardcodes 180 s with no way to shorten it.

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

| Dimension | `ahujasid/blender-mcp` v1.5.5 | `MCP-Blender-Bridge` v0.2.0 |
|-----------|-------------------------------|------------------------------|
| **Telemetry** | Default-on (Supabase) | Zero — no code exists |
| **Input validation** | None (raw kwargs) | Pydantic v2, `extra="forbid"` |
| **Tool annotations** | None | All 4 hints on every tool |
| **Tests** | 0 | 59 (schemas + utils) |
| **CI** | None | GitHub Actions, Python 3.10/3.11/3.12 |
| **Async** | Synchronous `def` | `async def` throughout |
| **Architecture** | 1 file × 1185 lines | Modular package, no file > 250 lines |
| **Blender addon** | 1 file × 2635 lines | 1 file × ~430 lines |
| **Hardcoded secrets** | `RODIN_FREE_TRIAL_KEY` in source | None — BYO keys via env vars |
| **Error format** | English string `"Error: ..."` | Structured JSON `{"status":"error","message":"..."}` |
| **Tool count** | 22 (heavy on 3rd-party AI gen) | 12 core + plugin-extensible |
| **Material tool** | None (buried in PolyHaven) | `blender_set_material` (Principled BSDF) |
| **Light tool** | None | `blender_add_light` (POINT/SUN/SPOT/AREA) |
| **Camera tool** | None | `blender_set_camera` (aim-at-target) |
| **Viewport screenshot** | Yes | Yes (inline `Image` content) |
| **Object inspection** | Yes | Yes (mesh/light/camera type-specific) |
| **Render submission** | No | Planned v0.3.0 |
| **Plugin architecture** | Baked-in integrations | Planned v0.3.0 (opt-in packages) |
| **Docker / deploy** | No | Planned v0.3.0 |
| **HTTP transport** | stdio only | Planned v0.3.0 |

---

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `BLENDER_BRIDGE_HOST` | `127.0.0.1` | Blender addon TCP address |
| `BLENDER_BRIDGE_PORT` | `9876` | Blender addon TCP port |
| `BLENDER_BRIDGE_LOG_LEVEL` | `INFO` | Python logging level |

Planned for v0.3.0:
- `BLENDER_BRIDGE_TIMEOUT` — socket timeout (currently hardcoded 30 s)
- `BLENDER_BRIDGE_LOG_FORMAT` — `json` for structured log output
- `BLENDER_BRIDGE_READ_ONLY` — disable all `destructiveHint: true` tools

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
