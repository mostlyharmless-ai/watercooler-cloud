"""Test script to invoke watercooler_v1_sync directly on Windows."""
import asyncio
import sys
from pathlib import Path

# Add src to path so imports work
sys.path.insert(0, str(Path(__file__).parent / "src"))

from watercooler_mcp.server import force_sync

class FakeContext:
    """Minimal context object for testing."""
    client_id = "test-client"

async def main():
    """Test the sync tool directly."""
    print("Testing watercooler_v1_sync...")
    print(f"CWD: {Path.cwd()}")

    # Call the sync tool directly
    result = force_sync(
        ctx=FakeContext(),
        code_path=".",
        action="status"
    )

    print("\n=== RESULT ===")
    print(result)
    print("==============\n")

if __name__ == "__main__":
    asyncio.run(main())
