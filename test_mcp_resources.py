#!/usr/bin/env python3
"""Test MCP resources including the new instructions."""

import asyncio
from watercooler_mcp.server import mcp

async def test_resources():
    """Test MCP resources."""

    print("\n" + "="*70)
    print("📚 Testing Watercooler MCP Resources")
    print("="*70 + "\n")

    # List all resources
    print("Available Resources:")
    print("-" * 70)
    resources = await mcp._list_resources()
    for resource in resources:
        print(f"📄 {resource.uri}")
        if hasattr(resource, 'name') and resource.name:
            print(f"   Name: {resource.name}")
        if hasattr(resource, 'description') and resource.description:
            print(f"   Description: {resource.description}")
        print()

    # Read the instructions resource
    print("Reading watercooler://instructions:")
    print("=" * 70)
    result = await mcp._read_resource("watercooler://instructions")

    # The result contains content
    for item in result:
        if hasattr(item, 'text'):
            print(item.text)
        elif hasattr(item, 'blob'):
            print(f"[Binary content: {len(item.blob)} bytes]")

    print("\n" + "="*70)
    print("✅ Resources test complete!")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(test_resources())
