<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:2E3192,100:1BFFFF&height=220&section=header&text=MCP-HUB&fontSize=64&fontColor=ffffff&animation=fadeIn&fontAlignY=36&desc=A%20Curated%20Hub%20of%20Model%20Context%20Protocol%20Servers&descSize=18&descAlignY=58" width="100%"/>

<br/>

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=1000&color=1BAEFF&center=true&vCenter=true&width=680&lines=One+hub%2C+many+MCP+servers+%F0%9F%A7%A9;AI+Agents+%E2%80%A2+3D+Animation+%E2%80%A2+Cybersecurity;Blockchain+%E2%80%A2+Big+Data;Open+source+%E2%80%A2+MIT+%E2%80%A2+free+for+everyone" alt="MCP-HUB" />

<br/><br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-1BFFFF.svg?style=for-the-badge)](LICENSE)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-2E3192.svg?style=for-the-badge)](CONTRIBUTING.md)
![Roadmap](https://img.shields.io/badge/roadmap-1%2F5%20shipped-yellow?style=for-the-badge)

**A curated hub of Model Context Protocol (MCP) servers — one shipped, four more landing by end of 2026.**

</div>

---

## Projects

### MCP-Blender-Bridge — ✅ Released (v0.4.1)

> **Repo: [Aayushdubey101/Blender-MCP](https://github.com/Aayushdubey101/Blender-MCP)** · [Full docs](https://github.com/Aayushdubey101/Blender-MCP#readme)

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
git clone https://github.com/Aayushdubey101/Blender-MCP.git
cd Blender-MCP
uv sync
# install blender_addon/mcp_blender_bridge.py in Blender, start the bridge
uv run mcp-blender-bridge
```

---

## Roadmap — rest shipping by end of 2026

| Project | Domain | Status |
|---------|--------|--------|
| MCP-Blender-Bridge | 3D Animation | ✅ Released |
| MCP-Motion-Capture | 3D Animation | 🔨 In progress |
| MCP-Agent-Monitor | AI Agents | 📋 Planned |
| MCP-Threat-Intel | Cybersecurity | 📋 Planned |
| MCP-Smart-Contract-Analyzer | Blockchain | 📋 Planned |

**Goal: all four remaining servers complete by end of 2026.** Star / watch to get notified when they drop.

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

## License

Released under the **[MIT License](LICENSE)** — free for anyone to use, modify, and distribute, commercial or personal. No strings attached. Just keep the copyright notice.

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:1BFFFF,100:2E3192&height=120&section=footer" width="100%"/>

**Made with ❤️ by [Aayush Dubey](https://github.com/Aayushdubey101)**

[Star ⭐](https://github.com/Aayushdubey101/MCP-HUB) • [Issues 🐛](https://github.com/Aayushdubey101/MCP-HUB/issues) • [Discussions 💬](https://github.com/Aayushdubey101/MCP-HUB/discussions)

</div>
