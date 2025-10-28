# Integration Guide

Complete guide for integrating watercooler-collab into your project.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
  - [CLI Usage](#cli-usage)
  - [Python Library Usage](#python-library-usage)
- [Configuration](#configuration)
  - [Threads Directory](#threads-directory)
  - [Templates Directory](#templates-directory)
  - [Environment Variables](#environment-variables)
- [Template Customization](#template-customization)
- [Agent Registry](#agent-registry)
- [Git Configuration](#git-configuration)
- [Integration Patterns](#integration-patterns)
- [Troubleshooting](#troubleshooting)

## Installation

### Development Installation

Currently watercooler-collab is available for development installation:

```bash
git clone https://github.com/mostlyharmless-ai/watercooler-collab.git
cd watercooler-collab
pip install -e .
```

### Future: PyPI Installation

```bash
# Not yet published
pip install watercooler-collab
```

### Verify Installation

```bash
# Check CLI is available
watercooler --help

# Check version
python3 -c "import watercooler; print(watercooler.__version__)"
```

---

## Quick Start

Watercooler-collab can be used three ways:
1. **MCP Server** - Automated integration with AI agents (Claude, Codex) - **Recommended**
2. **CLI** - Command-line tool for interactive use and scripts
3. **Python Library** - Programmatic API for custom automation

### MCP Server Integration (Recommended)

The **Model Context Protocol (MCP) server** allows AI agents to automatically use watercooler tools without manual CLI commands.

**Setup guides by client:**
- [Claude Code Setup](./CLAUDE_CODE_SETUP.md) - Configure Claude Code CLI
- [Claude Desktop Setup](./CLAUDE_DESKTOP_SETUP.md) - Configure Claude Desktop app
- [Codex Setup](./QUICKSTART.md#for-codex) - Configure Codex

**Benefits:**
- ✅ AI agents automatically discover and use watercooler tools
- ✅ Natural language interface ("Check my threads", "Respond to feature-x")
- ✅ No manual CLI commands needed
- ✅ Supports cloud sync for team collaboration

**Example workflow:**

```
User: "Claude, what watercooler threads do I have?"
Claude: [calls watercooler_v1_list_threads]
        "You have 3 threads where you have the ball..."

User: "Read the feature-auth thread and respond that it looks good"
Claude: [calls watercooler_v1_read_thread, then watercooler_v1_say]
        "✅ Entry added to 'feature-auth'"
```

See [MCP Server Guide](./mcp-server.md) for complete tool reference.

### CLI Usage

#### Initialize a Thread

```bash
watercooler init-thread feature-auth \
  --owner agent \
  --participants "agent, Claude, Codex" \
  --ball codex
```

This creates `.watercooler/feature-auth.md`:

```markdown
Title: Feature auth
Status: open
Ball: codex
Updated: 2025-10-07T10:00:00Z
Owner: agent
Participants: agent, Claude, Codex

# Feature auth
```

#### Add an Entry

```bash
watercooler say feature-auth \
  --agent Claude \
  --role critic \
  --title "Design Review" \
  --body "Authentication approach looks solid"
```

#### Update Status

```bash
watercooler set-status feature-auth in-review
```

#### List Threads

```bash
watercooler list
# Output:
# 2025-10-07T10:00:00Z    open    codex        feature-auth    .watercooler/feature-auth.md
```

See [README.md](../README.md) for complete CLI reference.

---

### Python Library Usage

#### Basic Operations

```python
from pathlib import Path
from watercooler import read, write, thread_path, bump_header, AdvisoryLock

# Configuration
threads_dir = Path(".watercooler")
topic = "feature-auth"

# Get thread path
t_path = thread_path(topic, threads_dir)
lock_path = threads_dir / f".{topic}.lock"

# Read thread with locking
with AdvisoryLock(lock_path, timeout=5):
    content = read(t_path)
    print(content)

# Update thread
with AdvisoryLock(lock_path, timeout=5):
    content = read(t_path)
    content = bump_header(content, status="in-review", ball="Claude")
    write(t_path, content)
```

#### Using Commands Module

For higher-level operations:

```python
from pathlib import Path
from watercooler.commands import init_thread, say, set_status

threads_dir = Path(".watercooler")

# Initialize thread
init_thread(
    "feature-auth",
    threads_dir=threads_dir,
    title="Feature Authentication",
    status="open",
    ball="codex"
)

# Add entry
say(
    "feature-auth",
    threads_dir=threads_dir,
    agent="Claude",
    role="critic",
    title="Review Complete",
    body="All good!"
)

# Update status
set_status("feature-auth", threads_dir=threads_dir, status="closed")
```

See [API Reference](api.md) for complete documentation.

---

## Configuration

### Threads Directory

Watercooler uses a **threads directory** to store thread files.

**Default:** `./.watercooler/` (hidden directory)

**Configuration precedence:**
1. CLI argument: `--threads-dir <path>`
2. Environment variable: `WATERCOOLER_DIR`
3. Default: `.watercooler`

**Examples:**

```bash
# Use default
watercooler list

# Override with CLI
watercooler list --threads-dir ./my-threads

# Override with environment variable
export WATERCOOLER_DIR=./my-threads
watercooler list
```

**Python usage:**

```python
from pathlib import Path
from watercooler.config import resolve_threads_dir

# Get configured threads directory
threads_dir = resolve_threads_dir()  # Uses env var or default

# Override in code
threads_dir = resolve_threads_dir(cli_value="./my-threads")
```

---

### Templates Directory

Templates customize thread and entry formatting.

**Default:** Package bundled templates

**Configuration precedence:**
1. CLI argument: `--templates-dir <path>`
2. Environment variable: `WATERCOOLER_TEMPLATES`
3. Project-local: `./.watercooler/templates/` (if exists)
4. Package bundled templates (fallback)

**Template files:**
- `_TEMPLATE_topic_thread.md` - Thread initialization template
- `_TEMPLATE_entry_block.md` - Entry format template

**Example - Project-local templates:**

```bash
# Create project-local templates
mkdir -p .watercooler/templates
cp $(python3 -c "from pathlib import Path; import watercooler; print(Path(watercooler.__file__).parent / 'templates')") .watercooler/templates/_TEMPLATE_topic_thread.md

# Edit template
vim .watercooler/templates/_TEMPLATE_topic_thread.md

# Will be used automatically
watercooler init-thread new-topic
```

See [Templates Guide](TEMPLATES.md) for complete customization reference.

---

### Environment Variables

Watercooler supports multiple environment variables for configuration. For complete documentation, see **[ENVIRONMENT_VARS.md](./ENVIRONMENT_VARS.md)**.

#### Key Variables

**Core Configuration:**
- `WATERCOOLER_AGENT` - Agent identity (required for MCP, optional for CLI)
- `WATERCOOLER_DIR` - Threads directory with upward search (default: `.watercooler`)
- `WATERCOOLER_TEMPLATES` - Custom templates directory

**Cloud Sync (Optional):**
- `WATERCOOLER_GIT_REPO` - Git repository URL (enables cloud mode)
- `WATERCOOLER_GIT_SSH_KEY` - SSH private key path
- `WATERCOOLER_GIT_AUTHOR` - Git commit author name
- `WATERCOOLER_GIT_EMAIL` - Git commit author email

**Advanced:**
- `WATERCOOLER_USER` - Username override for lock files (low-level, rarely needed)

**Locking Configuration:**
- `WCOOLER_LOCK_TTL` - Lock time-to-live in seconds (default: 30)
- `WCOOLER_LOCK_POLL` - Lock polling interval in seconds (default: 0.1)

**Example `.env` file:**

```bash
# MCP configuration
WATERCOOLER_AGENT=Claude
WATERCOOLER_DIR=/absolute/path/to/.watercooler

# Optional: Cloud sync
WATERCOOLER_GIT_REPO=git@github.com:org/watercooler-threads.git
WATERCOOLER_GIT_SSH_KEY=/path/to/deploy/key
WATERCOOLER_GIT_AUTHOR="Agent Name"
WATERCOOLER_GIT_EMAIL=agent@example.com

# Optional: Custom templates
WATERCOOLER_TEMPLATES=./templates/watercooler

# Optional: Lock tuning
WCOOLER_LOCK_TTL=60
WCOOLER_LOCK_POLL=0.2
```

See **[ENVIRONMENT_VARS.md](./ENVIRONMENT_VARS.md)** for detailed documentation and troubleshooting.

---

## Template Customization

### Quick Template Override

Copy bundled templates and customize:

```bash
# Find bundled templates
python3 -c "from pathlib import Path; import watercooler; print(Path(watercooler.__file__).parent / 'templates')"

# Copy to project
mkdir -p .watercooler/templates
cp <bundled-path>/_TEMPLATE_topic_thread.md .watercooler/templates/
cp <bundled-path>/_TEMPLATE_entry_block.md .watercooler/templates/

# Customize
vim .watercooler/templates/_TEMPLATE_topic_thread.md
```

### Thread Template

`.watercooler/templates/_TEMPLATE_topic_thread.md`:

```markdown
Title: {{Short title}}
Status: {{STATUS}}
Ball: {{BALL}}
Updated: {{UTC}}
Owner: {{OWNER}}
Participants: {{PARTICIPANTS}}

# {{Short title}}

Initial body here...
```

**Placeholders:**
- `{{TOPIC}}` or `<TOPIC>` - Thread topic
- `{{Short title}}` - Human-readable title
- `{{STATUS}}` - Initial status
- `{{BALL}}` - Initial ball owner
- `{{UTC}}` or `{{NOWUTC}}` - Current timestamp
- `{{OWNER}}` - Thread owner
- `{{PARTICIPANTS}}` - Comma-separated participant list

### Entry Template

`.watercooler/templates/_TEMPLATE_entry_block.md`:

```markdown
---
Entry: {{AGENT}} {{UTC}}
Role: {{ROLE}}
Type: {{TYPE}}
Title: {{TITLE}}

{{BODY}}
```

**Placeholders:**
- `{{AGENT}}` - Agent name with user tag (e.g., "Claude (agent)")
- `{{UTC}}` - Entry timestamp
- `{{ROLE}}` - Agent role (planner, critic, implementer, tester, pm, scribe)
- `{{TYPE}}` - Entry type (Note, Plan, Decision, PR, Closure)
- `{{TITLE}}` - Entry title
- `{{BODY}}` - Entry body text

See [Templates Guide](TEMPLATES.md) for advanced customization.

---

## Agent Registry

Configure agent behavior with a JSON registry.

### Default Agents

Built-in agents with counterpart mappings:
- **Codex** ↔ **Claude** (default pair)
- **Team** (neutral, no auto-flip)

### Custom Agent Registry

Create `agents.json`:

```json
{
  "canonical": {
    "gpt": "GPT",
    "claude": "Claude",
    "codex": "Codex",
    "team": "Team"
  },
  "counterpart": {
    "GPT": "Claude",
    "Claude": "Codex",
    "Codex": "Claude"
  },
  "default_agent": "Team",
  "default_role": "pm",
  "default_ball": "Team"
}
```

**Usage:**

```bash
watercooler say feature-auth \
  --agents-file ./agents.json \
  --agent gpt \
  --title "Review" \
  --body "Looks good"
```

See [Agent Registry Guide](AGENT_REGISTRY.md) for complete reference.

---

## Git Configuration

For multi-user collaboration, configure git merge strategies.

### Required: Enable "ours" Merge Driver

```bash
git config merge.ours.driver true
```

### Recommended: Pre-commit Hook

```bash
# Enable project hooks
git config core.hooksPath .githooks
```

### Create `.gitattributes`

```
.watercooler/*.md merge=ours
```

This ensures append-only semantics - last writer wins.

See [Git Setup Guide](../.github/WATERCOOLER_SETUP.md) for detailed configuration.

---

## Cloud Sync for Team Collaboration

Watercooler supports **git-based cloud sync** for distributed team collaboration. When enabled, the MCP server automatically pulls before reads and commits+pushes after writes.

### Quick Setup

1. **Create a git repository for threads:**
   ```bash
   # Option A: Dedicated repo (recommended)
   git init watercooler-threads
   cd watercooler-threads
   git remote add origin git@github.com:org/watercooler-threads.git

   # Option B: Use existing project repo
   # (threads will be in .watercooler/ subdirectory)
   ```

2. **Configure environment variables:**
   ```bash
   export WATERCOOLER_GIT_REPO=git@github.com:org/watercooler-threads.git
   export WATERCOOLER_GIT_SSH_KEY=/path/to/deploy/key
   export WATERCOOLER_GIT_AUTHOR="Agent Name"
   export WATERCOOLER_GIT_EMAIL=agent@example.com
   ```

3. **Restart your MCP client** (Claude Code, Claude Desktop, etc.)

### How It Works

**Local Mode (default):**
- Reads/writes directly to local `.watercooler/` directory
- No network operations
- Fast and simple

**Cloud Mode (when `WATERCOOLER_GIT_REPO` is set):**
- **Reads**: `git pull` before returning thread content
- **Writes**: Append entry, `git commit`, `git push`
- **Conflicts**: Automatic retry with fresh pull (3 attempts)
- **Latency**: ~500ms-1s per operation

### Documentation

> **Note**: Cloud sync features have been mothballed in favor of local-first architecture. See [LOCAL_QUICKSTART.md](./LOCAL_QUICKSTART.md) for current setup.

- **[Cloud Sync Guide](../.mothballed/docs/CLOUD_SYNC_GUIDE.md)** - 5-minute setup walkthrough (archived)
- **[Cloud Sync Strategy](../.mothballed/docs/CLOUD_SYNC_STRATEGY.md)** - Decision rationale and trade-offs (archived)
- **[Cloud Sync Architecture](../.mothballed/docs/CLOUD_SYNC_ARCHITECTURE.md)** - Technical implementation details (archived)

---

## Integration Patterns

### Pattern 1: Automation Script

```python
#!/usr/bin/env python3
"""Automated thread status updater."""
from pathlib import Path
from watercooler.commands import set_status
from watercooler.metadata import thread_meta, is_closed

threads_dir = Path(".watercooler")

# Find all open threads
for thread_file in threads_dir.glob("*.md"):
    title, status, ball, updated = thread_meta(thread_file)

    if not is_closed(status):
        # Check some condition
        if should_close_thread(title):
            topic = thread_file.stem
            set_status(topic, threads_dir=threads_dir, status="closed")
            print(f"Closed: {title}")

def should_close_thread(title: str) -> bool:
    # Your logic here
    return "deprecated" in title.lower()
```

### Pattern 2: CI/CD Integration

```yaml
# .github/workflows/watercooler.yml
name: Watercooler Index
on:
  push:
    paths:
      - '.watercooler/*.md'

jobs:
  update-index:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install watercooler
        run: pip install git+https://github.com/mostlyharmless-ai/watercooler-collab.git
      - name: Generate index
        run: |
          watercooler reindex
          watercooler web-export
      - name: Commit updates
        run: |
          git config user.name "Bot"
          git config user.email "bot@example.com"
          git add .watercooler/index.{md,html}
          git commit -m "chore: update watercooler index" || true
          git push
```

### Pattern 3: Pre-commit Hook

`.githooks/pre-commit`:

```bash
#!/bin/bash
# Validate watercooler threads before commit

set -e

echo "Validating watercooler threads..."

# Check for merge conflicts in threads
if git diff --cached .watercooler/*.md | grep -q '<<<<<<<'; then
    echo "Error: Merge conflict markers found in threads"
    exit 1
fi

# Regenerate index
watercooler reindex --threads-dir .watercooler

# Stage index if changed
git add .watercooler/index.md

echo "✓ Watercooler validation passed"
```

Make executable:

```bash
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
```

### Pattern 4: Wrapper Script

`tools/wc-say`:

```bash
#!/bin/bash
# Convenience wrapper for common watercooler operations

set -e

THREADS_DIR="${WATERCOOLER_DIR:-.watercooler}"

if [ -z "$1" ]; then
    echo "Usage: wc-say <topic> <message>"
    exit 1
fi

TOPIC="$1"
shift
MESSAGE="$*"

watercooler say "$TOPIC" \
    --threads-dir "$THREADS_DIR" \
    --agent Team \
    --role pm \
    --title "Quick Note" \
    --body "$MESSAGE"

echo "✓ Added note to $TOPIC"
```

Usage:

```bash
./tools/wc-say feature-auth "Deployment complete"
```

---

## Troubleshooting

### Issue: Command not found

```bash
watercooler: command not found
```

**Solution:**
- Ensure installation completed: `pip install -e .`
- Check PATH includes pip bin directory: `python3 -m site --user-base`
- Try: `python3 -m watercooler.cli --help`

### Issue: Lock timeout

```
AdvisoryLock timeout after 5 seconds
```

**Solutions:**
- Increase timeout: `WCOOLER_LOCK_TTL=60 watercooler say ...`
- Remove stuck lock: `watercooler unlock <topic>`
- Check for hung processes: `ps aux | grep watercooler`

### Issue: Template not found

```
FileNotFoundError: Template '_TEMPLATE_topic_thread.md' not found
```

**Solutions:**
- Check template location: `ls .watercooler/templates/`
- Verify `WATERCOOLER_TEMPLATES` if set
- Reset to bundled: `unset WATERCOOLER_TEMPLATES`

### Issue: Permission denied

```
PermissionError: [Errno 13] Permission denied: '.watercooler/thread.md'
```

**Solutions:**
- Check file permissions: `ls -la .watercooler/`
- Ensure directory is writable: `chmod u+w .watercooler/`
- Check lock file isn't orphaned: `watercooler unlock <topic>`

### Issue: Git merge conflicts

```
CONFLICT (content): Merge conflict in .watercooler/thread.md
```

**Solutions:**
- Configure merge driver: `git config merge.ours.driver true`
- Create `.gitattributes`: `.watercooler/*.md merge=ours`
- See [Git Setup Guide](../.github/WATERCOOLER_SETUP.md)

---

## See Also

### Getting Started
- [Quickstart Guide](./QUICKSTART.md) - 5-minute setup for MCP server
- [Claude Code Setup](./CLAUDE_CODE_SETUP.md) - Configure Claude Code
- [Claude Desktop Setup](./CLAUDE_DESKTOP_SETUP.md) - Configure Claude Desktop

### Configuration
- [Environment Variables](./ENVIRONMENT_VARS.md) - Complete configuration reference
- [Agent Registry](AGENT_REGISTRY.md) - Agent configuration guide
- [Templates Guide](TEMPLATES.md) - Template customization reference

### Cloud Sync (Archived)
- [Cloud Sync Guide](../.mothballed/docs/CLOUD_SYNC_GUIDE.md) - User-facing setup walkthrough (archived)
- [Cloud Sync Strategy](../.mothballed/docs/CLOUD_SYNC_STRATEGY.md) - Decision rationale (archived)
- [Cloud Sync Architecture](../.mothballed/docs/CLOUD_SYNC_ARCHITECTURE.md) - Technical details (archived)

### Reference
- [MCP Server Guide](./mcp-server.md) - MCP tool documentation
- [API Reference](api.md) - Python API documentation
- [Troubleshooting](./TROUBLESHOOTING.md) - Common issues and solutions
- [Roadmap](../ROADMAP.md) - Project status and future plans

### Community
- [Use Cases Guide](USE_CASES.md) - Real-world examples
- [FAQ](FAQ.md) - Frequently asked questions
- [GitHub Repository](https://github.com/mostlyharmless-ai/watercooler-collab)
