"""Test sync via stdio transport with diagnostic instrumentation.

This test enables WATERCOOLER_DIAGNOSTICS to log each git operation
to stderr, helping identify exactly which git call causes the stdio hang.
"""
import asyncio
import json
import sys
import subprocess
import os
from pathlib import Path

async def main():
    """Simulate Claude Code calling watercooler_v1_sync via stdio with diagnostics."""
    print("Testing stdio transport with DIAGNOSTICS enabled...")
    print(f"CWD: {Path.cwd()}\n")

    # Start the MCP server as a subprocess (same as Claude Code does)
    print("Starting MCP server: python -m watercooler_mcp")
    print("Diagnostics: WATERCOOLER_DIAGNOSTICS=1 (logs to stderr)\n")

    env = dict(os.environ)
    env["WATERCOOLER_AGENT"] = "Claude@Code"
    env["WATERCOOLER_DIAGNOSTICS"] = "1"  # Enable diagnostic logging

    server = subprocess.Popen(
        [sys.executable, "-m", "watercooler_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,  # Capture diagnostic logs
        text=True,
        bufsize=1,  # Line buffered
        env=env
    )

    print("✓ Server started\n")

    # Thread to read and print stderr (diagnostic logs) in real-time
    import threading

    def read_stderr():
        """Read and print diagnostic logs from stderr."""
        for line in server.stderr:
            print(f"  [STDERR] {line.rstrip()}")

    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()

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

        print("=" * 60)
        print("Sending watercooler_v1_sync request...")
        print(f"  code_path: {Path.cwd()}")
        print(f"  action: status")
        print("=" * 60)
        print("\nWatch the [STDERR] diagnostic logs below to see")
        print("which git operation starts but never ends (=hang point):\n")

        server.stdin.write(json.dumps(sync_request) + "\n")
        server.stdin.flush()

        # Try to read response with timeout
        print("Waiting for sync response (30s timeout)...\n")

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
        reader_thread.join(timeout=30.0)

        if reader_thread.is_alive():
            print("\n" + "=" * 60)
            print("✗ HUNG! No response after 30 seconds")
            print("=" * 60)
            print("\nLook at the diagnostic logs above.")
            print("The last 'GIT_OP_START' without a matching 'GIT_OP_END'")
            print("is the git operation that causes the stdio hang!")

            # Check if server is still alive
            if server.poll() is None:
                print("\nServer process is still running (tool executed but response not sent)")
            else:
                print(f"\nServer process died with code: {server.returncode}")

        elif response_container:
            response = response_container[0]
            if response.startswith("ERROR"):
                print(f"\n✗ Read error: {response}")
            else:
                print(f"\n✓ Got response!")
                print(f"\n=== RESPONSE ===\n{response}\n================\n")
                print("The stdio hang is FIXED! 🎉")
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
    asyncio.run(main())
