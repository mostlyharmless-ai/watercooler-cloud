"""Test sync via FastMCP Client (this might hang on Windows)."""
import asyncio
from fastmcp import FastMCP
from pathlib import Path

async def main():
    """Test calling sync through FastMCP client (simulates real MCP usage)."""
    print("Testing via FastMCP Client...")
    print("This simulates how Claude Desktop would call the tool.")
    print(f"CWD: {Path.cwd()}\n")

    # Load the server
    print("Loading server from fastmcp.json...")
    try:
        # Use the config file we created
        from watercooler_mcp.server import mcp
        print(f"✓ Server loaded: {mcp.name}\n")
    except Exception as e:
        print(f"✗ Failed to load server: {e}")
        return

    # Create a client
    print("Creating FastMCP client...")
    # Note: This is a simplified test - real usage would involve stdio transport
    # For now, just test if we can call the tool directly on the server object

    print("\nCalling watercooler_v1_sync via tool call...")
    print("Action: status")
    print("Code path: .")
    print("\n--- If this hangs, we've found Bug 2 ---\n")

    try:
        # Call the tool through FastMCP's internal mechanism
        from fastmcp import Context

        # Create a fake context
        class FakeCtx:
            client_id = "test-client"

        # Get the tool
        tool = None
        for t in mcp._tools:
            if t.name == "watercooler_v1_sync":
                tool = t
                break

        if not tool:
            print("✗ Tool not found!")
            return

        print(f"Found tool: {tool.name}")

        # Call it (this goes through FastMCP's wrapper)
        result = await tool.run({
            "code_path": ".",
            "action": "status"
        })

        print("\n✓ Tool returned!")
        print(f"\n=== RESULT ===\n{result}\n==============\n")

    except Exception as e:
        print(f"\n✗ Tool call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
