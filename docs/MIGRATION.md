# Migration Guide

This guide helps you migrate from acpmonkey's `watercooler.py` to the standalone `watercooler-collab` library.

## Overview

Watercooler-collab provides **full CLI parity** with acpmonkey's watercooler.py implementation. All commands, flags, and behaviors work identically.

**Key Compatibility**:
- ✅ Thread file format is byte-for-byte compatible
- ✅ All CLI commands work identically
- ✅ Template format matches exactly
- ✅ Agent registry structure is the same
- ✅ Existing threads can be used without modification

**Directory Convention Change**:
- acpmonkey default: `./watercooler/`
- watercooler-collab default: `./.watercooler/` (hidden directory)
- Use `--threads-dir` to specify custom locations

## Quick Migration

### 1. Install watercooler-collab

```bash
pip install watercooler-collab
```

Or for development:

```bash
git clone https://github.com/mostlyharmless-ai/watercooler-collab.git
cd watercooler-collab
pip install -e .
```

### 2. Move Existing Threads (Optional)

If you have existing threads in `./watercooler/`, you can either:

**Option A**: Move to `.watercooler` (recommended):
```bash
mv watercooler .watercooler
```

**Option B**: Keep using `./watercooler` by specifying `--threads-dir`:
```bash
# Set environment variable
export WATERCOOLER_DIR=./watercooler

# Or use --threads-dir flag
watercooler say topic --threads-dir ./watercooler --title "Update" --body "Done"
```

### 3. Replace Commands

**Before** (acpmonkey):
```bash
python -m acpmonkey.watercooler say topic --threads-dir ./watercooler --title "Update" --body "Done"
```

**After** (watercooler-collab):
```bash
# Uses .watercooler by default
watercooler say topic --title "Update" --body "Done"

# Or specify directory explicitly
watercooler say topic --threads-dir ./watercooler --title "Update" --body "Done"
```

All your existing threads, templates, and agent registries work as-is.

## Command Mapping

All commands have identical names and behavior:

| acpmonkey | watercooler-collab | Notes |
|-----------|-------------------|-------|
| `python -m acpmonkey.watercooler init-thread` | `watercooler init-thread` | Identical |
| `python -m acpmonkey.watercooler append-entry` | `watercooler append-entry` | Identical |
| `python -m acpmonkey.watercooler say` | `watercooler say` | Identical |
| `python -m acpmonkey.watercooler ack` | `watercooler ack` | Identical |
| `python -m acpmonkey.watercooler handoff` | `watercooler handoff` | Identical |
| `python -m acpmonkey.watercooler set-status` | `watercooler set-status` | Identical |
| `python -m acpmonkey.watercooler set-ball` | `watercooler set-ball` | Identical |
| `python -m acpmonkey.watercooler list` | `watercooler list` | Identical |
| `python -m acpmonkey.watercooler reindex` | `watercooler reindex` | Identical |
| `python -m acpmonkey.watercooler search` | `watercooler search` | Identical |
| `python -m acpmonkey.watercooler web-export` | `watercooler web-export` | Identical |

## File Compatibility

### Thread Files

Thread files are fully compatible. No conversion needed.

**Example thread** (works with both):
```markdown
Title: feature-auth
Status: open
Ball: codex
Updated: 2025-10-06T12:34:56Z

# feature-auth

---
Entry: Codex (jay) 2025-10-06T12:34:56Z
Type: Note
Title: Implementation Started

Working on JWT authentication.
```

### Templates

Template format is identical:

**Thread template** (`_TEMPLATE_topic_thread.md`):
```markdown
# {{TOPIC}} — Thread
Status: {{STATUS}}
Ball: {{BALL}}
Topic: {{TOPIC}}
Created: {{UTC}}
```

**Entry template** (`_TEMPLATE_entry_block.md`):
```markdown
---
Entry: {{AGENT}} {{UTC}}
Type: {{TYPE}}
Title: {{TITLE}}

{{BODY}}
```

### Agent Registry

Registry JSON format is identical:

```json
{
  "canonical": {
    "claude": "Claude",
    "codex": "Codex",
    "team": "Team"
  },
  "counterpart": {
    "Codex": "Claude",
    "Claude": "Codex",
    "Team": "Claude"
  },
  "default_ball": "Team"
}
```

## Import Changes

### Python API

If you were importing watercooler functions directly:

**Before** (acpmonkey):
```python
from acpmonkey.watercooler import say, ack, handoff, init_thread
```

**After** (watercooler-collab):
```python
from watercooler.commands import say, ack, handoff, init_thread
```

### Module Structure

The package is organized differently but provides the same functionality:

| acpmonkey | watercooler-collab |
|-----------|-------------------|
| `acpmonkey.watercooler` (monolithic) | `watercooler.commands` |
| N/A | `watercooler.agents` |
| N/A | `watercooler.templates` |
| N/A | `watercooler.config` |
| N/A | `watercooler.fs` |
| N/A | `watercooler.lock` |
| N/A | `watercooler.header` |
| N/A | `watercooler.metadata` |

The modular structure makes it easier to import specific functionality:

```python
# Agent handling
from watercooler.agents import _canonical_agent, _counterpart_of

# Template operations
from watercooler.templates import _fill_template

# File operations
from watercooler.fs import read_body, thread_path

# Locking
from watercooler.lock import AdvisoryLock
```

## Breaking Changes from Early watercooler-collab

**Note**: If you used watercooler-collab **before Phase 1** (commit 7102608), there are breaking changes:

### 1. Agent Format

**Old**: `codex#dev`
**New**: `Codex (jay)`

### 2. Entry Format

**Old** (simple):
```markdown
---
- Updated: 2025-10-06T12:34:56Z

Simple body text.
```

**New** (structured):
```markdown
---
Entry: Codex (jay) 2025-10-06T12:34:56Z
Role: implementer
Type: Note
Title: Implementation Complete

Detailed body text.
```

### 3. CLI Arguments

**append-entry**:
- Now requires: `--agent`, `--role`, `--title`
- Optional: `--type`, `--body`, `--status`, `--ball`

**say**:
- Now requires: `--title`
- Optional: `--agent`, `--role`, `--type`, `--body`

**ack**:
- `--note` renamed to `--body`

**handoff**:
- `--author` renamed to `--agent`

### 4. Migration Script (Pre-Phase 1 → Current)

If you have threads from pre-Phase 1 watercooler-collab:

```python
#!/usr/bin/env python3
"""Migrate old format to new structured entries."""

import re
from pathlib import Path

def migrate_thread(path: Path):
    """Convert old format entries to structured format."""
    content = path.read_text(encoding='utf-8')

    # Convert old entries to new format
    pattern = r'^- Updated: ([^\n]+?)(?:\s+by\s+([^\n]+?))?\n\n(.+?)(?=\n---|\Z)'

    def replace_entry(match):
        timestamp = match.group(1)
        author = match.group(2) or "Team (user)"
        body = match.group(3).strip()

        return f"""---
Entry: {author} {timestamp}
Type: Note
Title: Update

{body}"""

    new_content = re.sub(pattern, replace_entry, content, flags=re.DOTALL | re.MULTILINE)
    path.write_text(new_content, encoding='utf-8')
    print(f"Migrated: {path}")

# Migrate all threads
for thread in Path("watercooler").glob("*.md"):
    if thread.name != "index.md":
        migrate_thread(thread)
```

## Environment Variables

Both implementations support similar environment variables:

```bash
# Templates directory (both support)
export WATERCOOLER_TEMPLATES=/path/to/templates

# Threads directory
# acpmonkey: May have WATERCOOLER_DIR support
# watercooler-collab: WATERCOOLER_DIR overrides .watercooler default
export WATERCOOLER_DIR=./watercooler  # Optional, defaults to .watercooler
```

## Configuration Files

**watercooler-collab convention** (recommended):

```
project/
└── .watercooler/          # Hidden directory (default)
    ├── templates/         # Optional custom templates
    │   ├── _TEMPLATE_topic_thread.md
    │   └── _TEMPLATE_entry_block.md
    ├── agents.json        # Optional agent registry
    ├── topic1.md          # Thread files
    ├── topic2.md
    └── index.md
```

**acpmonkey convention** (still supported):

```
project/
├── .watercooler/          # Optional templates/config
│   ├── templates/
│   │   ├── _TEMPLATE_topic_thread.md
│   │   └── _TEMPLATE_entry_block.md
│   └── agents.json
└── watercooler/           # Threads directory (use --threads-dir)
    ├── topic1.md
    ├── topic2.md
    └── index.md
```

## Testing Migration

### 1. Verify Thread Compatibility

```bash
# List threads with both tools (using same directory)
python -m acpmonkey.watercooler list --threads-dir ./watercooler
watercooler list --threads-dir ./watercooler

# Compare output - should be identical
```

### 2. Test Commands

```bash
# Option A: Using new .watercooler default
watercooler init-thread test-migration
watercooler say test-migration --title "Test" --body "Migration test"
cat .watercooler/test-migration.md

# Option B: Using old watercooler directory
watercooler init-thread test-migration --threads-dir ./watercooler
watercooler say test-migration --threads-dir ./watercooler --title "Test" --body "Migration test"
cat watercooler/test-migration.md
```

### 3. Verify Templates

```bash
# Templates now default to .watercooler/templates/
mkdir -p .watercooler/templates
watercooler init-thread test-template

# Check result
cat .watercooler/test-template.md
```

## Side-by-Side Comparison

You can run both implementations side-by-side during migration:

```bash
# acpmonkey
python -m acpmonkey.watercooler say topic --title "From acpmonkey" --body "Using old tool"

# watercooler-collab
watercooler say topic --title "From watercooler-collab" --body "Using new tool"

# Both append to same thread - fully compatible
```

## Shell Aliases

Update your shell aliases:

**Before**:
```bash
alias wc='python -m acpmonkey.watercooler'
alias wc-say='python -m acpmonkey.watercooler say'
```

**After**:
```bash
alias wc='watercooler'
alias wc-say='watercooler say'
```

Or create migration aliases:

```bash
# Temporary aliases during migration
alias wc-old='python -m acpmonkey.watercooler'
alias wc-new='watercooler'
```

## CI/CD Integration

### GitHub Actions

**Before**:
```yaml
- name: Update thread
  run: |
    python -m pip install acpmonkey
    python -m acpmonkey.watercooler say build-status \
      --threads-dir ./watercooler \
      --title "Build Complete" \
      --body "All tests passed"
```

**After**:
```yaml
- name: Update thread
  run: |
    python -m pip install watercooler-collab
    watercooler say build-status \
      --threads-dir ./watercooler \
      --title "Build Complete" \
      --body "All tests passed"
```

### Scripts

**Before**:
```bash
#!/bin/bash
python -m acpmonkey.watercooler "$@"
```

**After**:
```bash
#!/bin/bash
watercooler "$@"
```

## Common Issues

### Issue: Command not found

**Problem**: `watercooler: command not found`

**Solution**: Ensure watercooler-collab is installed:
```bash
pip install watercooler-collab
# or
pip install -e /path/to/watercooler-collab
```

### Issue: Import errors

**Problem**: `ModuleNotFoundError: No module named 'watercooler'`

**Solution**: Update imports:
```python
# Wrong
from acpmonkey.watercooler import say

# Correct
from watercooler.commands import say
```

### Issue: Template not found

**Problem**: Templates not being discovered

**Solution**: Check template locations:
```bash
# Verify template exists
ls .watercooler/templates/_TEMPLATE_*.md

# Or set environment variable
export WATERCOOLER_TEMPLATES=/path/to/templates
```

### Issue: Agent registry not working

**Problem**: Agents not being canonicalized

**Solution**: Ensure registry is passed to commands:
```bash
watercooler say topic \
  --agents-file .watercooler/agents.json \
  --agent codex \
  --title "Update" \
  --body "Done"
```

## Rollback Plan

If you need to rollback:

1. Keep acpmonkey installed alongside watercooler-collab
2. All thread files work with both tools
3. Switch back to acpmonkey commands as needed

```bash
# Rollback example
python -m acpmonkey.watercooler say topic --title "Rolled back" --body "Using acpmonkey again"
```

## Benefits of Migration

### 1. Standalone Package

No need for full acpmonkey installation:

```bash
# Before: Install entire acpmonkey
pip install acpmonkey

# After: Install only watercooler
pip install watercooler-collab
```

### 2. Modular Architecture

Import only what you need:

```python
# Just need agent functions
from watercooler.agents import _canonical_agent

# Just need templates
from watercooler.templates import _fill_template
```

### 3. Better Discoverability

Dedicated command: `watercooler` vs `python -m acpmonkey.watercooler`

### 4. Comprehensive Tests

52 tests covering all features vs 25 in acpmonkey.

### 5. Better Documentation

Dedicated guides:
- [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md)
- [TEMPLATES.md](TEMPLATES.md)
- [AGENT_REGISTRY.md](AGENT_REGISTRY.md)

## Migration Checklist

- [ ] Install watercooler-collab
- [ ] Decide on directory structure:
  - [ ] Move `watercooler/` to `.watercooler/` (recommended), OR
  - [ ] Set `WATERCOOLER_DIR=./watercooler` to keep existing location
- [ ] Test commands with existing threads
- [ ] Update shell aliases
- [ ] Update scripts and automation
- [ ] Update CI/CD pipelines
- [ ] Update documentation references
- [ ] Update Python imports (if using API)
- [ ] Test template discovery (now checks `.watercooler/templates/`)
- [ ] Test agent registry
- [ ] Verify thread compatibility
- [ ] Update team documentation

## Support

If you encounter issues during migration:

1. Check existing threads are compatible: `watercooler list --threads-dir ./watercooler`
2. Verify commands work: `watercooler --help`
3. Test with new thread: `watercooler init-thread test-new --threads-dir ./watercooler`
4. Review this guide for common issues
5. Open issue: https://github.com/mostlyharmless-ai/watercooler-collab/issues

## See Also

- [README.md](../README.md) - Installation and usage
- [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md) - Entry format guide
- [TEMPLATES.md](TEMPLATES.md) - Template customization
- [AGENT_REGISTRY.md](AGENT_REGISTRY.md) - Agent configuration
- [STATUS.md](../STATUS.md) - Project status and history
