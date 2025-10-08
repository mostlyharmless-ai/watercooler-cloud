#!/usr/bin/env python3
"""Test script to call MCP tools through the server."""

import asyncio
from watercooler_mcp.server import mcp

async def main():
    """Test calling MCP tools."""

    print("\n" + "="*60)
    print("Testing Watercooler MCP Tools")
    print("="*60 + "\n")

    # Test 1: Health check
    print("📋 Test 1: watercooler_v1_health")
    print("-" * 40)
    result = await mcp._mcp_call_tool("watercooler_v1_health", {})
    print(result)
    print()

    # Test 2: Whoami
    print("📋 Test 2: watercooler_v1_whoami")
    print("-" * 40)
    result = await mcp._mcp_call_tool("watercooler_v1_whoami", {})
    print(result)
    print()

    # Test 3: List threads
    print("📋 Test 3: watercooler_v1_list_threads")
    print("-" * 40)
    result = await mcp._mcp_call_tool("watercooler_v1_list_threads", {})
    print(result[:500] + "..." if len(result) > 500 else result)
    print()

if __name__ == "__main__":
    asyncio.run(main())
