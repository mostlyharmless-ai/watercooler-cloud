# Watercooler MCP Server - Troubleshooting Guide

Common issues and solutions for the watercooler MCP server.

## Server Not Loading

### Symptom
MCP tools don't appear in your client (Claude Desktop, Claude Code, Codex).

### Solutions

1. **Verify installation**
   ```bash
   python3 -m watercooler_mcp
   ```
   Should display FastMCP banner and start server.

2. **Check configuration file syntax**
   - **Codex**: Verify `~/.codex/config.toml` is valid TOML
   - **Claude Desktop**: Verify `claude_desktop_config.json` is valid JSON
   - **Claude Code**: Verify `.mcp.json` is valid JSON

3. **Restart your client**
   - Codex: Restart the CLI session
   - Claude Desktop: Quit and relaunch the app
   - Claude Code: Reload window (Cmd+R or Ctrl+R)

4. **Check Python path**
   ```bash
   which python3
   ```
   Ensure the `python3` in your config matches your installation.

5. **Verify dependencies**
   ```bash
   pip list | grep -E "(fastmcp|mcp)"
   ```
   Should show `fastmcp>=2.0` and `mcp>=1.0`.

## Wrong Agent Identity

### Symptom
`watercooler_v1_whoami` shows incorrect agent name.

### Solutions

1. **Check WATERCOOLER_AGENT environment variable**

   **Codex config.toml:**
   ```toml
   [mcp_servers.watercooler.env]
   WATERCOOLER_AGENT = "Codex"  # ← Must match your desired name
   ```

   **Claude Desktop config.json:**
   ```json
   {
     "env": {
       "WATERCOOLER_AGENT": "Claude"
     }
   }
   ```

2. **Understand precedence**
   - `WATERCOOLER_AGENT` env var (highest priority)
   - `client_id` from MCP Context (auto-detected)
   - Fallback: "Agent"

3. **Client ID auto-detection**
   - "Claude Desktop" → "Claude"
   - "Claude Code" → "Claude"
   - Other values passed through as-is

## Threads Directory Not Found

### Symptom
```
No threads directory found at: /some/path/.watercooler
```

### Solutions

1. **Understand resolution order (Phase 1B)**
   1. `WATERCOOLER_DIR` env var (explicit override)
   2. Upward search from CWD for existing `.watercooler/`
   3. Fallback: `{CWD}/.watercooler` (for auto-creation)

2. **Let upward search find it**

   If you have `.watercooler/` at your repo root:
   ```bash
   # No configuration needed!
   # Works from any subdirectory in the repo
   ```

   The upward search stops at:
   - Git repository root
   - HOME directory
   - Filesystem root (safety)

3. **Set explicit directory**

   **Codex config.toml:**
   ```toml
   [mcp_servers.watercooler.env]
   WATERCOOLER_DIR = "/Users/jay/projects/my-project/.watercooler"
   ```

   **Use absolute paths** to avoid ambiguity.

4. **Create threads directory manually**
   ```bash
   mkdir -p /path/to/project/.watercooler
   ```

5. **Verify with health check**
   ```
   watercooler_v1_health
   ```
   Shows: `Threads Dir: /path` and `Threads Dir Exists: True/False`

## Permission Errors

### Symptom
```
PermissionError: [Errno 13] Permission denied: '/path/.watercooler/thread.md'
```

### Solutions

1. **Check directory permissions**
   ```bash
   ls -la /path/.watercooler
   ```

   Should be writable by your user:
   ```bash
   chmod 755 /path/.watercooler
   ```

2. **Check file permissions**
   ```bash
   chmod 644 /path/.watercooler/*.md
   ```

3. **Verify ownership**
   ```bash
   chown -R $USER /path/.watercooler
   ```

## Client ID is None

### Symptom
`watercooler_v1_whoami` shows `Client ID: None`

### Explanation
This is **normal for local STDIO connections**. The `client_id` is:
- Populated when using OAuth authentication (FastMCP Cloud)
- `None` for local STDIO transport (Claude Desktop, Claude Code, Codex)

### Solutions

1. **For local usage**: This is expected and doesn't affect functionality
   - Agent name comes from `WATERCOOLER_AGENT` env var
   - Everything works normally

2. **For multi-tenant cloud deployment**: Configure OAuth provider
   - See [L5_MCP_PLAN.md](../L5_MCP_PLAN.md) Phase 2
   - Requires GitHub, Google, WorkOS, Auth0, or Azure OAuth

## Tools Not Working

### Symptom
Tool calls fail or return errors.

### Solutions

1. **Check tool name**
   All tools are namespaced: `watercooler_v1_*`

   ✅ Correct:
   ```
   watercooler_v1_list_threads
   watercooler_v1_say
   ```

   ❌ Incorrect:
   ```
   list_threads
   say
   ```

2. **Verify tool availability**
   Check your client's tool list:
   - Should show 9 tools total
   - All prefixed with `watercooler_v1_`

3. **Check parameters**
   Each tool has required parameters. Example:
   ```
   watercooler_v1_say(
       topic="required",
       title="required",
       body="required"
   )
   ```

4. **Review error message**
   Error messages include helpful context:
   ```
   Error adding entry to 'topic': [specific error]
   ```

## Git Not Found

### Symptom
```
FileNotFoundError: git command not found
```

### Solutions

1. **Install git**
   ```bash
   # macOS
   brew install git

   # Linux
   sudo apt-get install git
   ```

2. **Verify git in PATH**
   ```bash
   which git
   git --version
   ```

3. **Fallback behavior**
   If git is not available:
   - Upward search stops at HOME directory
   - All other functionality works normally

## Upward Search Not Finding .watercooler

### Symptom
Server finds `CWD/.watercooler` instead of repo root `.watercooler`.

### Solutions

1. **Verify .watercooler exists at repo root**
   ```bash
   cd /path/to/repo
   ls -la .watercooler
   ```

2. **Check you're in a git repository**
   ```bash
   git status
   ```

   If not in a git repo:
   - Search stops at HOME directory
   - May not find repo-level `.watercooler`

3. **Use explicit WATERCOOLER_DIR**
   ```toml
   [mcp_servers.watercooler.env]
   WATERCOOLER_DIR = "/path/to/repo/.watercooler"
   ```

## Ball Not Flipping

### Symptom
`watercooler_v1_say` doesn't flip the ball to counterpart.

### Solutions

1. **Check agents.json configuration**
   ```bash
   cat .watercooler/agents.json
   ```

   Should define counterparts:
   ```json
   {
     "agents": {
       "Claude": {"counterpart": "Codex"},
       "Codex": {"counterpart": "Claude"}
     }
   }
   ```

2. **Create agents.json if missing**
   See [docs/integration.md](./integration.md) for configuration guide.

3. **Verify with read_thread**
   ```
   watercooler_v1_read_thread(topic="your-topic")
   ```
   Check `Ball:` line in output.

## Server Crashes or Hangs

### Symptom
MCP server stops responding or crashes.

### Solutions

1. **Check server logs**
   - Codex: Check terminal output
   - Claude Desktop: Check console logs
   - Claude Code: Check Developer Console

2. **Verify Python version**
   ```bash
   python3 --version
   ```
   Required: Python 3.10 or later

3. **Update dependencies**
   ```bash
   pip install -e .[mcp] --upgrade
   ```

4. **Test server directly**
   ```bash
   python3 -m watercooler_mcp
   ```
   Should start without errors.

## Format Parameter Errors

### Symptom
```
Error: Phase 1A only supports format='markdown'
```

### Explanation
Phase 1A only supports markdown output. JSON support is planned for Phase 1B.

### Solutions

1. **Use markdown format (default)**
   ```
   watercooler_v1_list_threads()
   # or explicitly
   watercooler_v1_list_threads(format="markdown")
   ```

2. **Wait for Phase 1B**
   JSON support coming in future release.

## Getting More Help

### Debug with Health Check

```
watercooler_v1_health
```

Returns comprehensive diagnostics:
- Server version
- Agent identity
- Threads directory location
- Directory existence
- Python executable
- FastMCP version

### Debug with Whoami

```
watercooler_v1_whoami
```

Returns:
- Your agent name
- Client ID (if available)
- Session ID

### Enable Verbose Logging

Run server directly to see detailed output:
```bash
python3 -m watercooler_mcp
```

### Report Issues

If you encounter a bug:
1. Run `watercooler_v1_health` and include output
2. Include your MCP configuration (redact sensitive data)
3. Include error messages and stack traces
4. Open an issue on GitHub

---

**Still having trouble?** Open an issue with:
- Output from `watercooler_v1_health`
- Your configuration (sanitized)
- Error messages
- Steps to reproduce
