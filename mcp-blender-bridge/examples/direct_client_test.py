"""Direct test of the Blender client (no MCP layer).

Run this AFTER starting the Blender addon's bridge server to verify the
TCP connection works end-to-end.

Usage:
    uv run python examples/direct_client_test.py
"""

from __future__ import annotations

import asyncio

from blender_bridge.client import BlenderClient, BlenderConnectionError


async def main() -> None:
    client = BlenderClient()

    print("→ Pinging Blender...")
    try:
        ok = await client.ping()
        if not ok:
            print("✗ Blender did not respond. Is the addon running?")
            return
        print("✓ Blender is reachable.\n")
    except BlenderConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return

    print("→ Getting scene info...")
    response = await client.send_command("get_scene_info")
    print(f"  {response}\n")

    print("→ Creating a red cube at (3, 0, 0)...")
    response = await client.send_command(
        "create_primitive",
        {"primitive_type": "cube", "name": "DemoCube", "location": [3, 0, 0], "size": 2.0},
    )
    print(f"  {response}\n")

    print("→ Listing all MESH objects...")
    response = await client.send_command("list_objects", {"object_type": "MESH"})
    print(f"  {response}\n")

    print("→ Deleting DemoCube...")
    response = await client.send_command("delete_object", {"name": "DemoCube"})
    print(f"  {response}\n")

    print("✓ All commands succeeded.")


if __name__ == "__main__":
    asyncio.run(main())
