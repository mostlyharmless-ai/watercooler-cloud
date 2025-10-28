# Environment Variables Reference

Complete reference for all watercooler-collab environment variables.

---

## Quick Reference

| Variable | Required | Default | Used By | Purpose |
|----------|----------|---------|---------|---------|
| [`WATERCOOLER_AGENT`](#watercooler_agent) | MCP: Yes<br>CLI: No | `"Agent"` | MCP Server | Agent identity for entries |
| [`WATERCOOLER_DIR`](#watercooler_dir) | No | `./.watercooler` | MCP & CLI | Threads directory location |
| [`WATERCOOLER_GIT_REPO`](#watercooler_git_repo) | Cloud: Yes<br>Local: No | None | MCP Server | Git repository URL (enables cloud sync) |
| [`WATERCOOLER_GIT_SSH_KEY`](#watercooler_git_ssh_key) | No | None | MCP Server | Path to SSH private key |
| [`WATERCOOLER_GIT_AUTHOR`](#watercooler_git_author) | No | `"Watercooler MCP"` | MCP Server | Git commit author name |
| [`WATERCOOLER_GIT_EMAIL`](#watercooler_git_email) | No | `"mcp@watercooler.dev"` | MCP Server | Git commit author email |
| [`WATERCOOLER_TEMPLATES`](#watercooler_templates) | No | Built-in | MCP & CLI | Custom templates directory |
| [`WATERCOOLER_USER`](#watercooler_user) | No | OS username | Lock System | Override username in lock files |

---

## Core Variables

### WATERCOOLER_AGENT

**Purpose:** Agent identity used in thread entries and ball ownership.

**Required:**
- **MCP Server:** Yes (recommended)
- **CLI:** No (defaults to "Team")

**Default:** `"Agent"` (MCP), `"Team"` (CLI)

**Format:** String (e.g., `"Claude"`, `"Codex"`, `"GPT-4"`)

**Used by:** MCP Server

**Details:**

Determines your agent identity in watercooler threads. When you create entries, they appear as:
```
Entry: Claude (agent) 2025-10-10T08:00:00Z
```

Where:
- `Claude` = Agent name from `WATERCOOLER_AGENT`
- `(agent)` = OS username from `getpass.getuser()` (automatically appended)

**Precedence (MCP only):**
1. `WATERCOOLER_AGENT` env var (highest priority)
2. `client_id` from MCP Context (auto-detected from client name)
3. Fallback: `"Agent"`

**Client ID mapping:**
- "Claude Desktop" → "Claude"
- "Claude Code" → "Claude"
- Other values passed through as-is

**Configuration examples:**

**Codex (`~/.codex/config.toml`):**
```toml
[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "Codex"
```

**Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "watercooler": {
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
      "env": {
        "WATERCOOLER_AGENT": "Claude"
      }
    }
  }
}
```

**Shell:**
```bash
export WATERCOOLER_AGENT="Claude"
```

**Related:**
- See [MCP Server Guide](./mcp-server.md) for complete MCP setup
- See [WATERCOOLER_USER](#watercooler_user) for username customization

---

### WATERCOOLER_DIR

**Purpose:** Override threads directory location.

**Required:** No

**Default:** `./.watercooler` (current working directory)

**Format:** Absolute or relative path (e.g., `"/Users/agent/project/.watercooler"`, `"~/threads"`)

**Used by:** MCP Server & CLI

**Details:**

Specifies where watercooler threads are stored. Supports three resolution strategies:

**Resolution order:**
1. `WATERCOOLER_DIR` env var (explicit override - highest priority)
2. Upward search from CWD for existing `.watercooler/` directory
   - Stops at: git repository root, HOME directory, or filesystem root
   - Works from any subdirectory in your repo
3. Fallback: `{CWD}/.watercooler` (auto-created if needed)

**Upward search behavior:**

The MCP server automatically searches upward from your current working directory to find an existing `.watercooler/` directory. This means:

✅ **Works without configuration** if `.watercooler/` exists at repo root
✅ **No need to set WATERCOOLER_DIR** for most projects
✅ **Consistent across subdirectories** within same project

**When to set explicitly:**
- Working with multiple projects simultaneously
- Want threads outside current project
- Using cloud sync with dedicated threads repository
- Testing in non-standard directory structure

**Configuration examples:**

**Absolute path (recommended for reliability):**
```bash
export WATERCOOLER_DIR="/Users/agent/project/.watercooler"
```

**Home directory:**
```bash
export WATERCOOLER_DIR="$HOME/.watercooler-threads"
```

**MCP config:**
```toml
[mcp_servers.watercooler.env]
WATERCOOLER_DIR = "/Users/agent/project/.watercooler"
```

**VS Code workspace variable (Cline):**
```json
{
  "mcp.servers": {
    "watercooler": {
      "env": {
        "WATERCOOLER_DIR": "${workspaceFolder}/.watercooler"
      }
    }
  }
}
```

**Relative paths:**
```bash
# Relative to CWD
export WATERCOOLER_DIR="./my-threads"

# Relative to home
export WATERCOOLER_DIR="~/threads"
```

**Related:**
- See [QUICKSTART.md](./QUICKSTART.md#environment-variables) for basic setup
- See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md) for team collaboration

---

## Cloud Sync Variables

These variables enable git-based cloud synchronization for team collaboration. Only used by the MCP server.

### WATERCOOLER_GIT_REPO

**Purpose:** Git repository URL for cloud sync (enables cloud mode).

**Required:** Yes (for cloud sync), No (for local mode)

**Default:** None

**Format:** Git URL (SSH or HTTPS)

**Used by:** MCP Server (cloud sync)

**Details:**

Setting this variable **enables cloud sync mode**:
- **Pull before read** - Always fetches latest thread content
- **Commit + push after write** - Automatic sync on every change
- **Entry-ID idempotency** - Prevents duplicate entries on retry
- **Retry logic** - Handles concurrent writes gracefully

**Supported URL formats:**

**SSH (recommended):**
```bash
export WATERCOOLER_GIT_REPO="git@github.com:my-team/watercooler-threads.git"
export WATERCOOLER_GIT_REPO="git@gitlab.com:org/threads.git"
```

**HTTPS:**
```bash
export WATERCOOLER_GIT_REPO="https://github.com/my-team/watercooler-threads.git"
```

**Local mode (unset):**
```bash
unset WATERCOOLER_GIT_REPO  # Disables cloud sync
```

**Configuration examples:**

**MCP config with cloud sync:**
```toml
[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "Claude"
WATERCOOLER_GIT_REPO = "git@github.com:team/threads.git"
WATERCOOLER_DIR = "/Users/agent/.watercooler-threads"
```

**Best practices:**
- Use **dedicated repository** for threads (not mixed with code)
- Use **SSH** with deploy keys for security
- Set [`WATERCOOLER_GIT_SSH_KEY`](#watercooler_git_ssh_key) for custom keys
- Clone repository locally and point `WATERCOOLER_DIR` to it

**Related:**
- See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md) for complete setup
- See [CLOUD_SYNC_STRATEGY.md](../.mothballed/docs/CLOUD_SYNC_STRATEGY.md) for architecture details

---

## Cloud Remote MCP (Cloudflare Worker) Variables

These variables are configured in the Cloudflare Worker (`wrangler.toml` and Wrangler secrets) and control the Remote MCP gateway.

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `BACKEND_URL` | Var | — | HTTPS URL of the Python HTTP facade (backend) |
| `DEFAULT_AGENT` | Var | `"Agent"` | Fallback agent label when not provided by client |
| `KV_PROJECTS` | Binding | — | KV namespace for per‑user ACLs, session metadata, rate limits |
| `INTERNAL_AUTH_SECRET` | Secret | — | Shared secret for Worker ↔ Backend auth (sent as `X‑Internal‑Auth`) |
| `ALLOW_DEV_SESSION` | Var | `"false"` | Optional (staging only). If `"true"`, allows temporary `?session=dev` testing; never enable in production |
| `AUTO_ENROLL_PROJECTS` | Var | `"false"` | If `"true"`, `set_project`/`create_project` may auto‑add requested project to caller’s ACL after backend validation; prefer explicit ACL seeding |

Notes
- Staging posture is auth‑only by default: keep `ALLOW_DEV_SESSION="false"` and use OAuth or tokens issued at `/console`.
- See `cloudflare-worker/scripts/README.md` for deployment and security guidance.

### WATERCOOLER_GIT_SSH_KEY

**Purpose:** Path to SSH private key for git authentication.

**Required:** No

**Default:** None (uses default SSH keys from `~/.ssh/`)

**Format:** Absolute path to private key file (e.g., `"/Users/agent/.ssh/id_ed25519_watercooler"`)

**Used by:** MCP Server (cloud sync)

**Details:**

Specifies a custom SSH private key for git operations. If not set, git uses the default SSH key resolution:
1. `~/.ssh/id_ed25519`
2. `~/.ssh/id_rsa`
3. SSH agent keys

**When to set:**
- Using dedicated deploy key for watercooler
- Multiple SSH keys for different repositories
- Need to isolate watercooler git access

**Configuration examples:**

**Shell:**
```bash
export WATERCOOLER_GIT_SSH_KEY="$HOME/.ssh/id_ed25519_watercooler"
```

**MCP config:**
```toml
[mcp_servers.watercooler.env]
WATERCOOLER_GIT_REPO = "git@github.com:team/threads.git"
WATERCOOLER_GIT_SSH_KEY = "/Users/agent/.ssh/id_ed25519_watercooler"
```

**Generate dedicated key:**
```bash
ssh-keygen -t ed25519 -C "watercooler@myteam" -f ~/.ssh/id_ed25519_watercooler
ssh-add ~/.ssh/id_ed25519_watercooler
```

**Add to GitHub/GitLab:**
1. Copy public key: `cat ~/.ssh/id_ed25519_watercooler.pub`
2. Add as deploy key with write access in repository settings

**Related:**
- See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md#ssh-key-setup) for detailed setup
- See [WATERCOOLER_GIT_REPO](#watercooler_git_repo) for enabling cloud sync

---

### WATERCOOLER_GIT_AUTHOR

**Purpose:** Git commit author name for cloud sync commits.

**Required:** No

**Default:** `"Watercooler MCP"`

**Format:** String (e.g., `"Claude Agent"`, `"Alice's Claude"`)

**Used by:** MCP Server (cloud sync)

**Details:**

Sets the git author name for commits made by the MCP server. Appears in git history as:
```
Author: Claude Agent <mcp@watercooler.dev>
Date:   Wed Oct 10 08:00:00 2025 +0000

    Claude: Implementation complete (feature-auth)

    Watercooler-Entry-ID: 01HQZXY...
    Watercooler-Topic: feature-auth
```

**Configuration examples:**

**Shell:**
```bash
export WATERCOOLER_GIT_AUTHOR="Claude Agent"
```

**MCP config:**
```toml
[mcp_servers.watercooler.env]
WATERCOOLER_GIT_AUTHOR = "Claude Agent"
WATERCOOLER_GIT_EMAIL = "claude@team.com"
```

**Team setup with per-user agents:**
```bash
# Alice's machine
export WATERCOOLER_GIT_AUTHOR="Alice's Claude"

# Bob's machine
export WATERCOOLER_GIT_AUTHOR="Bob's Claude"
```

**Related:**
- See [WATERCOOLER_GIT_EMAIL](#watercooler_git_email) for author email
- See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md) for team setup

---

### WATERCOOLER_GIT_EMAIL

**Purpose:** Git commit author email for cloud sync commits.

**Required:** No

**Default:** `"mcp@watercooler.dev"`

**Format:** Email string (e.g., `"claude@team.com"`)

**Used by:** MCP Server (cloud sync)

**Details:**

Sets the git author email for commits made by the MCP server.

**Configuration examples:**

**Shell:**
```bash
export WATERCOOLER_GIT_EMAIL="claude@team.com"
```

**MCP config:**
```toml
[mcp_servers.watercooler.env]
WATERCOOLER_GIT_AUTHOR = "Claude Agent"
WATERCOOLER_GIT_EMAIL = "claude@team.com"
```

**Related:**
- See [WATERCOOLER_GIT_AUTHOR](#watercooler_git_author) for author name
- See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md) for team setup

---

## Advanced Variables

### WATERCOOLER_TEMPLATES

**Purpose:** Override path to custom templates directory.

**Required:** No

**Default:** Built-in templates (from `src/watercooler/templates/`)

**Format:** Absolute path to directory containing template files

**Used by:** MCP Server & CLI

**Details:**

Allows customization of thread and entry templates. Templates use placeholder syntax:
- `{{KEY}}` or `<KEY>` for variable substitution
- Available placeholders: `TOPIC`, `AGENT`, `UTC`, `TITLE`, `BODY`, `TYPE`, `ROLE`, `BALL`, `STATUS`

**Template files:**
- `_TEMPLATE_topic_thread.md` - New thread initialization
- `_TEMPLATE_entry_block.md` - Entry format

**Configuration examples:**

**Shell:**
```bash
export WATERCOOLER_TEMPLATES="/Users/agent/my-templates"
```

**CLI:**
```bash
watercooler say feature-auth --title "Update" --body "..." --templates-dir /path/to/templates
```

**Custom template example (`_TEMPLATE_entry_block.md`):**
```markdown
---
Entry: {{AGENT}} {{UTC}}
Type: {{TYPE}}
Title: {{TITLE}}

{{BODY}}
```

**Related:**
- See [TEMPLATES.md](./TEMPLATES.md) for template customization guide
- See [integration.md](./integration.md) for Python API usage

---

### WATERCOOLER_USER

**Purpose:** Override username for lock file metadata.

**Required:** No

**Default:** OS username from `getpass.getuser()`

**Format:** String (e.g., `"agent"`, `"alice"`)

**Used by:** Lock System (internal)

**Details:**

**This is a low-level variable that most users don't need to set.**

Used only by the advisory locking system to record who owns a lock. Does **not** affect agent identity in entries (see [`WATERCOOLER_AGENT`](#watercooler_agent) for that).

**Automatic behavior:**

The lock system automatically determines username via `getpass.getuser()` which checks:
1. `os.getlogin()` - login name of user running process
2. Environment variables: `$LOGNAME`, `$USER`, `$LNAME`, `$USERNAME`
3. System user database: `pwd.getpwuid(os.getuid())[0]`

**When to set:**
- Running in containerized environment with wrong username
- Testing lock behavior with different identities
- Debugging lock contention issues

**Configuration examples:**

**Shell:**
```bash
export WATERCOOLER_USER="alice"
```

**Lock file format:**
```
PID: 12345
User: alice
Host: macbook.local
Created: 2025-10-10T08:00:00Z
```

**Related:**
- See [integration.md](./integration.md#locking-configuration) for lock system details
- See [FAQ.md](./FAQ.md) for lock behavior explanation

---

## Configuration Patterns

### Basic MCP Setup (Local Mode)

**Minimal configuration for single developer:**

```toml
[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "Claude"
```

**Explanation:**
- `WATERCOOLER_DIR` uses upward search (finds `.watercooler/` automatically)
- No cloud sync
- Works from any subdirectory in project

---

### Explicit Directory (Local Mode)

**When you want specific directory:**

```toml
[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "Codex"
WATERCOOLER_DIR = "/Users/agent/project/.watercooler"
```

**Use cases:**
- Multiple projects with different thread directories
- Non-standard project structure
- Testing in specific location

---

### Cloud Sync (Team Collaboration)

**Full setup for distributed team:**

```toml
[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "Claude"
WATERCOOLER_GIT_REPO = "git@github.com:team/threads.git"
WATERCOOLER_DIR = "/Users/agent/.watercooler-threads"
WATERCOOLER_GIT_SSH_KEY = "/Users/agent/.ssh/id_ed25519_watercooler"
WATERCOOLER_GIT_AUTHOR = "Alice's Claude"
WATERCOOLER_GIT_EMAIL = "alice+claude@team.com"
```

**Explanation:**
- `WATERCOOLER_GIT_REPO` enables cloud mode
- `WATERCOOLER_DIR` points to cloned repository
- `WATERCOOLER_GIT_SSH_KEY` uses dedicated deploy key
- `WATERCOOLER_GIT_AUTHOR/EMAIL` customize git identity

**Related:**
- See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md) for complete cloud setup

---

### Multiple Projects

**Dynamic directory per project:**

```toml
[mcp_servers.watercooler.env]
WATERCOOLER_AGENT = "Claude"
# No WATERCOOLER_DIR - uses upward search
```

**Launch from different project directories:**
```bash
cd ~/project-a
claude  # Uses ~/project-a/.watercooler

cd ~/project-b
claude  # Uses ~/project-b/.watercooler
```

**Alternative: Per-project config with direnv:**

**`~/project-a/.envrc`:**
```bash
export WATERCOOLER_DIR="$PWD/.watercooler"
export WATERCOOLER_GIT_REPO="git@github.com:team/project-a-threads.git"
```

**`~/project-b/.envrc`:**
```bash
export WATERCOOLER_DIR="$PWD/.watercooler"
export WATERCOOLER_GIT_REPO="git@github.com:team/project-b-threads.git"
```

**Related:**
- See [direnv](https://direnv.net/) for automatic environment switching
- See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md#multiple-projects)

---

## Troubleshooting

### Wrong Agent Name

**Symptom:** Entries show incorrect agent name

**Check current identity:**
```bash
# MCP: Ask agent to call watercooler_v1_whoami
# CLI: Check environment
echo $WATERCOOLER_AGENT
```

**Fix:**
```bash
export WATERCOOLER_AGENT="CorrectName"
# Or update MCP config and restart client
```

---

### Directory Not Found

**Symptom:** MCP server can't find threads directory

**Check resolution:**
```bash
# MCP: Ask agent to call watercooler_v1_health
# Look for "Threads Dir: /path" in output
```

**Fix options:**

1. **Let upward search find it:**
   ```bash
   # Create .watercooler at repo root
   mkdir -p $(git rev-parse --show-toplevel)/.watercooler
   ```

2. **Set explicit path:**
   ```bash
   export WATERCOOLER_DIR="/full/path/to/.watercooler"
   ```

---

### Cloud Sync Not Working

**Symptom:** Changes not syncing across machines

**Verify cloud mode enabled:**
```bash
echo $WATERCOOLER_GIT_REPO
# Should output git URL, not empty
```

**Check git access:**
```bash
cd $WATERCOOLER_DIR
git pull
# Should succeed without errors
```

**Common issues:**
- SSH key not configured → See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md#ssh-key-setup)
- Wrong repository URL → Verify `WATERCOOLER_GIT_REPO`
- Directory not a git clone → Re-clone repository

---

## See Also

- **[QUICKSTART.md](./QUICKSTART.md)** - Basic setup and configuration
- **[MCP Server Guide](./mcp-server.md)** - MCP server documentation
- **[CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md)** - Team collaboration setup
- **[integration.md](./integration.md)** - Python library configuration
- **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** - Common issues and solutions
- **[TEMPLATES.md](./TEMPLATES.md)** - Template customization

---

*Last updated: 2025-10-10*
