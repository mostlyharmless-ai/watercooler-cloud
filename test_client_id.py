#!/usr/bin/env python3
"""Test if we can get client_id from Context."""

import asyncio
from watercooler_mcp.server import mcp
from fastmcp import Context

# Add a test tool to check client_id
@mcp.tool(name="watercooler_v1_test_client_info")
async def test_client_info(ctx: Context) -> str:
    """Test tool to check what client information is available."""
    return f"""
Client Info Available:
- client_id: {ctx.client_id or 'Not available'}
- request_id: {ctx.request_id}
- session_id: {ctx.session_id}
"""

async def test():
    """Test calling the tool to see what info we get."""
    print("Testing client info extraction...")
    print("\nNote: client_id might be None when called locally")
    print("It should be populated when called via MCP protocol\n")

    # Try to call it (will fail without proper context but we can see the tool exists)
    tools = await mcp.get_tools()
    if "watercooler_v1_test_client_info" in tools:
        print("✅ Test tool registered successfully")
        print("\nTool will provide client_id when called through MCP protocol")
    else:
        print("❌ Test tool not found")

if __name__ == "__main__":
    asyncio.run(test())
