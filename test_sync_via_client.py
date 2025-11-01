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
        # Get the list of tools
        tools = mcp.get_tools()
        print(f"Server has {len(tools)} tools")

        sync_tool = None
        for tool in tools:
            if tool.name == "watercooler_v1_sync":
                sync_tool = tool
                break

        if not sync_tool:
            print("✗ watercooler_v1_sync not found!")
            return

        print(f"✓ Found tool: {sync_tool.name}")

        # Call it through FastMCP's internal _call_tool method
        # This is how the MCP protocol actually invokes tools
        print("\nCalling via _call_tool...")
        result = await mcp._call_tool(
            name="watercooler_v1_sync",
            arguments={
                "code_path": ".",
                "action": "status"
            }
        )

        print("\n✓ Tool returned!")
        print(f"\n=== RESULT ===")
        print(f"Type: {type(result)}")
        print(f"Content: {result}")
        print(f"==============\n")

    except Exception as e:
        print(f"\n✗ Tool call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
