# Environment Variables Reference

Complete reference for all watercooler-cloud environment variables.

---

## Quick Reference

| Variable | Required | Default | Used By | Purpose |
|----------|----------|---------|---------|---------|
| [`WATERCOOLER_AGENT`](#watercooler_agent) | MCP: Yes<br>CLI: No | `"Agent"` | MCP Server | Agent identity for entries |
| [`WATERCOOLER_THREADS_BASE`](#watercooler_threads_base) | No | `~/.watercooler-threads` | MCP Server | Local clone root for threads repos |
| [`WATERCOOLER_THREADS_PATTERN`](#watercooler_threads_pattern) | No | `git@github.com:{org}/{repo}-threads.git` | MCP Server | Remote threads repo URL template |
| [`WATERCOOLER_AUTO_BRANCH`](#watercooler_auto_branch) | No | `"1"` | MCP Server | Auto-create/check out matching branch |
| [`WATERCOOLER_DIR`](#watercooler_dir) | No | _Unset_ | MCP & CLI | Manual override for a fixed threads directory |
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
[mcp_servers.wc_universal.env]
WATERCOOLER_AGENT = "Codex"
```

**Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "watercooler-universal": {
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
    "watercooler-universal": {
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

### WATERCOOLER_THREADS_BASE

**Purpose:** Root directory where the MCP server stores local clones of threads repositories in universal mode.

**Required:** No

**Default:** `~/.watercooler-threads`

**Format:** Absolute path (environment variables are expanded)

**Used by:** MCP Server

```bash
export WATERCOOLER_THREADS_BASE="/Volumes/data/watercooler-threads"
```

---

### WATERCOOLER_THREADS_PATTERN

**Purpose:** Template for constructing the remote threads repository URL from `{org}` and `{repo}`.

**Required:** No

**Default:** `git@github.com:{org}/{repo}-threads.git`

**Used by:** MCP Server

```bash
export WATERCOOLER_THREADS_PATTERN="https://git.example.com/{org}/{repo}-threads.git"
```

---

### WATERCOOLER_AUTO_BRANCH

**Purpose:** Controls automatic creation and checkout of the matching branch in the threads repository.

**Required:** No

**Default:** `"1"` (enabled)

**Used by:** MCP Server

```bash
# Disable automatic branch creation
export WATERCOOLER_AUTO_BRANCH="0"
```

---

### WATERCOOLER_DIR

**Purpose:** Manual override for a fixed threads directory (disables automatic discovery).

**Required:** No

**Default:** _Unset_

**Format:** Absolute or relative path (e.g., `"/Users/agent/.watercooler-threads/custom-project-threads"`, `"~/threads"`)

**Used by:** MCP Server & CLI

**Details:**

Universal mode derives the threads repository from git metadata (`code_path`, repo origin, branch). Set this variable only when you intentionally keep threads in a specific location that differs from the standard `~/.watercooler-threads/<org>/<repo>-threads` pattern.

**When to set explicitly:**
- Running in an environment without git metadata (rare)
- Executing targeted tests that need an isolated threads sandbox
- Temporarily pointing at a staging directory like `$HOME/.watercooler-threads/tmp-migration` while you relocate it into the sibling `<repo>-threads` repository

**Configuration examples:**

**Absolute path example:**
```bash
export WATERCOOLER_DIR="/Users/agent/.watercooler-threads/custom-project-threads"
```

**Alternative location:**
```bash
export WATERCOOLER_DIR="/Volumes/threads-cache/project-threads"
```

**MCP config example:**
```toml
[mcp_servers.wc_universal.env]
WATERCOOLER_DIR = "/Users/agent/.watercooler-threads/custom-project-threads"
```

**VS Code workspace example:**
```json
{
  "mcp.servers": {
    "watercooler-universal": {
      "env": {
        "WATERCOOLER_DIR": "/Users/agent/.watercooler-threads/custom-project-threads"
      }
    }
  }
}
```

**Related:**
- See [SETUP_AND_QUICKSTART.md](./SETUP_AND_QUICKSTART.md#3-optional-global-overrides) for the canonical setup flow
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
[mcp_servers.wc_universal.env]
WATERCOOLER_AGENT = "Claude"
WATERCOOLER_GIT_REPO = "git@github.com:team/threads.git"
WATERCOOLER_THREADS_BASE = "/Users/agent/.watercooler-threads"
```

**Best practices:**
- Use **dedicated repository** for threads (not mixed with code)
- Use **SSH** with deploy keys for security
- Set [`WATERCOOLER_GIT_SSH_KEY`](#watercooler_git_ssh_key) for custom keys
- Let the server clone into `WATERCOOLER_THREADS_BASE` (avoid manual per-project overrides)

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
[mcp_servers.wc_universal.env]
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
[mcp_servers.wc_universal.env]
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
[mcp_servers.wc_universal.env]
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
[mcp_servers.wc_universal.env]
WATERCOOLER_AGENT = "Claude"
```

**Explanation:**
- Threads are stored automatically in `~/.watercooler-threads/<org>/<repo>-threads`
- No cloud sync
- Works from any subdirectory in the project (pass `code_path` with each tool call)

---

### Manual Threads Directory

**Use only for short-lived experiments or specialized testing:**

```toml
[mcp_servers.wc_universal.env]
WATERCOOLER_AGENT = "Codex"
WATERCOOLER_DIR = "/Users/agent/.watercooler-threads/custom-project-threads"
```

**Use cases:**
- Temporarily reading threads left in a repo-local staging folder before relocating them
- Running in environments without git metadata (e.g., ad-hoc scripts)
- Experimental setups where a bespoke location is required

---

### Cloud Sync (Team Collaboration)

**Full setup for distributed team:**

```toml
[mcp_servers.wc_universal.env]
WATERCOOLER_AGENT = "Claude"
WATERCOOLER_GIT_REPO = "git@github.com:team/threads.git"
WATERCOOLER_THREADS_BASE = "/Users/agent/.watercooler-threads"
WATERCOOLER_GIT_SSH_KEY = "/Users/agent/.ssh/id_ed25519_watercooler"
WATERCOOLER_GIT_AUTHOR = "Alice's Claude"
WATERCOOLER_GIT_EMAIL = "alice+claude@team.com"
```

**Explanation:**
- `WATERCOOLER_GIT_REPO` enables cloud mode
- `WATERCOOLER_THREADS_BASE` controls where clones live locally
- `WATERCOOLER_GIT_SSH_KEY` uses dedicated deploy key
- `WATERCOOLER_GIT_AUTHOR/EMAIL` customize git identity

**Related:**
- See [CLOUD_SYNC_GUIDE.md](../.mothballed/docs/CLOUD_SYNC_GUIDE.md) for complete cloud setup

---

### Multiple Projects

**Dynamic directory per project:**

```toml
[mcp_servers.wc_universal.env]
WATERCOOLER_AGENT = "Claude"
# No additional environment variables needed
```

The server resolves the correct sibling threads repository for whichever code repo you open (based on `code_path`).

**Per-project overrides:**

If you still maintain repo-local threads directories, you can set `WATERCOOLER_DIR` in a `.envrc`, but this disables universal discovery. Prefer converting those projects to the sibling repo layout.

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

1. **Use universal defaults:** `watercooler_v1_health(code_path=".")` will report the expected threads directory under `~/.watercooler-threads/<org>/<repo>-threads`. Ensure that path exists and is writable.

2. **Override location (manual):**
   ```bash
   export WATERCOOLER_DIR="/full/path/to/custom-threads"
   ```
   Only do this when relocating a staging folder that you created manually inside the code repo.

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
cd ~/.watercooler-threads/<org>/<repo>-threads
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
