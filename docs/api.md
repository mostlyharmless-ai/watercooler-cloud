# Python API Reference

Complete reference for using watercooler-collab as a Python library.

**Note:** For MCP server integration (AI agents automatically using watercooler tools), see [MCP Server Guide](./mcp-server.md). This document covers the **Python library API** for programmatic usage in scripts and custom applications.

## Table of Contents

- [Installation](#installation)
- [Public API](#public-api)
  - [File Operations](#file-operations)
  - [Thread Operations](#thread-operations)
  - [Header Operations](#header-operations)
  - [Locking](#locking)
- [Module Overview](#module-overview)
- [Usage Examples](#usage-examples)
- [Type Hints](#type-hints)

## Installation

```bash
# Development installation
git clone https://github.com/mostlyharmless-ai/watercooler-collab.git
cd watercooler-collab
pip install -e .

# Future: PyPI installation (not yet published)
# pip install watercooler-collab
```

## Public API

The public API is exposed through the main `watercooler` module:

```python
from watercooler import (
    read,
    write,
    thread_path,
    bump_header,
    AdvisoryLock,
    __version__,
)
```

### File Operations

#### `read(p: Path) -> str`

Read a file and return its contents as a string.

**Parameters:**
- `p` (Path): Path to the file to read

**Returns:**
- str: File contents

**Example:**
```python
from pathlib import Path
from watercooler import read

content = read(Path("thread.md"))
print(content)
```

---

#### `write(p: Path, s: str) -> None`

Write a string to a file, creating parent directories if needed.

**Parameters:**
- `p` (Path): Path to the file to write
- `s` (str): Content to write

**Returns:**
- None

**Example:**
```python
from pathlib import Path
from watercooler import write

write(Path(".watercooler/my-thread.md"), "# My Thread\n\nContent here")
```

**Notes:**
- Automatically creates parent directories with `parents=True, exist_ok=True`
- Uses UTF-8 encoding
- Overwrites existing files

---

### Thread Operations

#### `thread_path(topic: str, threads_dir: Path) -> Path`

Get the file path for a thread topic.

**Parameters:**
- `topic` (str): Thread topic identifier (e.g., "feature-auth")
- `threads_dir` (Path): Directory containing threads

**Returns:**
- Path: Full path to the thread markdown file

**Example:**
```python
from pathlib import Path
from watercooler import thread_path

path = thread_path("feature-auth", Path(".watercooler"))
# Returns: Path(".watercooler/feature-auth.md")

# Handles special characters
path = thread_path("fix/bug-123", Path(".watercooler"))
# Returns: Path(".watercooler/fix-bug-123.md")  # slashes converted to dashes
```

**Notes:**
- Strips whitespace from topic
- Converts "/" to "-" for filesystem safety
- Always returns a `.md` file extension

---

### Header Operations

#### `bump_header(text: str, *, status: str | None = None, ball: str | None = None) -> str`

Update Status and/or Ball fields in a thread header.

**Parameters:**
- `text` (str): Thread file contents
- `status` (str, optional): New status value (e.g., "in-review", "closed")
- `ball` (str, optional): New ball owner (e.g., "Claude", "Codex", "Team")

**Returns:**
- str: Updated thread contents with modified header

**Example:**
```python
from pathlib import Path
from watercooler import read, write, bump_header

# Read thread
content = read(Path(".watercooler/feature-auth.md"))

# Update status
content = bump_header(content, status="in-review")

# Update ball
content = bump_header(content, ball="Claude")

# Update both
content = bump_header(content, status="closed", ball="Team")

# Write back
write(Path(".watercooler/feature-auth.md"), content)
```

**Header Format:**
```markdown
Title: Feature Auth
Status: open
Ball: codex
Updated: 2025-10-07T10:00:00Z

# Feature Auth

Thread content here...
```

**Notes:**
- Header is separated from body by double newline (`\n\n`)
- Case-insensitive field matching (e.g., "status:" or "Status:")
- Preserves header/body structure
- If field doesn't exist, it's appended to header

---

### Locking

#### `AdvisoryLock`

Context manager for advisory file locking with TTL and timeout.

**Constructor:**
```python
AdvisoryLock(
    path: Path,
    *,
    ttl: int | None = None,
    timeout: int | None = None,
    force_break: bool = False
)
```

**Parameters:**
- `path` (Path): Path to lock file (typically `.{topic}.lock`)
- `ttl` (int, optional): Seconds before lock is considered stale (default: 30 or `WCOOLER_LOCK_TTL`)
- `timeout` (int, optional): Seconds to wait for lock before giving up (default: unlimited)
- `force_break` (bool): If True, break existing locks immediately (default: False)

**Environment Variables:**
- `WCOOLER_LOCK_TTL`: Default TTL in seconds (default: 30)
- `WCOOLER_LOCK_POLL`: Polling interval in seconds (default: 0.1)

**Example - Basic Usage:**
```python
from pathlib import Path
from watercooler import AdvisoryLock, read, write, bump_header

lock_path = Path(".watercooler/.feature-auth.lock")

with AdvisoryLock(lock_path, timeout=5):
    # Lock acquired - safe to modify thread
    content = read(Path(".watercooler/feature-auth.md"))
    content = bump_header(content, status="in-review")
    write(Path(".watercooler/feature-auth.md"), content)
# Lock automatically released
```

**Example - Custom TTL:**
```python
# Short-lived lock for quick operations
with AdvisoryLock(lock_path, ttl=10, timeout=2):
    # Do work
    pass
```

**Example - Force Break (Debugging):**
```python
# Break stuck locks (use with caution!)
with AdvisoryLock(lock_path, force_break=True):
    # Lock will be forcibly broken if it exists
    pass
```

**Lock File Format:**
```
pid=12345 time=2025-10-07T10:00:00Z user=agent cwd=/Users/agent/project
```

**Notes:**
- Locks are **advisory only** - processes must cooperate
- Stale locks (exceeding TTL) are automatically removed
- Lock file contains PID, timestamp, user, and working directory for debugging
- Use `timeout=0` to fail immediately if lock cannot be acquired
- Locks are automatically released when exiting the context manager

**Attributes:**
- `path` (Path): Lock file path
- `ttl` (int): Time-to-live in seconds
- `timeout` (int | None): Timeout in seconds (None = unlimited)
- `force_break` (bool): Whether to break existing locks
- `acquired` (bool): Whether lock was successfully acquired

**Methods:**
- `acquire() -> bool`: Manually acquire lock (returns True if successful)
- `release() -> None`: Manually release lock

---

## Module Overview

The watercooler package consists of several internal modules:

### `watercooler.fs`
File system operations: read, write, thread_path, backup utilities

### `watercooler.header`
Thread header parsing and manipulation: bump_header

### `watercooler.lock`
Advisory file locking: AdvisoryLock

### `watercooler.commands`
High-level command functions: init_thread, append_entry, say, ack, handoff, etc.

### `watercooler.cli`
Command-line interface implementation

### `watercooler.config`
Configuration resolution: threads_dir, templates_dir discovery

### `watercooler.templates`
Template loading and placeholder filling

### `watercooler.agents`
Agent registry and canonicalization

### `watercooler.metadata`
Thread metadata extraction: status, ball, title, updated timestamp

**Note:** Only the functions and classes listed in the [Public API](#public-api) section are part of the stable public API. Internal modules may change between versions.

---

## Usage Examples

### Example 1: Read and Update a Thread

```python
from pathlib import Path
from watercooler import read, write, bump_header, thread_path, AdvisoryLock

threads_dir = Path(".watercooler")
topic = "feature-auth"

# Get thread path
t_path = thread_path(topic, threads_dir)
lock_path = threads_dir / f".{topic}.lock"

# Update thread with locking
with AdvisoryLock(lock_path, timeout=5):
    content = read(t_path)
    content = bump_header(content, status="in-review", ball="Claude")
    write(t_path, content)

print(f"Updated {t_path}")
```

### Example 2: Create a Simple Thread

```python
from pathlib import Path
from watercooler import write, thread_path

threads_dir = Path(".watercooler")
topic = "quick-note"

# Create thread content
content = """Title: Quick Note
Status: open
Ball: Team
Updated: 2025-10-07T10:00:00Z

# Quick Note

This is a simple thread created programmatically.
"""

# Write thread
t_path = thread_path(topic, threads_dir)
write(t_path, content)

print(f"Created thread: {t_path}")
```

### Example 3: Safely Modify Multiple Threads

```python
from pathlib import Path
from watercooler import read, write, bump_header, AdvisoryLock

def update_thread_status(threads_dir: Path, topic: str, new_status: str):
    """Update a thread's status with proper locking."""
    from watercooler import thread_path

    t_path = thread_path(topic, threads_dir)
    lock_path = threads_dir / f".{topic}.lock"

    with AdvisoryLock(lock_path, ttl=30, timeout=5):
        if not t_path.exists():
            raise FileNotFoundError(f"Thread {topic} not found")

        content = read(t_path)
        content = bump_header(content, status=new_status)
        write(t_path, content)

    print(f"✓ Updated {topic} → {new_status}")

# Update multiple threads
threads_dir = Path(".watercooler")
for topic in ["feature-auth", "bug-fix-123", "docs-update"]:
    try:
        update_thread_status(threads_dir, topic, "closed")
    except FileNotFoundError as e:
        print(f"✗ {e}")
```

### Example 4: Using with the Commands Module

For higher-level operations, use the commands module directly:

```python
from pathlib import Path
from watercooler.commands import init_thread, append_entry, say

threads_dir = Path(".watercooler")

# Initialize a new thread
init_thread(
    "new-feature",
    threads_dir=threads_dir,
    title="New Feature Implementation",
    status="open",
    ball="codex",
)

# Add a structured entry
append_entry(
    "new-feature",
    threads_dir=threads_dir,
    agent="Claude",
    role="critic",
    title="Design Review",
    entry_type="Decision",
    body="Approach looks good. Ready to implement.",
)

# Quick team note
say(
    "new-feature",
    threads_dir=threads_dir,
    agent="Team",
    role="pm",
    title="Timeline",
    body="Target: end of sprint",
)
```

**Note:** The commands module is not part of the stable public API, but is available for advanced usage.

---

## Type Hints

All public API functions include type hints for better IDE support:

```python
from pathlib import Path
from watercooler import read, write, thread_path, bump_header, AdvisoryLock

# Type hints are included
content: str = read(Path("thread.md"))
write(Path("out.md"), content)
path: Path = thread_path("topic", Path(".watercooler"))
updated: str = bump_header(content, status="open")

# Context manager works with type checkers
with AdvisoryLock(Path(".lock"), timeout=5) as lock:
    pass
```

---

## See Also

### Core Documentation
- [Integration Guide](./integration.md) - Complete integration tutorial with MCP, CLI, and Python API patterns
- [MCP Server Guide](./mcp-server.md) - MCP tool reference for AI agent integration
- [Environment Variables](./ENVIRONMENT_VARS.md) - Configuration reference

### Getting Started
- [Quickstart Guide](./QUICKSTART.md) - 5-minute setup
- [Claude Code Setup](./CLAUDE_CODE_SETUP.md) - Configure Claude Code
- [Claude Desktop Setup](./CLAUDE_DESKTOP_SETUP.md) - Configure Claude Desktop

### Reference
- [CLI Reference](../README.md) - Command-line interface documentation
- [Use Cases](USE_CASES.md) - Real-world usage patterns
- [Troubleshooting](./TROUBLESHOOTING.md) - Common issues and solutions
- [Contributing](./CONTRIBUTING.md) - Contribution guidelines

### Project
- [Roadmap](../ROADMAP.md) - Project status and future plans
- [GitHub Repository](https://github.com/mostlyharmless-ai/watercooler-collab)
