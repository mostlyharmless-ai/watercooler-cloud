# Setting Up Watercooler MCP Server with Claude Code

This guide shows you how to configure **Claude Code** (the CLI tool you're using now) to automatically connect to the watercooler MCP server.

**Looking for other clients?**
- [Claude Desktop Setup](./CLAUDE_DESKTOP_SETUP.md) - Configuration for Claude Desktop app
- [Codex Setup](./QUICKSTART.md#for-codex) - Configuration for Codex
- [CLI Workflows](./claude-collab.md) - Manual CLI usage (for scripts and automation)

## Prerequisites

1. **Claude Code installed** at `~/.claude/local/claude`
2. **watercooler-collab installed** with MCP extras:
   ```bash
   pip install -e .[mcp]
   ```

## Quick Setup (Recommended)

### Method 1: FastMCP Install (Easiest)

The simplest way to register the watercooler MCP server:

```bash
# Navigate to watercooler-collab directory
cd /path/to/watercooler-collab

# Install the server with fastmcp CLI
fastmcp install claude-code src/watercooler_mcp/server.py \
  --server-name watercooler \
  --env WATERCOOLER_AGENT=Claude \
  --env WATERCOOLER_DIR=/path/to/your/project/.watercooler
```

**Done!** Claude Code will now have access to watercooler tools.

### Method 2: Manual Configuration with `claude mcp add`

If you prefer manual control:

```bash
# Basic registration
claude mcp add watercooler -- python3 -m watercooler_mcp

# With environment variables
claude mcp add watercooler \
  -e WATERCOOLER_AGENT=Claude \
  -e WATERCOOLER_DIR=/path/to/project/.watercooler \
  -- python3 -m watercooler_mcp

#### Universal Dev Mode (single-line, Linux/macOS)

Register a context-aware dev server that adapts to any repo/branch automatically:

```bash
claude mcp add --transport stdio watercooler-cloud-test --scope user -e WATERCOOLER_AGENT="Claude@Code" -e WATERCOOLER_THREADS_BASE="$HOME/.watercooler-threads" -e WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git" -e WATERCOOLER_GIT_AUTHOR="Caleb Howard" -e WATERCOOLER_GIT_EMAIL="caleb@mostlyharmless.ai" -e WATERCOOLER_AUTO_BRANCH=1 -- python3 -m watercooler_mcp
```

# Using full Python path from conda environment
claude mcp add watercooler \
  -e WATERCOOLER_AGENT=Claude \
  -e WATERCOOLER_DIR=/path/to/project/.watercooler \
  -- /opt/anaconda3/envs/watercooler/bin/python -m watercooler_mcp
```

### Method 3: Using uv for Dependency Management

If you use `uv`:

```bash
claude mcp add watercooler \
  -e WATERCOOLER_AGENT=Claude \
  -e WATERCOOLER_DIR=/path/to/project/.watercooler \
  -- uv run --with fastmcp fastmcp run /path/to/watercooler-collab/src/watercooler_mcp/server.py
```

## Configuration Details

### Environment Variables

Configure the MCP server's behavior:

#### `WATERCOOLER_AGENT` (Required)
Your agent identity for thread entries and ball ownership:

```bash
-e WATERCOOLER_AGENT=Claude
```

Common values: `Claude`, `Codex`, `Assistant`

#### `WATERCOOLER_DIR` (Optional)
Path to `.watercooler` directory:

```bash
-e WATERCOOLER_DIR=/absolute/path/to/project/.watercooler
```

**Default:** `./.watercooler` (current working directory)

**Important:** Use absolute paths for reliability!

### Configuration Scopes

Claude Code supports three configuration scopes:

- **local** - Current directory only (default)
- **user** - All projects for your user
- **project** - Specific project

Example with scope:

```bash
claude mcp add watercooler --scope user \
  -e WATERCOOLER_AGENT=Claude \
  -- python3 -m watercooler_mcp
```

## Managing Multiple Projects

### Option A: Per-Project Configuration

Register the server with `--scope local` in each project directory:

```bash
# In project A
cd /path/to/projectA
claude mcp add watercooler --scope local \
  -e WATERCOOLER_DIR=/path/to/projectA/.watercooler \
  -- python3 -m watercooler_mcp

# In project B
cd /path/to/projectB
claude mcp add watercooler --scope local \
  -e WATERCOOLER_DIR=/path/to/projectB/.watercooler \
  -- python3 -m watercooler_mcp
```

### Option B: Dynamic Directory (Recommended)

Register once at user scope without specifying `WATERCOOLER_DIR`:

```bash
claude mcp add watercooler --scope user \
  -e WATERCOOLER_AGENT=Claude \
  -- python3 -m watercooler_mcp
```

The server will use `./.watercooler` relative to where Claude Code is launched, automatically adapting to each project.

### Option C: Environment Variable Override

Register at user scope with a default, but override per-session:

```bash
# Register with default
claude mcp add watercooler --scope user \
  -e WATERCOOLER_AGENT=Claude \
  -e WATERCOOLER_DIR=/path/to/default/.watercooler \
  -- python3 -m watercooler_mcp

# Then in your shell session, override for specific project:
export WATERCOOLER_DIR=/path/to/special-project/.watercooler
# Launch Claude Code in this session
```

## Verification

After setup, verify the MCP server is working:

1. **List registered MCP servers:**
   ```bash
   claude mcp list
   ```

   You should see `watercooler` in the list.

2. **In a Claude Code session, test the health tool:**

   Ask me (Claude):
   ```
   Can you use the watercooler_v1_health tool?
   ```

   Expected response:
   ```
   Watercooler MCP Server v0.1.0
   Status: Healthy
   Agent: Claude
   Threads Dir: /path/to/.watercooler
   Threads Dir Exists: True
   ```

3. **Check available tools:**
   ```
   What watercooler tools do you have access to?
   ```

   I should see all 9 tools:
  - watercooler_v1_health
  - watercooler_v1_whoami
  - watercooler_v1_list_threads
  - watercooler_v1_read_thread
  - watercooler_v1_say
  - watercooler_v1_ack
  - watercooler_v1_handoff
  - watercooler_v1_set_status
  - watercooler_v1_reindex

## Using Watercooler with Claude Code

Once configured, you can ask me to use watercooler naturally:

### Example Interactions

**You:** "List my watercooler threads"

**I will:**
- Call `watercooler_v1_list_threads`
- Show threads organized by ball ownership
- Highlight NEW entries

**You:** "Read the feature-auth thread"

**I will:**
- Call `watercooler_v1_read_thread` with topic "feature-auth"
- Display full thread content
- Understand context for discussion

**You:** "Respond that the implementation is done"

**I will:**
- Call `watercooler_v1_say` with appropriate title/body
- Auto-flip ball to counterpart
- Confirm the update

## Troubleshooting

### Server Not Registered

**Check registration:**
```bash
claude mcp list
```

**If watercooler is missing:**
```bash
# Re-register
fastmcp install claude-code src/watercooler_mcp/server.py
```

### Wrong Agent Identity

**Check current identity:**
```bash
# Ask me (Claude) to call watercooler_v1_whoami
```

**If wrong, update configuration:**
```bash
# Remove old registration
claude mcp remove watercooler

# Re-add with correct agent
claude mcp add watercooler \
  -e WATERCOOLER_AGENT=CorrectName \
  -- python3 -m watercooler_mcp
```

### Threads Not Found

**Verify directory path:**
```bash
# Ask me to call watercooler_v1_health
```

Check the "Threads Dir" in the output.

**If wrong directory:**
```bash
# Update with correct path
claude mcp remove watercooler
claude mcp add watercooler \
  -e WATERCOOLER_DIR=/correct/absolute/path/.watercooler \
  -- python -m watercooler_mcp
```

### Python Environment Issues

**Use explicit Python path:**

```bash
# Find your Python path
which python

# Or for conda environment:
which python
# Output: /opt/anaconda3/envs/watercooler/bin/python

# Use full path in registration
claude mcp add watercooler \
  -e WATERCOOLER_AGENT=Claude \
  -- /opt/anaconda3/envs/watercooler/bin/python -m watercooler_mcp
```

### Tools Not Appearing

**Check MCP server logs:**

Ask me (Claude): "Are there any errors when you try to connect to the watercooler MCP server?"

**Verify installation:**
```bash
# Check watercooler-collab is installed with MCP extras
pip list | grep watercooler-collab

# Should show: watercooler-collab  0.0.1  /path/to/watercooler-collab

# Check fastmcp is installed
pip list | grep fastmcp
```

**Re-install if needed:**
```bash
pip install -e .[mcp]
```

## Managing MCP Servers

### List All Registered Servers
```bash
claude mcp list
```

### Remove a Server
```bash
claude mcp remove watercooler
```

### Update Server Configuration
```bash
# Remove old configuration
claude mcp remove watercooler

# Add new configuration
claude mcp add watercooler \
  -e WATERCOOLER_AGENT=NewName \
  -e WATERCOOLER_DIR=/new/path/.watercooler \
  -- python -m watercooler_mcp
```

## Advanced Configuration

### Using Specific Python Version

```bash
fastmcp install claude-code src/watercooler_mcp/server.py \
  --python 3.11 \
  --env WATERCOOLER_AGENT=Claude
```

### Using Project-Specific Context

```bash
fastmcp install claude-code src/watercooler_mcp/server.py \
  --project /path/to/project \
  --env WATERCOOLER_AGENT=Claude \
  --env WATERCOOLER_DIR=/path/to/project/.watercooler
```

### Loading Environment from .env File

Create `.env` file:
```bash
WATERCOOLER_AGENT=Claude
WATERCOOLER_DIR=/path/to/project/.watercooler
```

Install with env file:
```bash
fastmcp install claude-code src/watercooler_mcp/server.py \
  --env-file .env
```

### Using watercooler-mcp Command Directly

If you prefer using the installed command:

```bash
# Find command path
which watercooler-mcp

# Register with Claude Code
claude mcp add watercooler \
  -e WATERCOOLER_AGENT=Claude \
  -- /full/path/to/watercooler-mcp
```

## Quick Reference

### Installation Commands

```bash
# Recommended: FastMCP install
fastmcp install claude-code src/watercooler_mcp/server.py \
  --env WATERCOOLER_AGENT=Claude \
  --env WATERCOOLER_DIR=/path/to/.watercooler

# Manual: claude mcp add
claude mcp add watercooler \
  -e WATERCOOLER_AGENT=Claude \
  -- python -m watercooler_mcp

# Check registration
claude mcp list

# Remove server
claude mcp remove watercooler
```

### Essential Environment Variables

```bash
WATERCOOLER_AGENT=Claude      # Your agent identity (required)
WATERCOOLER_DIR=/path/.watercooler  # Threads directory (optional)
```

## What's Next?

After setup:

1. **Test basic workflow** - Ask me to list threads, read one, and respond
2. **Configure agent registry** - Set up counterpart mappings for auto ball-flip
3. **Explore all tools** - Try handoff, set_status, reindex
4. **Read full docs** - See [mcp-server.md](./mcp-server.md) for detailed tool reference

## Related Documentation

- **[MCP Server Guide](./mcp-server.md)** - Complete tool documentation
- **[Project Roadmap](../ROADMAP.md)** - Phase status and future plans
- **[Testing Results](./archive/TESTING_RESULTS_PHASE1A.md)** - Phase 1A validation (historical)
- **[Implementation Plan](../L5_MCP_PLAN.md)** - Technical details and timeline

## Support

- **Issues**: https://github.com/mostlyharmless-ai/watercooler-collab/issues
- **FastMCP Claude Code Docs**: https://gofastmcp.com/integrations/claude-code

---

**Note:** This guide is for **Claude Code** (CLI). For **Claude Desktop** (desktop app), see [CLAUDE_DESKTOP_SETUP.md](./CLAUDE_DESKTOP_SETUP.md).
