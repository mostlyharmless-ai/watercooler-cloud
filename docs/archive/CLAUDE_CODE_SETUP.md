# Setting Up Watercooler MCP Server with Claude Code

This guide shows you how to configure **Claude Code** (the CLI tool you're using now) to automatically connect to the watercooler MCP server.

**Looking for other clients?**
- [Claude Desktop Setup](./CLAUDE_DESKTOP_SETUP.md) - Configuration for Claude Desktop app
- [Codex Setup](./QUICKSTART.md#for-codex) - Configuration for Codex
- [CLI Workflows](./claude-collab.md) - Manual CLI usage (for scripts and automation)

## Prerequisites

1. **Claude Code installed** at `~/.claude/local/claude`
2. **watercooler-cloud installed** with MCP extras:
   ```bash
   pip install -e .[mcp]
   ```
3. **GitHub CLI installed and authenticated** (for auto-provisioning):
   ```bash
   gh auth status  # Verify authentication
   ```
   If not authenticated, run: `gh auth login`

## Quick Setup (Recommended)

### 1. Follow the canonical quickstart

Complete the steps in [SETUP_AND_QUICKSTART.md](./SETUP_AND_QUICKSTART.md). That guide installs the package, explains branch pairing, and introduces the identity rules that Claude Code must follow.

### 2. Register the universal server (one command)

Run this once; it applies to every repo you open in Claude Code:

```bash
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python3 -m watercooler_mcp
```

Use `fastmcp install` if you prefer an installer-style workflow:

```bash
fastmcp install claude-code src/watercooler_mcp/server.py \
  --server-name watercooler-cloud \
  --env WATERCOOLER_AGENT="Claude@Code" \
  --env WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  --env WATERCOOLER_AUTO_BRANCH=1
```

That’s it—Claude Code now discovers Watercooler tools for any repo/branch you open. No per-project `WATERCOOLER_DIR` settings are required in universal mode.

## Configuration Details

### Environment Variables

Configure the MCP server's behavior:

#### `WATERCOOLER_AGENT` (Required)
Your agent identity for thread entries and ball ownership:

```bash
-e WATERCOOLER_AGENT="Claude@Code"
```

Common values: `Claude`, `Codex`, `Assistant`. Include the specialization suffix (`@Code`, `@Desk`, etc.) if you want it to appear in thread entries.

#### Universal-mode overrides (Optional)

- `WATERCOOLER_THREADS_BASE` — optional central cache for threads (defaults to the sibling `<repo>-threads` directory beside your code repo)
- `WATERCOOLER_THREADS_PATTERN` — pattern for resolving the remote threads repo (defaults to `https://github.com/{org}/{repo}-threads.git`)
- `WATERCOOLER_AUTO_BRANCH` — set to `0` to disable branch auto-creation
- `WATERCOOLER_THREADS_AUTO_PROVISION` — set to `0` to disable auto-provisioning (enabled by default)
- `WATERCOOLER_THREADS_CREATE_CMD` — override the provisioning command (defaults to `gh repo create {slug} --private --disable-wiki --disable-issues`)
- `WATERCOOLER_GIT_AUTHOR` / `WATERCOOLER_GIT_EMAIL` — override commit identity in the threads repo

**Note:** Auto-provisioning is **enabled by default** and will automatically create missing `<repo>-threads` repositories using GitHub CLI. To disable, set `WATERCOOLER_THREADS_AUTO_PROVISION=0`.

Avoid setting `WATERCOOLER_DIR` unless you require a fixed override. Universal mode automatically locates the correct threads repo based on `code_path`.

### Configuration Scopes

Claude Code supports three configuration scopes:

- **local** - Current directory only (default)
- **user** - All projects for your user
- **project** - Specific project

Example with scope:

```bash
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python3 -m watercooler_mcp
```

## Managing Multiple Projects

Universal dev mode already adapts to whichever repo you open. No further configuration is required when you switch projects.

**Advanced workflows**: If you still maintain per-project registrations (for example, to force a bespoke threads directory), you can keep those `WATERCOOLER_DIR` overrides in place. Just note that the canonical flow—and all MCP tooling tests—assume the universal pattern described above.

## Verification

After setup, verify the MCP server is working:

1. **List registered MCP servers:**
   ```bash
   claude mcp list
   ```

   You should see `watercooler-cloud` in the list.

2. **In a Claude Code session, test the health tool:**

   Ask the assistant:
   ```
   Can you call watercooler_v1_health with code_path="."?
   ```

  Expected response:
  ```
  Watercooler MCP Server v0.2.0
  Status: Healthy
  Agent: Claude@Code
  Threads Dir: /path/to/<repo>-threads
  Threads Dir Exists: True
  ```

3. **Check available tools:**
   ```
   What watercooler tools do you have access to?
   ```

   Claude should list the complete `watercooler_v1_*` tool suite.

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

**If `watercooler-cloud` is missing:**
```bash
# Re-register with the universal command
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python3 -m watercooler_mcp
```

### Wrong Agent Identity

**Check current identity:**
```bash
# Ask me (Claude) to call watercooler_v1_whoami
```

**If wrong, update configuration:**
```bash
# Remove old registration
claude mcp remove watercooler-cloud

# Re-add with the correct agent base/spec suffix
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python3 -m watercooler_mcp
```

### Threads Not Found

**Verify directory path:**
```bash
# Ask me to call watercooler_v1_health
```

Check the "Threads Dir" in the output. It should point to the sibling directory (for example `/workspace/<repo>-threads`).

**If it shows a path inside your code repo (for example `.../threads-local`):**
- Confirm you are passing `code_path` on every tool call
- Remove any lingering `WATERCOOLER_DIR` overrides from your registration or environment
- Delete the stray directory in the repo after copying its contents into the sibling `<repo>-threads` repository.

### Python Environment Issues

**Use explicit Python path:**

```bash
# Find your Python path
which python

# Or for conda environment:
which python
# Output: /opt/anaconda3/envs/watercooler/bin/python

# Use full path in registration
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- /opt/anaconda3/envs/watercooler/bin/python -m watercooler_mcp
```

### Tools Not Appearing

**Check MCP server logs:**

Ask me (Claude): "Are there any errors when you try to connect to the watercooler MCP server?"

**Verify installation:**
```bash
# Check watercooler-cloud is installed with MCP extras
pip list | grep watercooler-cloud

# Should show: watercooler-cloud  0.0.1  /path/to/watercooler-cloud

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
claude mcp remove watercooler-cloud
```

### Update Server Configuration
```bash
# Remove old configuration
claude mcp remove watercooler-cloud

# Add new configuration (example: change agent identity)
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python3 -m watercooler_mcp
```

## Advanced Configuration

### Using Specific Python Version

```bash
fastmcp install claude-code src/watercooler_mcp/server.py \
  --python 3.11 \
  --env WATERCOOLER_AGENT="Claude@Code"
```

### Project-specific overrides

If you must target a bespoke threads directory, you can still provide `WATERCOOLER_DIR`, but note that doing so disables universal repo discovery. Prefer the default flow unless you have a concrete requirement.

### Loading Environment from `.env`

Prefer storing overrides in a file? Create `.env` with only the variables you need:

```bash
WATERCOOLER_AGENT="Claude@Code"
WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git"
WATERCOOLER_AUTO_BRANCH=1
```

Install with the env file:

```bash
fastmcp install claude-code src/watercooler_mcp/server.py \
  --server-name watercooler-cloud \
  --env-file .env
```

### Using `watercooler-mcp` directly

If you prefer referencing the installed entry point explicitly:

```bash
# Find command path
which watercooler-mcp

# Register with Claude Code
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- /full/path/to/watercooler-mcp
```

## Quick Reference

### Installation Commands

```bash
# One-and-done universal registration
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python3 -m watercooler_mcp

# Check registration
claude mcp list

# Remove server
claude mcp remove watercooler-cloud
```

### Essential Environment Variables

```bash
WATERCOOLER_AGENT="Claude@Code"               # Required agent identity
WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git"  # Optional override
WATERCOOLER_AUTO_BRANCH=1                     # Ensure branch mirroring
```

## What's Next?

After setup:

1. **Test basic workflow** - Ask me to list threads, read one, and respond
2. **Configure agent registry** - Set up counterpart mappings for auto ball-flip
3. **Explore all tools** - Try handoff, set_status, reindex
4. **Read full docs** - See [mcp-server.md](./mcp-server.md) for detailed tool reference

## Related Documentation

- **[MCP Server Guide](./mcp-server.md)** - Complete tool documentation
- **[Project Roadmap](../../ROADMAP.md)** - Phase status and future plans
- **[Testing Results](./archive/TESTING_RESULTS_PHASE1A.md)** - Phase 1A validation (historical)
- **[Implementation Plan](../../L5_MCP_PLAN.md)** - Technical details and timeline

## Support

- **Issues**: https://github.com/mostlyharmless-ai/watercooler-cloud/issues
- **FastMCP Claude Code Docs**: https://gofastmcp.com/integrations/claude-code

---

**Note:** This guide is for **Claude Code** (CLI). For **Claude Desktop** (desktop app), see [CLAUDE_DESKTOP_SETUP.md](./CLAUDE_DESKTOP_SETUP.md).
