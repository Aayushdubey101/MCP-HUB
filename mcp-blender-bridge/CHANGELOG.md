# Changelog

All notable changes to **mcp-blender-bridge** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [SemVer](https://semver.org/).

<!-- ## [Unreleased] -->

<!-- --- -->


## [0.4.1] — 2026-05-23

### Added
- **Asset cache** (`asset_cache.py`) — SHA-256 content-addressed cache for downloaded 3D assets; stale entries pruned on startup; env-configurable path.
- **Headless Blender launcher** (`headless_blender.py`) — `--launch-blender` flag spawns `blender --background`, waits for port-readiness with timeout, and shuts down cleanly on exit.

### Quality
- Total test count: **207** (core + all plugins).  Coverage: **90%**.
- `pyproject.toml` bumped to `0.4.1`; `uv.lock` regenerated.

---

## [0.3.1] — 2026-05-09

### Added
- **PolyHaven plugin** (`mcp-blender-bridge-polyhaven`) — 5 tools for browsing and
  applying free PBR assets. No API key required. Async `httpx` downloads, env-configurable
  cache dir, full `respx`-mocked test suite (15 tests).
- **Hyper3D Rodin plugin** (`mcp-blender-bridge-hyper3d`) — 5 tools for AI text→3D
  and image→3D generation. BYO `HYPER3D_API_KEY`; key never embedded in code. Exponential
  backoff polling (5 → 60s cap). ZIP/GLTF download + Blender import. (44 tests).
- **Sketchfab plugin** (`mcp-blender-bridge-sketchfab`) — 4 tools for searching,
  previewing, and downloading 3D models from Sketchfab. Requires `SKETCHFAB_API_KEY`
  for downloads; search is keyless. ZIP extraction, GLTF cache, Blender import. (33 tests).
- **Streamable HTTP transport** — `--transport http --host 0.0.0.0 --port 8765` flag.
  Backed by `uvicorn` + `starlette`. `AuthMiddleware` enforces `BLENDER_BRIDGE_AUTH_TOKEN`
  (Bearer token) — server refuses to start in HTTP mode without the env var set.
- **Blender addon**: `cmd_import_3d_model` command handler supporting GLB (GLTF),
  FBX, OBJ, and STL import. Handles Blender 3.x/4.x API differences.
- **`.env.example`** updated with all new env vars: HTTP auth token, plugin keys,
  asset cache dir.

### Fixed
- PolyHaven and Hyper3D `tools.py` used a direct `blender_bridge` import at module
  level, causing `ModuleNotFoundError` when running plugin tests in isolation. Fixed
  via `TYPE_CHECKING` guard (import is now analysis-only; `Any` used at runtime).

### Quality
- Total test count: **268** (176 core + 15 PolyHaven + 44 Hyper3D + 33 Sketchfab).
- All tests green, zero telemetry, zero hardcoded keys verified.

---

## [0.3.0] — 2026-05-08

### Added
- `blender_render_image` — synchronous render with inline PNG preview, EEVEE / EEVEE_NEXT / CYCLES / WORKBENCH engines, override-and-restore semantics for engine and Cycles samples, configurable timeout up to 1 hour.
- Wire-protocol versioning. `BRIDGE_PROTOCOL_VERSION = "1.0"` shipped on both server and addon. Mismatch returns a structured error from `blender_ping` with an upgrade hint.
- JSON structured logging via `BLENDER_BRIDGE_LOG_FORMAT=json`. Pipe directly into log infrastructure; no `print()` anywhere.
- Read-only mode via `BLENDER_BRIDGE_READ_ONLY=true`. All `destructiveHint: true` tools refuse to run; read tools work normally. Useful for shared / demo instances.
- Persistent socket mode via `BLENDER_BRIDGE_PERSISTENT=true`. Reuses one TCP connection across all tool calls (saves the per-call handshake), serializes concurrent callers with `asyncio.Lock`, and reconnects automatically on broken pipe. Addon-side `_handle_client` now loops over newline-delimited commands per connection (backward-compatible with per-call clients).
- Plugin discovery via standard `importlib.metadata` entry points on the `blender_bridge.plugins` group. Plugins are separately-installable packages that satisfy the `BlenderBridgePlugin` Protocol (`name`, `version`, `register(mcp, client, *, read_only)`). Bad imports and bad-shape plugins are logged and skipped — one bad plugin never brings the server down. New `mcp-blender-bridge --list-plugins` CLI flag enumerates installed plugins.
- `Dockerfile` (multi-stage, uv-based) and `docker-compose.yml` for headless / render-farm deployments.
- `docs/ARCHITECTURE.md` covering process model, transport, threading inside Blender, response shape, and extensibility.

### Changed
- Bumped server version to `0.3.0` to reflect the Tier 2 feature set.

### Quality
- 176 tests passing, 89% coverage.
- CI matrix: Python 3.10 / 3.11 / 3.12.

## [0.2.0] — 2026-05-07

### Added
- `blender_get_object_info` — full object detail with type-specific data (mesh stats, light energy, camera focal length).
- `blender_get_viewport_screenshot` — inline PNG of the active 3D viewport, OpenGL-rendered.
- `blender_set_material` — Principled BSDF, RGBA + metallic + roughness + optional emission.
- `blender_add_light` — POINT / SUN / SPOT / AREA with per-type parameters validated.
- `blender_set_camera` — location + aim target + focal length, optional set-active.

### Quality
- Pytest suite + GitHub Actions CI matrix (Python 3.10 / 3.11 / 3.12).

## [0.1.0] — 2026-05-05

### Added
- Initial MCP server with stdio transport.
- 7 core tools: `blender_ping`, `blender_get_scene_info`, `blender_list_objects`,
  `blender_create_primitive`, `blender_transform_object`, `blender_delete_object`,
  `blender_execute_python`.
- Blender addon (`blender_addon/mcp_blender_bridge.py`) with N-panel start/stop control.
- Pydantic v2 input validation, `extra="forbid"` on every tool input model.
- Async TCP client (`asyncio.open_connection`).
- All four MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) on every tool.
- **Zero telemetry**, **zero hardcoded third-party keys** — by policy, verified by `grep`.
