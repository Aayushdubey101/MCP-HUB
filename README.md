# MCP-HUB

<div align="center">

![MCP-HUB Banner](https://img.shields.io/badge/MCP-HUB-blue?style=for-the-badge)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)](CONTRIBUTING.md)

**A Curated Hub of Model Context Protocol (MCP) Servers**

*Spanning AI Agents • 3D Animation • Cybersecurity • Blockchain • Big Data*

</div>

---

## Projects

### MCP-Blender-Bridge — ✅ Released (v0.4.1)

> [`mcp-blender-bridge/`](mcp-blender-bridge/) · [Full docs](mcp-blender-bridge/README.md)

Production-grade MCP server that connects Blender 3D to any MCP-compatible AI assistant (Claude Desktop, Claude Code, Antigravity, Cursor, Cline, …).

**13 core tools** — ping, scene info, object list/inspect, viewport screenshot, create/transform/delete objects, materials, lights, camera, render, execute Python.

**3 opt-in plugins** — PolyHaven (free PBR assets), Hyper3D Rodin (text/image → 3D), Sketchfab (3D model library).

| | |
|---|---|
| Tests | 207 passing, 90% coverage |
| Telemetry | Zero |
| Secrets | None hardcoded — BYO keys |
| Transport | stdio (default) · HTTP + Bearer auth |
| Deploy | Docker included |

```bash
# quick start
git clone https://github.com/Aayushdubey101/MCP-HUB.git
cd MCP-HUB/mcp-blender-bridge
uv sync
# install blender_addon/mcp_blender_bridge.py in Blender, start the bridge
uv run mcp-blender-bridge
```

---

## Coming Soon

| Project | Domain | Status |
|---------|--------|--------|
| MCP-Motion-Capture | 3D Animation | Planned |
| MCP-Agent-Monitor | AI Agents | Planned |
| MCP-Threat-Intel | Cybersecurity | Planned |
| MCP-Smart-Contract-Analyzer | Blockchain | Planned |

Star / watch the repo to get notified when they drop.

---

## Contributing

1. Fork → branch → PR
2. Check open [Issues](https://github.com/Aayushdubey101/MCP-HUB/issues) for "good first issue"
3. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines

---

## Resources

- [MCP Specification](https://spec.modelcontextprotocol.io)
- [Anthropic MCP Docs](https://docs.anthropic.com/mcp)
- [Awesome MCP](https://github.com/punkpeye/awesome-mcp)

---

<div align="center">

**Made with ❤️ by [Aayush Dubey](https://github.com/Aayushdubey101)**

[Star ⭐](https://github.com/Aayushdubey101/MCP-HUB) • [Issues 🐛](https://github.com/Aayushdubey101/MCP-HUB/issues) • [Discussions 💬](https://github.com/Aayushdubey101/MCP-HUB/discussions)

</div>
