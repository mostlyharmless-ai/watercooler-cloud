> **📦 Archived Documentation**: This document may contain outdated installation URLs. For current setup instructions, see [INSTALLATION.md](../INSTALLATION.md). Production users should install from the `@stable` branch.

# Setting Up Watercooler MCP Server with Claude Desktop

This guide shows you how to configure Claude Desktop to automatically launch and connect to the watercooler MCP server.

**Looking for other clients?**
- [Claude Code Setup](./CLAUDE_CODE_SETUP.md) - Configuration for Claude Code CLI
- [Codex Setup](./QUICKSTART.md#for-codex) - Configuration for Codex
- [Cursor Setup](../mcp-server.md#configuration-examples) - Configuration for Cursor IDE
- [CLI Workflows](./claude-collab.md) - Manual CLI usage (for scripts and automation)

## Prerequisites

1. **Claude Desktop installed** (macOS, Windows, or Linux)
2. **watercooler-cloud installed** with MCP extras:
   ```bash
   pip install -e .[mcp]
   ```

## Quick Setup (Recommended)

### 1. Follow the canonical quickstart

Complete [SETUP_AND_QUICKSTART.md](./SETUP_AND_QUICKSTART.md) to install dependencies and understand universal dev mode.

### 2. Register the universal server

Using `fastmcp`:

```bash
fastmcp install claude-desktop src/watercooler_mcp/server.py \
  --server-name "Watercooler" \
  --env WATERCOOLER_AGENT="Claude@Desktop" \
  --env WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  --env WATERCOOLER_AUTO_BRANCH=1
```

Or edit the Desktop config manually (
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows, `~/.config/Claude/claude_desktop_config.json` on Linux):

```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mostlyharmless-ai/watercooler-cloud",
        "watercooler-mcp"
      ],
      "env": {
        "WATERCOOLER_AGENT": "Claude@Desktop",
        "WATERCOOLER_THREADS_PATTERN": "https://github.com/{org}/{repo}-threads.git",
        "WATERCOOLER_AUTO_BRANCH": "1"
      }
    }
  }
}
```

**Note:** `uvx` must be in your PATH. If it's not found, use the full path (e.g., `~/.local/bin/uvx` on Linux/macOS). The `uvx` command ensures you always get the latest code from the repository and runs in an isolated environment.

Restart Claude Desktop and the tools appear automatically. No project-specific `WATERCOOLER_DIR` is necessary when you pass `code_path` on tool calls.

## Configuration Details

### Environment Variables

Claude Desktop lets you specify environment variables in the MCP registration. Most installations only need `WATERCOOLER_AGENT`; the universal defaults handle thread storage automatically.

```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mostlyharmless-ai/watercooler-cloud",
        "watercooler-mcp"
      ],
      "env": {
        "WATERCOOLER_AGENT": "Claude@Desktop",
        "WATERCOOLER_THREADS_PATTERN": "https://github.com/{org}/{repo}-threads.git",
        "WATERCOOLER_AUTO_BRANCH": "1"
      }
    }
  }
}
```

**Note:** `uvx` must be in your PATH. If it's not found, use the full path (e.g., `~/.local/bin/uvx` on Linux/macOS). The `uvx` command ensures you always get the latest code from the repository and runs in an isolated environment.

#### `WATERCOOLER_AGENT` (Required)
Identifies the assistant in thread entries. Add a suffix (`@Desktop`, `@Code`, etc.) if you use multiple clients.

#### Universal overrides

- `WATERCOOLER_THREADS_BASE` — optional central cache for threads repos (defaults to the sibling `<repo>-threads` directory)
- `WATERCOOLER_THREADS_PATTERN` — pattern used to construct the remote Git URL
- `WATERCOOLER_AUTO_BRANCH` — set to `0` to skip auto-creating branches (not recommended)
- `WATERCOOLER_GIT_AUTHOR` / `WATERCOOLER_GIT_EMAIL` — optional commit identity overrides when pushing

#### Manual override (`WATERCOOLER_DIR`)

Use `WATERCOOLER_DIR` only when you need a fixed threads directory (for example, a repo-local staging folder you created manually):

```json
{
  "env": {
        "WATERCOOLER_DIR": "/Users/you/project/threads-local"
  }
}
```

Setting this bypasses universal discovery; remove it after you relocate the data into the sibling `<repo>-threads` repository.

### Using Multiple Projects

Universal dev mode already adapts to whatever repo you launch Claude Desktop in. No extra entries are required.

If you prefer per-project segregation, you may still register additional MCP servers, but treat that as an advanced configuration. Each extra entry should use the same universal env vars and distinct `server-name` values to avoid confusion.

## Verification

After setup, verify the MCP server is working:

1. **Open Claude Desktop** (restart if it was already open)

2. **In a conversation, ask Claude:**
   ```
   Can you use the watercooler_v1_health tool to check if the watercooler MCP server is running?
   ```

3. **Expected response from Claude:**
   ```
   Watercooler MCP Server v0.2.0
   Status: Healthy
   Agent: Claude@Desktop
   Threads Dir: /path/to/<repo>-threads
   Threads Dir Exists: True
   ```

   If you see any path that lives inside the code repository (for example `.../threads-local`), remove manual overrides, pass `code_path="."` on every call, and move the data into the sibling `<repo>-threads` directory before deleting the stray files.

4. **List available watercooler tools:**
   ```
   What watercooler tools are available?
   ```

   Claude should list the complete `watercooler_v1_*` tool suite.

## Using Watercooler with Claude

Once configured, Claude can naturally use watercooler tools without you manually invoking CLI commands.

### Example Workflow

**You:** "Can you check what watercooler threads I have?"

**Claude will:**
1. Call `watercooler_v1_list_threads`
2. Show you threads where you have the ball
3. Highlight threads with NEW entries

**You:** "Read the feature-auth thread"

**Claude will:**
1. Call `watercooler_v1_read_thread` with topic "feature-auth"
2. Show you the full thread content
3. Understand the context and discussion

**You:** "Respond saying the implementation is complete"

**Claude will:**
1. Call `watercooler_v1_say` with appropriate title and body
2. Auto-flip the ball to your counterpart
3. Confirm the entry was added

## Troubleshooting

### Server Not Starting

**Symptom:** Claude says watercooler tools are not available

**Check:**
1. Command path is correct:
   ```bash
   which watercooler-mcp
   ```
2. File has execute permissions
3. Python environment is accessible
4. Check Claude Desktop logs (see below)

### Wrong Agent Identity

**Symptom:** Entries show wrong agent name

**Fix:** Update `WATERCOOLER_AGENT` in config and restart Claude Desktop

```json
"env": {
  "WATERCOOLER_AGENT": "YourCorrectName"
}
```

### Threads Not Found

**Symptom:** "No threads directory found" error

**Fix:**
- Call `watercooler_v1_health(code_path=".")` and confirm the output points to the sibling `<repo>-threads` directory
- Ensure every subsequent tool call includes `code_path`
- Remove any `WATERCOOLER_DIR` overrides from the Desktop config; universal mode handles path discovery automatically

### Finding Claude Desktop Logs

**macOS:**
```bash
~/Library/Logs/Claude/
```

**Windows:**
```
%APPDATA%\Claude\logs\
```

**Linux:**
```bash
~/.config/Claude/logs/
```

Look for MCP-related errors in the latest log files.

## Advanced Configuration

### Using Python from Specific Environment

If you have multiple Python environments, specify the full path:

```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mostlyharmless-ai/watercooler-cloud",
        "watercooler-mcp"
      ],
      "env": {
        "WATERCOOLER_AGENT": "Claude@Desktop",
        "WATERCOOLER_THREADS_PATTERN": "https://github.com/{org}/{repo}-threads.git",
        "WATERCOOLER_AUTO_BRANCH": "1"
      }
    }
  }
}
```

**Note:** If you need to use a specific Python environment, you can still use `uvx` as it manages its own isolated environment. The `uvx` command ensures you always get the latest code from the repository.

### Using uv for Dependency Management

If you use `uv` for package management:

```json
{
  "mcpServers": {
        "watercooler-cloud": {
          "command": "uv",
          "args": [
            "run",
            "--with", "fastmcp",
            "fastmcp",
            "run",
            "/path/to/watercooler-cloud/src/watercooler_mcp/server.py"
          ],
          "env": {
            "WATERCOOLER_AGENT": "Claude@Desktop",
            "WATERCOOLER_THREADS_PATTERN": "https://github.com/{org}/{repo}-threads.git",
            "WATERCOOLER_AUTO_BRANCH": "1"
          }
        }
      }
}
```

### Specifying Project Directory

If your server needs to run in a specific project context:

```json
{
  "mcpServers": {
    "watercooler": {
      "command": "/path/to/watercooler-mcp",
      "env": {
        "WATERCOOLER_AGENT": "Claude@Desktop",
        "WATERCOOLER_THREADS_PATTERN": "https://github.com/{org}/{repo}-threads.git",
        "WATERCOOLER_AUTO_BRANCH": "1"
      },
      "cwd": "/path/to/project"
    }
  }
}
```

## Quick Reference

### Installation Commands

```bash
# Automatic (recommended)
fastmcp install claude-desktop src/watercooler_mcp/server.py \
  --server-name "Watercooler" \
  --env WATERCOOLER_AGENT="Claude@Desktop" \
  --env WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  --env WATERCOOLER_AUTO_BRANCH=1

# Find command path
which watercooler-mcp

# Check if watercooler is installed
pip list | grep watercooler
```

### Config File Locations

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Minimal Working Config

```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mostlyharmless-ai/watercooler-cloud",
        "watercooler-mcp"
      ],
      "env": {
        "WATERCOOLER_AGENT": "Claude@Desktop",
        "WATERCOOLER_THREADS_PATTERN": "https://github.com/{org}/{repo}-threads.git",
        "WATERCOOLER_AUTO_BRANCH": "1"
      }
    }
  }
}
```

**Note:** `uvx` must be in your PATH. If it's not found, use the full path (e.g., `~/.local/bin/uvx` on Linux/macOS). The `uvx` command ensures you always get the latest code from the repository and runs in an isolated environment.

## Next Steps

After setup:

1. **Test with a simple thread** - Create a test thread and verify Claude can read/respond
2. **Configure counterparts** - Set up agent registry for automatic ball flipping
3. **Explore all tools** - Try list_threads, handoff, set_status, reindex
4. **Read the full docs** - See [mcp-server.md](./mcp-server.md) for detailed tool documentation

## Support

- **Issues**: https://github.com/mostlyharmless-ai/watercooler-cloud/issues
- **Full MCP Docs**: [mcp-server.md](./mcp-server.md)
- **Testing Results**: [TESTING_RESULTS.md](./TESTING_RESULTS.md)
