import pytest
from mcp_blender_bridge_polyhaven.plugin import PolyHavenPlugin

class MockMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, **kwargs):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator

class MockClient:
    pass

def test_plugin_registration():
    plugin = PolyHavenPlugin()
    assert plugin.name == "polyhaven"
    assert plugin.version == "0.1.0"
    
    mcp = MockMCP()
    client = MockClient()
    
    plugin.register(mcp, client)
    
    assert "polyhaven_status" in mcp.tools
    assert "polyhaven_categories" in mcp.tools
    assert "polyhaven_search" in mcp.tools
    assert "polyhaven_download" in mcp.tools
    assert "polyhaven_apply_texture" in mcp.tools
