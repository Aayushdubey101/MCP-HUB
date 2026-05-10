class PolyHavenPlugin:
    name = "polyhaven"
    version = "0.1.0"

    def register(self, mcp, client, *, read_only: bool = False) -> None:
        from .tools import register_tools
        register_tools(mcp, client, read_only=read_only)
