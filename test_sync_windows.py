"""Test script to invoke watercooler_v1_sync directly on Windows."""
import asyncio
import sys
from pathlib import Path

# Add src to path so imports work
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import the internal function, not the decorated version
from watercooler_mcp.server import _require_context, get_git_sync_manager_from_context

async def main():
    """Test the sync tool directly."""
    print("Testing watercooler_v1_sync logic...")
    print(f"CWD: {Path.cwd()}")

    code_path = "."

    # Step 1: Test path resolution
    print(f"\nResolving code_path: {code_path!r}")
    error, context = _require_context(code_path)

    if error:
        print(f"ERROR: {error}")
        return

    if context is None:
        print("ERROR: Unable to resolve code context")
        return

    print(f"✓ Context resolved:")
    print(f"  - Code root: {context.code_root}")
    print(f"  - Threads dir: {context.threads_dir}")

    # Step 2: Test git sync manager
    print(f"\nGetting git sync manager...")
    sync = get_git_sync_manager_from_context(context)

    if not sync:
        print("ERROR: Async sync unavailable")
        return

    print(f"✓ Git sync manager obtained")

    # Step 3: Get status
    print(f"\nGetting async status...")
    status = sync.get_async_status()

    print("\n=== ASYNC STATUS ===")
    for key, value in status.items():
        print(f"  {key}: {value}")
    print("====================\n")

if __name__ == "__main__":
    asyncio.run(main())
