# Watercooler MCP Server

FastMCP server that exposes watercooler-collab tools to AI agents through the Model Context Protocol (MCP).

## Overview

The watercooler MCP server allows AI agents (like Claude, Codex, etc.) to naturally discover and use watercooler collaboration tools without manual CLI commands. All tools are namespaced as `watercooler_v1_*` for provider compatibility.

**Current Status:** Production Ready (Phase 1A/1B/2A complete)
**Version:** v0.2.0 + Phase 2A git sync

## Installation

Install watercooler-collab with MCP support:

```bash
pip install -e .[mcp]
```

This installs `fastmcp>=2.0` and creates the `watercooler-mcp` command.

## Quick Start

**For complete setup instructions, see [QUICKSTART.md](./QUICKSTART.md)**

### Configuration Examples

**Codex (`~/.codex/config.toml`):**
```toml
[mcp_servers.watercooler]
command = "python3"
args = ["-m", "watercooler_mcp"]

[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "Codex"
```

**Claude Desktop:**
```json
{
  "mcpServers": {
    "watercooler": {
      "command": "python3",
      "args": ["-m", "watercooler_mcp"],
      "env": {
        "WATERCOOLER_AGENT": "Claude"
      }
    }
  }
}
```

**Claude Code (`.mcp.json`):**
```json
{
  "mcpServers": {
    "watercooler": {
      "command": "python3",
      "args": ["-m", "watercooler_mcp"],
      "env": {
        "WATERCOOLER_AGENT": "Claude"
      }
    }
  }
}
```

## Environment Variables

### WATERCOOLER_AGENT (Required)
Your agent identity (e.g., "Claude", "Codex"). Set in MCP config.

### WATERCOOLER_DIR (Optional)
Explicit threads directory override.

**Resolution order (Phase 1B):**
1. `WATERCOOLER_DIR` env var (highest priority)
2. Upward search from CWD for existing `.watercooler/` (stops at git root or HOME)
3. Fallback: `{CWD}/.watercooler` (for auto-creation)

**The upward search is automatic** - works from any subdirectory in your repo without configuration.

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):
```json
{
  "mcpServers": {
    "watercooler": {
      "command": "/opt/anaconda3/envs/watercooler/bin/watercooler-mcp",
      "env": {
        "WATERCOOLER_AGENT": "Claude",
        "WATERCOOLER_DIR": "/Users/jay/projects/watercooler-test/.watercooler"
      }
    }
  }
}
```

**Cline** (`.vscode/settings.json` or VS Code settings):
```json
{
  "mcp.servers": {
    "watercooler": {
      "command": "/opt/anaconda3/envs/watercooler/bin/watercooler-mcp",
      "args": [],
      "env": {
        "WATERCOOLER_AGENT": "Codex",
        "WATERCOOLER_DIR": "${workspaceFolder}/.watercooler"
      }
    }
  }
}
```

**Note:** Adjust paths for your system:
- Use `which watercooler-mcp` to find the command path
- Use absolute paths for `WATERCOOLER_DIR` or relative to project root

## Available Tools

All tools are namespaced as `watercooler_v1_*`:

### Diagnostic Tools

#### `watercooler_v1_health`
Check server health and configuration.

**Returns:** Server version, agent identity, threads directory status

**Example output:**
```
Watercooler MCP Server v0.1.0
Status: Healthy
Agent: Codex
Threads Dir: /path/to/.watercooler
Threads Dir Exists: True
```

#### `watercooler_v1_whoami`
Get your resolved agent identity.

**Returns:** Current agent name

**Example output:**
```
You are: Codex
```

### Thread Management Tools

#### `watercooler_v1_list_threads`
List all threads with ball ownership and NEW markers.

**Parameters:**
- `open_only` (bool | None): Filter by status (True=open only, False=closed only, None=all)
- `limit` (int): Max threads (not yet implemented - returns all)
- `cursor` (str | None): Pagination cursor (not yet implemented)
- `format` (str): Output format - "markdown" (json support deferred)

**Returns:** Formatted thread list organized by:
- 🎾 Your Turn - Threads where you have the ball
- 🆕 NEW Entries - Threads with unread updates
- ⏳ Waiting on Others - Threads where others have the ball

#### `watercooler_v1_read_thread`
Read complete thread content.

**Parameters:**
- `topic` (str): Thread topic identifier (e.g., "feature-auth")
- `from_entry` (int): Starting entry index (not yet implemented - returns from start)
- `limit` (int): Max entries (not yet implemented - returns all)
- `format` (str): Output format - "markdown" (json support deferred)

**Returns:** Full markdown thread content with all entries

#### `watercooler_v1_say`
Add your response to a thread and flip the ball to your counterpart.

**Parameters:**
- `topic` (str): Thread topic identifier
- `title` (str): Entry title - brief summary
- `body` (str): Full entry content (markdown supported)
- `role` (str): Your role - planner, critic, implementer, tester, pm, scribe (default: implementer)
- `entry_type` (str): Entry type - Note, Plan, Decision, PR, Closure (default: Note)

**Returns:** Confirmation with new ball owner

**Example:**
```python
say("feature-auth", "Implementation complete", "All tests passing. Ready for review.", role="implementer")
```

#### `watercooler_v1_ack`
Acknowledge a thread without flipping the ball.

**Parameters:**
- `topic` (str): Thread topic identifier
- `title` (str): Optional acknowledgment title (default: "Ack")
- `body` (str): Optional acknowledgment message (default: "ack")

**Returns:** Confirmation (ball remains with current owner)

#### `watercooler_v1_handoff`
Hand off the ball to another agent.

**Parameters:**
- `topic` (str): Thread topic identifier
- `note` (str): Optional handoff message
- `target_agent` (str | None): Specific agent name (optional, uses counterpart if None)

**Returns:** Confirmation with new ball owner

**Example:**
```python
handoff("feature-auth", "Ready for your review", target_agent="Claude")
```

#### `watercooler_v1_set_status`
Update thread status.

**Parameters:**
- `topic` (str): Thread topic identifier
- `status` (str): New status (e.g., "OPEN", "IN_REVIEW", "CLOSED", "BLOCKED")

**Returns:** Confirmation message

#### `watercooler_v1_reindex`
Generate index summary of all threads.

**Returns:** Markdown index organized by:
- Actionable threads (where you have the ball)
- Open threads (waiting on others)
- In Review threads
- Closed threads (limited to 10 most recent)

## Configuration

### Environment Variables

- **`WATERCOOLER_AGENT`**: Your agent identity (default: "Agent")
  - Used when creating entries
  - Determines which threads show as "Your Turn"

- **`WATERCOOLER_DIR`**: Threads directory path (default: `./.watercooler`)
  - Can be absolute or relative path
  - Server auto-creates if it doesn't exist

### Deferred Features

Some features are available as parameters but deferred for future implementation (see [ROADMAP.md](../ROADMAP.md) for details):

- **JSON format**: `format` parameter accepts "json" but currently only "markdown" is supported
- **Pagination**: `limit` and `cursor` parameters are accepted but not yet implemented (returns all results)

These features will be implemented if real-world usage demonstrates the need.

## Usage Examples

### Example 1: Check Server Health

```python
# AI agent calls
health()

# Returns:
# Watercooler MCP Server v0.1.0
# Status: Healthy
# Agent: Codex
# Threads Dir: /path/to/.watercooler
# Threads Dir Exists: True
```

### Example 2: List Threads Where You Have the Ball

```python
# AI agent calls
list_threads(open_only=True)

# Returns organized list showing:
# - Threads where you have the ball (🎾)
# - Threads with NEW entries (🆕)
# - Threads waiting on others (⏳)
```

### Example 3: Respond to a Thread

```python
# AI agent reads thread
content = read_thread("feature-auth")

# AI agent responds
say(
    "feature-auth",
    "Implementation complete",
    "All unit tests passing. Integration tests added. Ready for code review.",
    role="implementer",
    entry_type="Note"
)

# Ball automatically flips to counterpart
```

### Example 4: Hand Off to Specific Team Member

```python
# AI agent hands off to specific reviewer
handoff(
    "feature-auth",
    "Security review needed for OAuth implementation",
    target_agent="SecurityBot"
)
```

## Troubleshooting

### Server Not Found

If `watercooler-mcp` command is not found:

```bash
# Check installation
pip list | grep watercooler-collab

# Reinstall with MCP extras
pip install -e .[mcp]

# Find command path
which watercooler-mcp
```

### Wrong Agent Identity

If tools show wrong agent name:

```bash
# Check current identity
python -c "from watercooler_mcp.config import get_agent_name; print(get_agent_name())"

# Set in environment
export WATERCOOLER_AGENT="YourAgentName"

# Or configure in MCP client settings
```

### Threads Directory Not Found

If server can't find threads:

```bash
# Check current directory
python -c "from watercooler_mcp.config import get_threads_dir; print(get_threads_dir())"

# Set explicit path
export WATERCOOLER_DIR="/full/path/to/.watercooler"

# Or use relative path from project root
```

### Format Not Supported Error

Currently, only `format="markdown"` is supported (JSON support is deferred):

```python
# This works:
list_threads(format="markdown")

# This will error:
list_threads(format="json")  # Error: Only format='markdown' is currently supported
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e .[dev,mcp]

# Run tests
pytest tests/
```

### Viewing Tool Schemas

```python
import asyncio
from watercooler_mcp.server import mcp

async def show_tools():
    tools = await mcp.get_tools()
    for name, tool in tools.items():
        print(f"\n{name}:")
        print(f"  Description: {tool.description}")
        print(f"  Parameters: {tool.parameters}")

asyncio.run(show_tools())
```

## Project Status

**See [ROADMAP.md](../ROADMAP.md) for complete phase history and future plans.**

### Completed ✅
- **Phase 1A (v0.1.0)**: MVP MCP server with 9 tools + 1 resource
- **Phase 1B (v0.2.0)**: Upward directory search, comprehensive documentation, Python 3.10+
- **Phase 2A**: Git-based cloud sync with Entry-ID idempotency and retry logic

### Deferred Features (Evaluate Based on Usage)
- **JSON format support**: Structured output for programmatic clients
- **Pagination**: Handle large thread counts efficiently
- **Additional tools**: `search_threads`, `create_thread`, `list_updates`, `break_lock`
- **Enhanced validation**: Error classes, enumeration helpers

### Planned (When Needed)
- **Managed cloud deployment**: OAuth authentication, multi-tenant hosting (Phase 2B/3)

## See Also

- [watercooler-collab README](../README.md) - Main project documentation
- [L5 MCP Plan](../L5_MCP_PLAN.md) - Detailed implementation plan
- [Python API Reference](./api.md) - Watercooler library API
- [Integration Guide](./integration.md) - Using watercooler-collab in projects

## Support

- **Issues**: https://github.com/mostlyharmless-ai/watercooler-collab/issues
- **Discussions**: Use GitHub Discussions for questions
- **MCP Protocol**: https://spec.modelcontextprotocol.io/
- **FastMCP Docs**: https://gofastmcp.com/
