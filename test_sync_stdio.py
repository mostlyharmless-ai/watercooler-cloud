"""Test sync via stdio transport (simulates Claude Code client)."""
import asyncio
import json
import sys
import subprocess
from pathlib import Path

async def main():
    """Simulate Claude Code calling watercooler_v1_sync via stdio."""
    print("Testing stdio transport (simulates Claude Code client)...")
    print(f"CWD: {Path.cwd()}\n")

    # Start the MCP server as a subprocess (same as Claude Code does)
    print("Starting MCP server: python -m watercooler_mcp")

    server = subprocess.Popen(
        [sys.executable, "-m", "watercooler_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
        env={
            **dict(os.environ),
            "WATERCOOLER_AGENT": "Claude@Code",
        }
    )

    print("✓ Server started\n")

    try:
        # Send initialize request (required by MCP protocol)
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        }

        print("Sending initialize request...")
        server.stdin.write(json.dumps(init_request) + "\n")
        server.stdin.flush()

        # Read response
        print("Waiting for initialize response...")
        response_line = server.stdout.readline()
        print(f"✓ Got response: {response_line[:100]}...\n")

        # Now call watercooler_v1_sync
        sync_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "watercooler_v1_sync",
                "arguments": {
                    "code_path": str(Path.cwd()),
                    "action": "status"
                }
            }
        }

        print("Sending watercooler_v1_sync request...")
        print(f"  code_path: {Path.cwd()}")
        print(f"  action: status\n")

        print("--- If this hangs, we've found the bug ---\n")

        server.stdin.write(json.dumps(sync_request) + "\n")
        server.stdin.flush()

        # Try to read response with timeout
        print("Waiting for sync response (10s timeout)...")

        import threading
        response_container = []

        def read_response():
            try:
                line = server.stdout.readline()
                response_container.append(line)
            except Exception as e:
                response_container.append(f"ERROR: {e}")

        reader_thread = threading.Thread(target=read_response)
        reader_thread.daemon = True
        reader_thread.start()
        reader_thread.join(timeout=10.0)

        if reader_thread.is_alive():
            print("\n✗ HUNG! No response after 10 seconds")
            print("This confirms the stdio transport bug on Windows")

            # Check if server is still alive
            if server.poll() is None:
                print("Server process is still running (tool executed but response not sent)")
            else:
                print(f"Server process died with code: {server.returncode}")

        elif response_container:
            response = response_container[0]
            if response.startswith("ERROR"):
                print(f"\n✗ Read error: {response}")
            else:
                print(f"\n✓ Got response!")
                print(f"\n=== RESPONSE ===\n{response}\n================\n")
        else:
            print("\n✗ No response received")

    finally:
        print("\nCleaning up...")
        server.terminate()
        try:
            server.wait(timeout=2)
        except:
            server.kill()


if __name__ == "__main__":
    import os
    asyncio.run(main())
