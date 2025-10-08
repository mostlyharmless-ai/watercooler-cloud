#!/usr/bin/env python3
"""Test script to verify MCP tools are properly exposed."""

import asyncio
from watercooler_mcp.server import mcp

async def main():
    """List all registered tools."""
    tools = await mcp.get_tools()

    print(f"\n{'='*60}")
    print(f"Watercooler MCP Server - Registered Tools")
    print(f"{'='*60}\n")
    print(f"Total tools: {len(tools)}\n")

    for name, tool in tools.items():
        print(f"📋 {name}")
        desc = tool.description or "(no description)"
        # Truncate long descriptions
        if len(desc) > 100:
            desc = desc[:97] + "..."
        print(f"   {desc}")
        print()

if __name__ == "__main__":
    asyncio.run(main())
