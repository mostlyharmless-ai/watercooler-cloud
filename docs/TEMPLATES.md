# Templates Guide

Watercooler-collab uses customizable templates for thread initialization and entry formatting. This guide covers template syntax, customization, and discovery.

## Table of Contents

- [Overview](#overview)
- [Template Discovery](#template-discovery)
- [Placeholder Syntax](#placeholder-syntax)
- [Thread Templates](#thread-templates)
- [Entry Templates](#entry-templates)
- [Template Special Cases](#template-special-cases)
- [Complete Customization Example](#complete-customization-example)
- [Template Variables in Detail](#template-variables-in-detail)
- [Environment-Specific Templates](#environment-specific-templates)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)
- [Advanced Examples](#advanced-examples)
- [See Also](#see-also)

## Overview

Two types of templates:
- **Thread templates**: Used by `init-thread` to create new threads
- **Entry templates**: Used by `append-entry`, `say`, `ack`, `handoff` to format entries

## Template Discovery

Templates are discovered in this order (highest precedence first):

1. **CLI argument**: `--templates-dir /path/to/templates`
2. **Environment variable**: `WATERCOOLER_TEMPLATES=/path/to/templates`
3. **Project-local**: `./.watercooler/templates/`
4. **Bundled**: Built-in templates from the package

This allows per-command overrides, per-project customization, or global defaults.

### Example: CLI Override

```bash
watercooler init-thread topic --templates-dir /custom/templates
```

### Example: Environment Variable

```bash
export WATERCOOLER_TEMPLATES=/home/user/my-templates
watercooler init-thread topic
watercooler say topic --title "Note" --body "Using custom templates"
```

### Example: Project-Local

```bash
# Create local templates directory
mkdir -p .watercooler/templates

# Copy bundled templates as starting point
cp $(python3 -c "import watercooler; import os; print(os.path.dirname(watercooler.__file__))")/templates/_TEMPLATE_*.md .watercooler/templates/

# Edit templates as needed
# vim .watercooler/templates/_TEMPLATE_topic_thread.md

# Commands will now use your custom templates automatically
watercooler init-thread topic  # Uses .watercooler/templates/
```

## Placeholder Syntax

Templates support two placeholder formats:

### 1. Double-Brace: `{{KEY}}`
Standard placeholder format.

```markdown
Title: {{TOPIC}}
Created: {{UTC}}
```

### 2. Angle-Bracket: `<KEY>`
Alternative format for compatibility.

```markdown
Title: <TOPIC>
Created: <UTC>
```

Both formats are equivalent and can be mixed in the same template.

## Thread Templates

### File Name
`_TEMPLATE_topic_thread.md`

### Available Placeholders

| Placeholder | Description | Example |
|------------|-------------|---------|
| `{{TOPIC}}` | Thread topic identifier | `feature-auth` |
| `{{Short title}}` | Human-readable title | `Feature Auth` |
| `{{OWNER}}` | Thread owner | `Jay` |
| `{{PARTICIPANTS}}` | Comma-separated participants | `Jay, Claude, Codex` |
| `{{STATUS}}` | Initial status | `OPEN` |
| `{{BALL}}` | Initial ball owner | `codex` |
| `{{UTC}}` or `{{NOWUTC}}` | Current UTC timestamp | `2025-10-06T12:34:56Z` |

### Bundled Template

The built-in thread template:

```markdown
# {{TOPIC}} — Thread
Status: {{STATUS}}
Ball: {{BALL}}
Topic: {{TOPIC}}
Created: {{UTC}}
```

### Custom Thread Template Example

Create `.watercooler/templates/_TEMPLATE_topic_thread.md`:

```markdown
---
title: {{Short title}}
status: {{STATUS}}
ball: {{BALL}}
owner: {{OWNER}}
participants: {{PARTICIPANTS}}
created: {{UTC}}
---

# {{Short title}}

**Owner**: {{OWNER}}
**Participants**: {{PARTICIPANTS}}
**Status**: {{STATUS}}
**Ball**: {{BALL}}

## Context

<!-- Add project context here -->

## Timeline

- Created: {{UTC}}

## Entries
```

Usage:

```bash
watercooler init-thread feature-auth \
  --owner Jay \
  --participants "Jay, Claude, Codex" \
  --ball codex
```

Results in:

```markdown
---
title: Feature Auth
status: OPEN
ball: codex
owner: Jay
participants: Jay, Claude, Codex
created: 2025-10-06T12:34:56Z
---

# Feature Auth

**Owner**: Jay
**Participants**: Jay, Claude, Codex
**Status**: OPEN
**Ball**: codex

## Context

<!-- Add project context here -->

## Timeline

- Created: 2025-10-06T12:34:56Z

## Entries
```

## Entry Templates

### File Name
`_TEMPLATE_entry_block.md`

### Available Placeholders

| Placeholder | Description | Example |
|------------|-------------|---------|
| `{{AGENT}}` | Canonical agent name with user tag | `Claude (jay)` |
| `{{ROLE}}` | Agent role | `critic` |
| `{{TYPE}}` | Entry type | `Decision` |
| `{{TITLE}}` | Entry title | `Review Complete` |
| `{{UTC}}` | Current UTC timestamp | `2025-10-06T12:34:56Z` |
| `{{BODY}}` | Entry body content | `Implementation approved` |

### Bundled Template

The built-in entry template:

```markdown
---
Entry: {{AGENT}} {{UTC}}
Type: {{TYPE}}
Title: {{TITLE}}

{{BODY}}
```

### Custom Entry Template Examples

#### Minimal Format

Create `.watercooler/templates/_TEMPLATE_entry_block.md`:

```markdown
---
[{{UTC}}] {{AGENT}} ({{ROLE}}): {{TITLE}}

{{BODY}}
```

Results in:

```markdown
---
[2025-10-06T12:34:56Z] Claude (jay) (critic): Review Complete

All edge cases covered. Approved for merge.
```

#### Detailed Format

```markdown
---
**Entry**: {{TITLE}}
**Agent**: {{AGENT}}
**Role**: {{ROLE}}
**Type**: {{TYPE}}
**Timestamp**: {{UTC}}

---

{{BODY}}

---
```

Results in:

```markdown
---
**Entry**: Security Review Complete
**Agent**: Claude (jay)
**Role**: critic
**Type**: Decision
**Timestamp**: 2025-10-06T12:34:56Z

---

Authentication approach approved. All security requirements met.

---
```

#### Issue Tracker Style

```markdown
---
## {{TITLE}}

**Type**: {{TYPE}}
**Author**: {{AGENT}}
**Role**: {{ROLE}}
**Date**: {{UTC}}

### Description

{{BODY}}

---
```

## Template Special Cases

### BODY Placeholder Handling

If your template does NOT include `{{BODY}}` or `<BODY>`, the body content is automatically appended after the template.

Template without BODY:

```markdown
---
Entry: {{AGENT}} {{UTC}}
Title: {{TITLE}}
```

With `--body "Implementation complete"`:

```markdown
---
Entry: Claude (jay) 2025-10-06T12:34:56Z
Title: Implementation Complete

Implementation complete
```

### Empty Template

If template file exists but is empty or contains only whitespace, watercooler-collab falls back to built-in default templates.

## Complete Customization Example

### Project Setup

```bash
# Create project-local templates
mkdir -p .watercooler/templates
```

### Thread Template

`.watercooler/templates/_TEMPLATE_topic_thread.md`:

```markdown
# {{Short title}}

| Field | Value |
|-------|-------|
| Topic | {{TOPIC}} |
| Owner | {{OWNER}} |
| Status | {{STATUS}} |
| Ball | {{BALL}} |
| Created | {{UTC}} |

## Participants
{{PARTICIPANTS}}

## Thread History
```

### Entry Template

`.watercooler/templates/_TEMPLATE_entry_block.md`:

```markdown

---

### {{TITLE}}

> {{TYPE}} by {{AGENT}} as {{ROLE}} — {{UTC}}

{{BODY}}
```

### Usage

```bash
# Initialize thread with custom template
watercooler init-thread feature-auth \
  --owner Jay \
  --participants "Jay, Claude, Codex"

# Add entry with custom template
watercooler say feature-auth \
  --agent Claude \
  --role planner \
  --title "Architecture Proposal" \
  --type Plan \
  --body "JWT-based auth with Redis session store"
```

### Result

Thread file `watercooler/feature-auth.md`:

```markdown
# Feature Auth

| Field | Value |
|-------|-------|
| Topic | feature-auth |
| Owner | Jay |
| Status | OPEN |
| Ball | codex |
| Created | 2025-10-06T12:00:00Z |

## Participants
Jay, Claude, Codex

## Thread History

---

### Architecture Proposal

> Plan by Claude (jay) as planner — 2025-10-06T12:05:30Z

JWT-based auth with Redis session store
```

## Template Variables in Detail

### Agent Canonicalization

The `{{AGENT}}` placeholder receives canonicalized agent names:

Input: `--agent codex`
Output: `Codex (jay)`

Input: `--agent Claude`
Output: `Claude (jay)`

See [AGENT_REGISTRY.md](AGENT_REGISTRY.md) for custom agent mappings.

### Status Formatting

The `{{STATUS}}` placeholder is automatically uppercased:

Input: `--status open`
Output: `OPEN`

Input: `--status in-review`
Output: `IN-REVIEW`

### Timestamp Format

`{{UTC}}` and `{{NOWUTC}}` produce ISO 8601 timestamps:

Format: `YYYY-MM-DDTHH:MM:SSZ`
Example: `2025-10-06T12:34:56Z`

Always UTC timezone (indicated by `Z` suffix).

### Title Normalization

`{{Short title}}` converts topic to human-readable format:

Input topic: `feature-auth`
Output: `Feature Auth`

Input topic: `bug_fix_login`
Output: `Bug Fix Login`

## Environment-Specific Templates

### Development vs Production

```bash
# Development
export WATERCOOLER_TEMPLATES=~/templates/dev
watercooler init-thread test-feature

# Production
export WATERCOOLER_TEMPLATES=~/templates/prod
watercooler init-thread release-1.2
```

### Team-Specific Templates

```bash
# Backend team
export WATERCOOLER_TEMPLATES=/shared/templates/backend

# Frontend team
export WATERCOOLER_TEMPLATES=/shared/templates/frontend
```

## Troubleshooting

### Template Not Found

If template file is missing, watercooler-collab falls back to bundled templates without error.

To verify which template is used:

```bash
# Check template discovery
ls .watercooler/templates/_TEMPLATE_*.md
echo $WATERCOOLER_TEMPLATES
```

### Placeholder Not Replaced

If a placeholder isn't replaced:

1. Check spelling: `{{TOPIC}}` not `{{Topic}}`
2. Verify placeholder is supported for template type
3. Ensure value is provided (e.g., `--owner` for `{{OWNER}}`)

### Missing BODY Content

If body content doesn't appear:

1. Verify `{{BODY}}` is in template, or
2. Content auto-appends if BODY placeholder missing

## Best Practices

### 1. Start with Bundled Templates

Copy bundled templates as starting point:

```bash
mkdir -p .watercooler/templates
cp src/watercooler/templates/_TEMPLATE_*.md .watercooler/templates/
```

### 2. Keep Templates Consistent

Use same format across thread and entry templates for cohesive look.

### 3. Use Markdown Features

Templates support full markdown:
- Headers
- Tables
- Lists
- Blockquotes
- Code blocks

### 4. Version Control Templates

Commit project-local templates to git:

```bash
git add .watercooler/templates/
git commit -m "Add custom watercooler templates"
```

### 5. Document Template Requirements

If using custom templates, document required placeholders in team docs.

## Advanced Examples

### Timestamped Sections

```markdown
## {{UTC}} — {{TITLE}}

**{{AGENT}}** ({{ROLE}}) — {{TYPE}}

{{BODY}}

---
```

### Conditional Styling by Type

While templates don't support conditionals, you can create type-specific templates by having multiple versions and selecting via script.

### Integration with Tools

Templates can include tool-specific markers:

```markdown
---
Entry: {{AGENT}} {{UTC}}
Type: {{TYPE}}
Title: {{TITLE}}
<!-- Jira: PROJECT-123 -->
<!-- PR: #42 -->

{{BODY}}
```

## See Also

- [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md) - Entry roles and types
- [AGENT_REGISTRY.md](AGENT_REGISTRY.md) - Agent configuration
- [README.md](../README.md) - General usage
