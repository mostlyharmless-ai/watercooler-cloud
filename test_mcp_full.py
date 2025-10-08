#!/usr/bin/env python3
"""Comprehensive test of watercooler MCP server tools."""

import asyncio
from watercooler_mcp.server import mcp

async def test_all_tools():
    """Test all MCP tools."""

    print("\n" + "="*70)
    print("🧪 Testing Watercooler MCP Server - All Tools")
    print("="*70 + "\n")

    # Test 1: Health check
    print("1️⃣  watercooler_v1_health")
    print("-" * 70)
    result = await mcp._mcp_call_tool("watercooler_v1_health", {})
    print(result[1]['result'])
    print()

    # Test 2: Whoami
    print("2️⃣  watercooler_v1_whoami")
    print("-" * 70)
    result = await mcp._mcp_call_tool("watercooler_v1_whoami", {})
    print(result[1]['result'])
    print()

    # Test 3: List threads
    print("3️⃣  watercooler_v1_list_threads")
    print("-" * 70)
    result = await mcp._mcp_call_tool("watercooler_v1_list_threads", {})
    output = result[1]['result']
    # Truncate for readability
    lines = output.split('\n')[:15]
    print('\n'.join(lines))
    print("... (truncated)")
    print()

    # Test 4: Read the new thread
    print("4️⃣  watercooler_v1_read_thread (mcp-testing)")
    print("-" * 70)
    result = await mcp._mcp_call_tool("watercooler_v1_read_thread", {"topic": "mcp-testing"})
    output = result[1]['result']
    print(output[:400] + "..." if len(output) > 400 else output)
    print()

    # Test 5: Ack the thread
    print("5️⃣  watercooler_v1_ack (mcp-testing)")
    print("-" * 70)
    result = await mcp._mcp_call_tool("watercooler_v1_ack", {
        "topic": "mcp-testing",
        "title": "Test ack from MCP",
        "body": "Testing acknowledgment via MCP tools"
    })
    print(result[1]['result'])
    print()

    # Test 6: Generate index
    print("6️⃣  watercooler_v1_reindex")
    print("-" * 70)
    result = await mcp._mcp_call_tool("watercooler_v1_reindex", {})
    output = result[1]['result']
    lines = output.split('\n')[:20]
    print('\n'.join(lines))
    print("... (truncated)")
    print()

    print("="*70)
    print("✅ All MCP tools tested successfully!")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(test_all_tools())
