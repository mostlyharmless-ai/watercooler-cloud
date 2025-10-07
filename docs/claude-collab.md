# Claude Collaboration Workflow

This guide shows practical patterns for collaborating with Claude using the watercooler CLI.

## Table of Contents

- [Setup](#setup)
- [Basic Workflow: Start a Thread](#basic-workflow-start-a-thread)
- [Exchange Updates with Claude](#exchange-updates-with-claude)
- [Using Claude as Extended Context](#using-claude-as-extended-context)
- [Multi-Agent Workflows](#multi-agent-workflows)
- [Track and Export](#track-and-export)

---

## Setup

### Directory Configuration

Choose a threads directory (default `.watercooler` or set `WATERCOOLER_DIR`):

```bash
# Use default .watercooler directory
# (No configuration needed)

# Or customize:
export WATERCOOLER_DIR=./my-threads
```

### Agent Names

Use canonical agent names with role specification:
- `Claude` - Reasoning and planning agent
- `Codex` - Code generation agent
- `Team` - Human team members

Agent names are automatically tagged with user (e.g., `Claude (jay)`).

### Git Configuration

For team collaboration, configure git merge strategies:

```bash
git config merge.ours.driver true
git config core.hooksPath .githooks
```

See [.github/WATERCOOLER_SETUP.md](../.github/WATERCOOLER_SETUP.md) for details.

---

## Basic Workflow: Start a Thread

```bash
# Initialize thread for Claude discussion
watercooler init-thread claude-integration \
  --title "Claude Integration Features" \
  --owner Team \
  --participants "Team, Claude, Codex" \
  --ball claude

# Thread created at: .watercooler/claude-integration.md
```

---

## Exchange Updates with Claude

### Pattern 1: Ask Claude a Question

```bash
# Human asks Claude for review
watercooler say claude-integration \
  --agent Team \
  --role pm \
  --title "Review Request" \
  --body "Claude, please review L3 features and suggest gaps for L4."

# Ball auto-flips to: claude (counterpart)
```

### Pattern 2: Record Claude's Response

After Claude provides analysis (via API or interactive session):

```bash
# Record Claude's insights
watercooler say claude-integration \
  --agent Claude \
  --role planner \
  --title "L4 Recommendations" \
  --type Plan \
  --body "Suggested additions: (1) handoff command, (2) refine NEW markers, (3) web-export improvements."

# Ball auto-flips to: team
```

### Pattern 3: Acknowledge Without Ball Flip

```bash
# Acknowledge without changing ball owner
watercooler ack claude-integration \
  --agent Team \
  --role pm \
  --title "Acknowledged" \
  --body "Thanks - will implement handoff command first."

# Ball stays with: team
```

### Pattern 4: Explicit Handoff

```bash
# Explicit handoff to Codex for implementation
watercooler handoff claude-integration \
  --agent Team \
  --role pm \
  --note "Codex, please implement handoff command per Claude's design"

# Ball explicitly set to: codex
```

---

## Using Claude as Extended Context

### Problem: Context Window Exhaustion

When Claude's context window fills up, use watercooler threads as persistent memory:

```bash
# Session 1: Initial planning (context fills up)
watercooler say feature-design \
  --agent Claude \
  --role planner \
  --title "Architecture Design" \
  --body @long-design-doc.md
# (10,000 tokens of detailed design)

# Context window near limit...
```

```bash
# Session 2: Resume work (new context, read thread)
# Human prompt to Claude:
"Read .watercooler/feature-design.md for context, then implement phase 1"

# Claude reads thread, continues work:
watercooler say feature-design \
  --agent Claude \
  --role implementer \
  --title "Phase 1 Implementation" \
  --body "Implemented core API based on architecture from 2025-10-07 design."
```

### Pattern: Reference Threads in Prompts

Instead of re-explaining context:

```
❌ Bad: "Last week we discussed using JWT auth with OAuth2 for social login.
We decided on token rotation every 15 minutes. The security concerns were..."
(Wastes 500+ tokens re-explaining)

✅ Good: "Read .watercooler/auth-design.md then implement the OAuth2 flow"
(Claude reads structured thread history, 0 wasted tokens)
```

---

## Multi-Agent Workflows

### Claude + Codex Collaboration

```bash
# Claude plans
watercooler say api-redesign \
  --agent Claude \
  --role planner \
  --title "API v2 Design" \
  --type Plan \
  --body "RESTful design with versioned endpoints. See attached spec."
# Ball auto-flips to: codex

# Codex implements
watercooler say api-redesign \
  --agent Codex \
  --role implementer \
  --title "Implementation Complete" \
  --body "Endpoints implemented. Tests at 90% coverage."
# Ball auto-flips to: claude

# Claude reviews
watercooler say api-redesign \
  --agent Claude \
  --role critic \
  --title "Review Complete" \
  --type Decision \
  --body "Approved. Minor suggestion: add request validation middleware."
# Ball auto-flips to: codex
```

### Agent Registry for Auto-Flip

Configure counterpart mappings in `agents.json`:

```json
{
  "agents": {
    "claude": {
      "name": "Claude",
      "counterpart": "codex",
      "default_role": "planner"
    },
    "codex": {
      "name": "Codex",
      "counterpart": "claude",
      "default_role": "implementer"
    },
    "team": {
      "name": "Team",
      "counterpart": "claude",
      "default_role": "pm"
    }
  }
}
```

Use with commands:

```bash
watercooler say feature-design \
  --agents-file ./agents.json \
  --agent claude \
  --title "Design Complete"
# Auto-flips to counterpart (codex) based on registry
```

---

## Track and Export

### List Threads

```bash
# List all open threads
watercooler list

# List with NEW markers
watercooler list --open-only
# 2025-10-07T12:00:00Z  open  claude  NEW  Claude Integration  claude-integration.md

# NEW marker means: ball is with claude, but last entry wasn't from claude
```

### Search Threads

```bash
# Find threads by keyword
watercooler search "authentication"
watercooler search "Claude"

# Returns: file:line: matching text
```

### Generate Indexes

```bash
# Markdown index
watercooler reindex
# Creates: .watercooler/index.md

# HTML web export
watercooler web-export
# Creates: .watercooler/index.html
# Open in browser for dashboard view
```

### Git Workflow

```bash
# After each significant update
git add .watercooler/
git commit -m "watercooler: claude-integration design review"
git push

# Team members pull to see updates
git pull
watercooler list --open-only
```

---

## Complete Example: Feature Development

```bash
# 1. Human requests feature from Claude
watercooler init-thread feature-search --ball claude

watercooler say feature-search \
  --agent Team \
  --role pm \
  --title "Feature Request: Search" \
  --body "Need full-text search for blog. Requirements: fuzzy match, autocomplete."

# 2. Claude designs approach
watercooler say feature-search \
  --agent Claude \
  --role planner \
  --title "Search Design" \
  --type Plan \
  --body "Use PostgreSQL tsvector + GIN index. Frontend: debounced autocomplete."

# 3. Human approves and delegates to Codex
watercooler handoff feature-search \
  --agent Team \
  --note "Approved. Codex, please implement."

# 4. Codex implements
watercooler say feature-search \
  --agent Codex \
  --role implementer \
  --title "Implementation Complete" \
  --body "Search implemented. PR #456. Tests passing."

# 5. Claude reviews code
watercooler say feature-search \
  --agent Claude \
  --role critic \
  --title "Code Review" \
  --type Decision \
  --body "Looks good. Request: add input sanitization."

# 6. Codex fixes
watercooler say feature-search \
  --agent Codex \
  --role implementer \
  --title "Sanitization Added" \
  --body "Added input validation. Updated tests."

# 7. Claude approves
watercooler say feature-search \
  --agent Claude \
  --role critic \
  --title "Approved" \
  --type Decision \
  --body "LGTM"

# 8. Human merges and closes
watercooler say feature-search \
  --agent Team \
  --role pm \
  --title "Deployed" \
  --type Closure \
  --body "PR merged. Deployed to production." \
  --status closed

git add .watercooler/feature-search.md
git commit -m "watercooler: feature-search deployed"
git push
```

---

## See Also

- [USE_CASES.md](USE_CASES.md) - Comprehensive use case examples
- [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md) - Entry format and metadata
- [AGENT_REGISTRY.md](AGENT_REGISTRY.md) - Agent configuration details
- [README.md](../README.md) - Command reference and installation

