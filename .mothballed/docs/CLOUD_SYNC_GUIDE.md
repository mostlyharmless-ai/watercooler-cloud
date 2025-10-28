# Cloud Sync Guide - Git-Based Team Collaboration

[Documentation Hub](README.md) > **Cloud Sync Guide**

Enable distributed team collaboration using git-based synchronization.

---

## Overview

**Cloud Sync Mode** allows multiple team members (and their AI agents) to collaborate on watercooler threads using git as the synchronization layer.

### When to Use Cloud Sync

**✅ Enable cloud sync if you need:**
- Async collaboration across timezones
- Multiple team members working on same project
- Centralized thread history (GitHub/GitLab)
- AI agents collaborating across different machines

**❌ Stick with local mode if:**
- Single developer working solo
- AI agents all on same machine
- Don't need cross-machine collaboration

---

## How It Works

```
┌──────────────┐      pull      ┌──────────────┐      pull      ┌──────────────┐
│   Machine A  │ ◄──────────────┤ Git Repo     │───────────────►│  Machine B   │
│   (Claude)   │                 │ (GitHub)     │                 │  (Codex)     │
└──────────────┘                 └──────────────┘                 └──────────────┘
       │                                                                  │
       │ say(...) → commit + push                commit + push ← say(...) │
       │                                                                  │
       └───────────────────► Automatic sync ◄──────────────────────────┘
```

**Key features:**
- **Pull before read** - Always get latest thread content
- **Commit + push after write** - Automatic sync on every change
- **Entry-ID idempotency** - Prevents duplicate entries on retry
- **Retry logic** - Handles concurrent writes gracefully
- **Clean conflict handling** - Aborts on merge conflicts (manual resolution)

---

## Quick Setup (5 minutes)

### Step 1: Create GitHub Repository

```bash
# Create a new repository on GitHub
gh repo create my-team/watercooler-threads --private

# Or use existing repository
```

**Recommended:** Use a **dedicated repository** for threads (not your code repo).

### Step 2: Clone Repository Locally

```bash
# Clone to where you want threads stored
git clone git@github.com:my-team/watercooler-threads.git ~/.watercooler-threads
```

### Step 3: Configure Environment Variables

Add to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):

```bash
# Enable cloud sync mode
export WATERCOOLER_GIT_REPO="git@github.com:my-team/watercooler-threads.git"

# Point to cloned directory
export WATERCOOLER_DIR="$HOME/.watercooler-threads"

# Optional: Custom git identity
export WATERCOOLER_GIT_AUTHOR="Your Name"
export WATERCOOLER_GIT_EMAIL="you@example.com"

# Optional: SSH key (if not using default)
export WATERCOOLER_GIT_SSH_KEY="$HOME/.ssh/id_ed25519_watercooler"
```

### Step 4: Configure MCP Server

Update your MCP configuration to include environment variables:

**For Claude Code** (`~/.config/claude-code/config.toml`):
```toml
[[mcpServers]]
command = "python3"
args = ["-m", "watercooler_mcp"]
env = {
  WATERCOOLER_AGENT = "Claude",
  WATERCOOLER_GIT_REPO = "git@github.com:my-team/watercooler-threads.git",
  WATERCOOLER_DIR = "/Users/you/.watercooler-threads"
}
```

**For Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "watercooler": {
      "command": "python3",
      "args": ["-m", "watercooler_mcp"],
      "env": {
        "WATERCOOLER_AGENT": "Claude",
        "WATERCOOLER_GIT_REPO": "git@github.com:my-team/watercooler-threads.git",
        "WATERCOOLER_DIR": "/Users/you/.watercooler-threads"
      }
    }
  }
}
```

### Step 5: Test Your Setup

```bash
# Verify git access
cd ~/.watercooler-threads
git pull

# Test MCP server with health check
# (This will be available through your AI agent once configured)
```

---

## SSH Key Setup

### Generate Deploy Key (Recommended)

For security, use a **dedicated SSH key** for watercooler:

```bash
# Generate new key
ssh-keygen -t ed25519 -C "watercooler@myteam" -f ~/.ssh/id_ed25519_watercooler

# Add to ssh-agent
ssh-add ~/.ssh/id_ed25519_watercooler

# Copy public key
cat ~/.ssh/id_ed25519_watercooler.pub
```

### Add to GitHub

1. Go to your repository → **Settings** → **Deploy keys**
2. Click **Add deploy key**
3. Paste public key
4. ✅ Enable **Allow write access**
5. Save

### Configure Watercooler to Use Key

```bash
export WATERCOOLER_GIT_SSH_KEY="$HOME/.ssh/id_ed25519_watercooler"
```

---

## Team Workflow

### Setup for Each Team Member

Each team member should:

1. **Clone the threads repository** to their machine
2. **Configure environment variables** with their identity
3. **Set up MCP server** with cloud sync enabled
4. **Configure git identity** (name/email)

### Daily Usage

**No manual git commands needed!** The MCP server handles all git operations:

```
Team Member A                    Team Member B
     │                                  │
     │ say("feature-auth", ...)         │
     │ → pull → append → commit → push  │
     │                                  │
     │                                  │ list_threads()
     │                                  │ → pull
     │                                  │ → sees new entry from A
     │                                  │
     │                                  │ say("feature-auth", ...)
     │                                  │ → pull → append → commit → push
     │                                  │
     │ read_thread("feature-auth")      │
     │ → pull                            │
     │ → sees response from B           │
```

**It just works!** ✨

---

## Configuration Reference

### Environment Variables

| Variable | Required | Purpose | Example |
|----------|----------|---------|---------|
| `WATERCOOLER_GIT_REPO` | ✅ Yes (for cloud mode) | Git repository URL | `git@github.com:team/threads.git` |
| `WATERCOOLER_DIR` | Recommended | Local threads directory | `$HOME/.watercooler-threads` |
| `WATERCOOLER_GIT_SSH_KEY` | Optional | Path to SSH private key | `$HOME/.ssh/id_ed25519_watercooler` |
| `WATERCOOLER_GIT_AUTHOR` | Optional | Git commit author name | `"Claude Agent"` |
| `WATERCOOLER_GIT_EMAIL` | Optional | Git commit author email | `claude@team.com` |
| `WATERCOOLER_AGENT` | Recommended | Agent identity | `"Claude"`, `"Codex"` |

### Defaults

- **Author name**: "Watercooler MCP" (if not specified)
- **Author email**: "mcp@watercooler.dev" (if not specified)
- **SSH key**: Uses default from `~/.ssh/` (if not specified)

---

## Troubleshooting

### "fatal: Could not read from remote repository"

**Cause:** SSH key not configured or not added to GitHub.

**Solution:**
1. Verify SSH key exists: `ls -la ~/.ssh/id_ed25519_watercooler`
2. Test GitHub access: `ssh -T git@github.com`
3. Add key to ssh-agent: `ssh-add ~/.ssh/id_ed25519_watercooler`
4. Verify key is added to GitHub deploy keys

### "Git push rejected (non-fast-forward)"

**Cause:** Someone else pushed while you were writing.

**Solution:** Automatic! The MCP server will:
1. Pull with rebase
2. Retry push
3. Repeat up to 3 times
4. Fail gracefully if still rejected

### "Merge conflict during rebase"

**Cause:** Two people edited the same lines simultaneously (rare).

**Solution:**
1. The operation will abort safely
2. Read the thread: `watercooler_v1_read_thread("topic")`
3. See what changed
4. Try your operation again (Entry-ID prevents duplicates)

### "Entry appears twice"

**Should not happen** - Entry-IDs prevent duplicates.

**If it does:**
1. Check if WATERCOOLER_GIT_REPO is set correctly
2. Verify git sync is actually enabled
3. Report as bug (this shouldn't happen!)

### Directory Not Found

**Cause:** `WATERCOOLER_DIR` points to non-existent directory.

**Solution:**
```bash
# Create and clone
mkdir -p ~/.watercooler-threads
git clone git@github.com:team/threads.git ~/.watercooler-threads
```

---

## Best Practices

### 1. Use Dedicated Repository

**✅ Recommended:**
```
my-team/watercooler-threads      # Threads only
my-team/my-project               # Code
```

**❌ Not recommended:**
```
my-team/my-project
├── src/                         # Code
├── .watercooler/               # Threads mixed with code
```

**Why?**
- Cleaner git history
- Separate permissions
- No merge conflicts with code
- Easier backup/restore

### 2. Use Deploy Keys

Don't reuse your personal SSH key - create a dedicated deploy key for watercooler.

### 3. Set Agent Identity

Always set `WATERCOOLER_AGENT` so entries are properly attributed:

```bash
export WATERCOOLER_AGENT="Claude"  # or "Codex", etc.
```

### 4. Small, Focused Threads

**✅ Good:**
- `feature-auth` - Authentication implementation
- `bug-login-redirect` - Specific bug fix
- `design-api-versioning` - Design discussion

**❌ Too broad:**
- `general-discussion` - Will grow forever
- `all-features` - Loses focus

### 5. Close Threads When Done

```bash
watercooler set-status feature-auth CLOSED
```

This keeps the index clean and focused on active work.

---

## Advanced Topics

### Running Your Own Git Server

Instead of GitHub, you can use:
- **GitLab** (self-hosted or gitlab.com)
- **Gitea** (lightweight self-hosted)
- **Bitbucket**
- **Any git server** with SSH access

Just change `WATERCOOLER_GIT_REPO` to your server's URL.

### Read-Only Mode

To prevent writes (e.g., for observers):

Don't set `WATERCOOLER_GIT_REPO` - threads will be read-only from local directory.

### Multiple Projects

Use different directories and environment variables per project:

```bash
# Project A
cd ~/project-a
export WATERCOOLER_DIR=~/project-a/.watercooler
export WATERCOOLER_GIT_REPO=git@github.com:team/project-a-threads.git

# Project B
cd ~/project-b
export WATERCOOLER_DIR=~/project-b/.watercooler
export WATERCOOLER_GIT_REPO=git@github.com:team/project-b-threads.git
```

Or use project-specific `.envrc` files with [direnv](https://direnv.net/).

---

## Implementation Details

For deep-dive into architecture and implementation:
- **[CLOUD_SYNC_STRATEGY.md](CLOUD_SYNC_STRATEGY.md)** - Complete implementation guide
- **[L5_MCP_PLAN.md](../L5_MCP_PLAN.md)** - Phase 2A development plan

---

## FAQ

**Q: Can I use HTTPS instead of SSH?**
A: Yes, but you'll need to configure git credentials. SSH with deploy keys is recommended.

**Q: What happens if I'm offline?**
A: Local mode continues to work. Sync will happen when you're back online.

**Q: Can I mix CLI and MCP usage?**
A: Yes! Both use the same files and locking. Cloud sync only works with MCP server though.

**Q: How do I migrate existing threads to cloud sync?**
A: Just commit them to your git repo and configure the environment variables.

**Q: Is there a size limit for threads?**
A: No hard limit, but git performance degrades with very large files (>1MB). Keep threads focused.

**Q: Can I use this for sensitive information?**
A: Use private repositories and consider encrypting sensitive data before committing.

---

**Next Steps:**
- Set up your first cloud-synced thread
- Read [Use Cases Guide](USE_CASES.md) for collaboration patterns
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for MCP issues

---

*Last updated: 2025-10-09*
