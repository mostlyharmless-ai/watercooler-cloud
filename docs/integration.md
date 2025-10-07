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

Watercooler-collab can be used two ways:
1. **CLI** - Command-line tool for interactive use
2. **Python Library** - Programmatic API for automation

### CLI Usage

#### Initialize a Thread

```bash
watercooler init-thread feature-auth \
  --owner Jay \
  --participants "Jay, Claude, Codex" \
  --ball codex
```

This creates `.watercooler/feature-auth.md`:

```markdown
Title: Feature auth
Status: open
Ball: codex
Updated: 2025-10-07T10:00:00Z
Owner: Jay
Participants: Jay, Claude, Codex

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

#### General Configuration

- `WATERCOOLER_DIR` - Default threads directory (default: `.watercooler`)
- `WATERCOOLER_TEMPLATES` - Templates directory override
- `WATERCOOLER_USER` - Override user name for agent tagging

#### Locking Configuration

- `WCOOLER_LOCK_TTL` - Lock time-to-live in seconds (default: 30)
- `WCOOLER_LOCK_POLL` - Lock polling interval in seconds (default: 0.1)

**Example `.env` file:**

```bash
# Threads configuration
WATERCOOLER_DIR=./collaboration
WATERCOOLER_TEMPLATES=./templates/watercooler

# User identity
WATERCOOLER_USER=jay

# Lock tuning
WCOOLER_LOCK_TTL=60
WCOOLER_LOCK_POLL=0.2
```

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
- `{{AGENT}}` - Agent name with user tag (e.g., "Claude (jay)")
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

- [API Reference](api.md) - Complete Python API documentation
- [Use Cases Guide](USE_CASES.md) - Real-world integration examples
- [Templates Guide](TEMPLATES.md) - Template customization reference
- [Agent Registry](AGENT_REGISTRY.md) - Agent configuration guide
- [Migration Guide](MIGRATION.md) - Migrating from acpmonkey
- [FAQ](FAQ.md) - Frequently asked questions
- [GitHub Repository](https://github.com/mostlyharmless-ai/watercooler-collab)
