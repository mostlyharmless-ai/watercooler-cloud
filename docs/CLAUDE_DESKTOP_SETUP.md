# Setting Up Watercooler MCP Server with Claude Desktop

This guide shows you how to configure Claude Desktop to automatically launch and connect to the watercooler MCP server.

## Prerequisites

1. **Claude Desktop installed** (macOS, Windows, or Linux)
2. **watercooler-collab installed** with MCP extras:
   ```bash
   pip install -e .[mcp]
   ```

## Quick Setup (Recommended)

### Option 1: Automatic Installation with fastmcp CLI

The easiest way to register the watercooler MCP server with Claude Desktop:

```bash
# Navigate to your watercooler-collab directory
cd /path/to/watercooler-collab

# Install the server with fastmcp CLI
fastmcp install claude-desktop src/watercooler_mcp/server.py \
  --server-name "Watercooler" \
  --env WATERCOOLER_AGENT=Claude \
  --env WATERCOOLER_DIR=/path/to/your/project/.watercooler
```

**That's it!** Restart Claude Desktop and the watercooler tools will be available.

### Option 2: Manual Configuration

If you prefer manual configuration or need more control:

1. **Find your Claude Desktop config file:**
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. **Edit the config file** (create it if it doesn't exist):

```json
{
  "mcpServers": {
    "watercooler": {
      "command": "/path/to/watercooler-mcp",
      "env": {
        "WATERCOOLER_AGENT": "Claude",
        "WATERCOOLER_DIR": "/path/to/your/project/.watercooler"
      }
    }
  }
}
```

3. **Find your watercooler-mcp command path:**
   ```bash
   which watercooler-mcp
   # Example output: /opt/anaconda3/envs/watercooler/bin/watercooler-mcp
   ```

4. **Replace paths in the config:**
   - `command`: Use the full path from `which watercooler-mcp`
   - `WATERCOOLER_DIR`: Use absolute path to your project's `.watercooler` directory

5. **Restart Claude Desktop**

## Configuration Details

### Environment Variables

You can configure the MCP server's behavior through environment variables:

#### `WATERCOOLER_AGENT` (Required)
Your agent identity - this determines:
- How you appear in thread entries
- Which threads show as "Your Turn"

```json
"env": {
  "WATERCOOLER_AGENT": "Claude"
}
```

Common agent names: `Claude`, `Codex`, `Assistant`, etc.

#### `WATERCOOLER_DIR` (Optional)
Path to the `.watercooler` directory containing threads.

```json
"env": {
  "WATERCOOLER_DIR": "/Users/you/projects/myproject/.watercooler"
}
```

**Default:** `./.watercooler` (current working directory)

**Note:** Use absolute paths for reliability. Relative paths are relative to where Claude Desktop launches the server.

### Using Multiple Projects

If you work on multiple projects with separate watercooler threads, you can:

#### Option A: One Server Per Project

Add multiple server entries to your config:

```json
{
  "mcpServers": {
    "watercooler-project-a": {
      "command": "/path/to/watercooler-mcp",
      "env": {
        "WATERCOOLER_AGENT": "Claude",
        "WATERCOOLER_DIR": "/path/to/projectA/.watercooler"
      }
    },
    "watercooler-project-b": {
      "command": "/path/to/watercooler-mcp",
      "env": {
        "WATERCOOLER_AGENT": "Claude",
        "WATERCOOLER_DIR": "/path/to/projectB/.watercooler"
      }
    }
  }
}
```

Claude Desktop will connect to all configured servers and namespace their tools:
- Tools from project-a: `watercooler.v1.list_threads` (from watercooler-project-a)
- Tools from project-b: `watercooler.v1.list_threads` (from watercooler-project-b)

#### Option B: Change Config Per Project

Keep a simple single-server config and change `WATERCOOLER_DIR` when switching projects. Requires restarting Claude Desktop after changes.

## Verification

After setup, verify the MCP server is working:

1. **Open Claude Desktop** (restart if it was already open)

2. **In a conversation, ask Claude:**
   ```
   Can you use the watercooler.v1.health tool to check if the watercooler MCP server is running?
   ```

3. **Expected response from Claude:**
   ```
   Watercooler MCP Server v0.1.0
   Status: Healthy
   Agent: Claude
   Threads Dir: /path/to/.watercooler
   Threads Dir Exists: True
   ```

4. **List available watercooler tools:**
   ```
   What watercooler tools are available?
   ```

   Claude should see all 9 tools:
   - `watercooler.v1.health`
   - `watercooler.v1.whoami`
   - `watercooler.v1.list_threads`
   - `watercooler.v1.read_thread`
   - `watercooler.v1.say`
   - `watercooler.v1.ack`
   - `watercooler.v1.handoff`
   - `watercooler.v1.set_status`
   - `watercooler.v1.reindex`

## Using Watercooler with Claude

Once configured, Claude can naturally use watercooler tools without you manually invoking CLI commands.

### Example Workflow

**You:** "Can you check what watercooler threads I have?"

**Claude will:**
1. Call `watercooler.v1.list_threads`
2. Show you threads where you have the ball
3. Highlight threads with NEW entries

**You:** "Read the feature-auth thread"

**Claude will:**
1. Call `watercooler.v1.read_thread` with topic "feature-auth"
2. Show you the full thread content
3. Understand the context and discussion

**You:** "Respond saying the implementation is complete"

**Claude will:**
1. Call `watercooler.v1.say` with appropriate title and body
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

**Fix:** Verify `WATERCOOLER_DIR` path is correct and absolute:

```json
"env": {
  "WATERCOOLER_DIR": "/full/absolute/path/to/.watercooler"
}
```

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
    "watercooler": {
      "command": "/opt/anaconda3/envs/watercooler/bin/python",
      "args": ["-m", "watercooler_mcp"],
      "env": {
        "WATERCOOLER_AGENT": "Claude",
        "WATERCOOLER_DIR": "/path/to/.watercooler"
      }
    }
  }
}
```

### Using uv for Dependency Management

If you use `uv` for package management:

```json
{
  "mcpServers": {
    "watercooler": {
      "command": "uv",
      "args": [
        "run",
        "--with", "fastmcp",
        "fastmcp",
        "run",
        "/path/to/watercooler-collab/src/watercooler_mcp/server.py"
      ],
      "env": {
        "WATERCOOLER_AGENT": "Claude",
        "WATERCOOLER_DIR": "/path/to/.watercooler"
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
        "WATERCOOLER_AGENT": "Claude",
        "WATERCOOLER_DIR": "/path/to/.watercooler"
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
  --env WATERCOOLER_AGENT=Claude \
  --env WATERCOOLER_DIR=/path/to/.watercooler

# Find command path
which watercooler-mcp

# Check if watercooler is installed
pip list | grep watercooler-collab
```

### Config File Locations

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Minimal Working Config

```json
{
  "mcpServers": {
    "watercooler": {
      "command": "/full/path/to/watercooler-mcp",
      "env": {
        "WATERCOOLER_AGENT": "Claude"
      }
    }
  }
}
```

## Next Steps

After setup:

1. **Test with a simple thread** - Create a test thread and verify Claude can read/respond
2. **Configure counterparts** - Set up agent registry for automatic ball flipping
3. **Explore all tools** - Try list_threads, handoff, set_status, reindex
4. **Read the full docs** - See [mcp-server.md](./mcp-server.md) for detailed tool documentation

## Support

- **Issues**: https://github.com/mostlyharmless-ai/watercooler-collab/issues
- **Full MCP Docs**: [mcp-server.md](./mcp-server.md)
- **Testing Results**: [TESTING_RESULTS.md](./TESTING_RESULTS.md)
