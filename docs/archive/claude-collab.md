# Claude Collaboration Workflow (CLI)

**Note:** This guide covers **manual CLI workflows** using the `watercooler` command-line tool. Replace any repo-local thread folders with your threads repository (for example, the sibling `../<repo>-threads` directory). For **automated MCP server integration** (where Claude automatically uses watercooler tools), see:
- [Claude Code Setup](./CLAUDE_CODE_SETUP.md) - For Claude Code CLI
- [Claude Desktop Setup](./CLAUDE_DESKTOP_SETUP.md) - For Claude Desktop app

This guide shows practical patterns for collaborating with Claude using the watercooler CLI **manually** (useful for automation scripts or understanding the underlying commands).

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

Choose a threads directory (mirror repository):

```bash
THREADS_DIR="../<repo>-threads"
```

### Agent Names

Use canonical agent names with role specification:
- `Claude` - Reasoning and planning agent
- `Codex` - Code generation agent
- `Team` - Human team members

Agent names are automatically tagged with user (e.g., `Claude (agent)`).

### Git Configuration

For team collaboration, configure git merge strategies:

```bash
git config merge.ours.driver true
git config core.hooksPath .githooks
```

See [.github/WATERCOOLER_SETUP.md](../../.github/WATERCOOLER_SETUP.md) for details.

---

## Basic Workflow: Start a Thread

```bash
# Initialize thread for Claude discussion
watercooler --threads-dir "$THREADS_DIR" init-thread claude-integration \
  --title "Claude Integration Features" \
  --owner Team \
  --participants "Team, Claude, Codex" \
  --ball claude

# Thread created at: $THREADS_DIR/claude-integration.md
```

---

## Exchange Updates with Claude

### Pattern 1: Ask Claude a Question

```bash
# Human asks Claude for review
watercooler --threads-dir "$THREADS_DIR" say claude-integration \
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
watercooler --threads-dir "$THREADS_DIR" say claude-integration \
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
watercooler --threads-dir "$THREADS_DIR" ack claude-integration \
  --agent Team \
  --role pm \
  --title "Acknowledged" \
  --body "Thanks - will implement handoff command first."

# Ball stays with: team
```

### Pattern 4: Explicit Handoff

```bash
# Explicit handoff to Codex for implementation
watercooler --threads-dir "$THREADS_DIR" handoff claude-integration \
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
watercooler --threads-dir "$THREADS_DIR" say feature-design \
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
"Read $THREADS_DIR/feature-design.md for context, then implement phase 1"

# Claude reads thread, continues work:
watercooler --threads-dir "$THREADS_DIR" say feature-design \
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

✅ Good: "Read $THREADS_DIR/auth-design.md then implement the OAuth2 flow"
(Claude reads structured thread history, 0 wasted tokens)
```

---

## Multi-Agent Workflows

### Claude + Codex Collaboration

```bash
# Claude plans
watercooler --threads-dir "$THREADS_DIR" say api-redesign \
  --agent Claude \
  --role planner \
  --title "API v2 Design" \
  --type Plan \
  --body "RESTful design with versioned endpoints. See attached spec."
# Ball auto-flips to: codex

# Codex implements
watercooler --threads-dir "$THREADS_DIR" say api-redesign \
  --agent Codex \
  --role implementer \
  --title "Implementation Complete" \
  --body "Endpoints implemented. Tests at 90% coverage."
# Ball auto-flips to: claude

# Claude reviews
watercooler --threads-dir "$THREADS_DIR" say api-redesign \
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
watercooler --threads-dir "$THREADS_DIR" say feature-design \
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
watercooler --threads-dir "$THREADS_DIR" list

# List with NEW markers
watercooler --threads-dir "$THREADS_DIR" list --open-only
# 2025-10-07T12:00:00Z  open  claude  NEW  Claude Integration  claude-integration.md

# NEW marker means: ball is with claude, but last entry wasn't from claude
```

### Search Threads

```bash
# Find threads by keyword
watercooler --threads-dir "$THREADS_DIR" search "authentication"
watercooler --threads-dir "$THREADS_DIR" search "Claude"

# Returns: file:line: matching text
```

### Generate Indexes

```bash
# Markdown index
watercooler --threads-dir "$THREADS_DIR" reindex
# Creates: $THREADS_DIR/index.md

# HTML web export
watercooler --threads-dir "$THREADS_DIR" web-export
# Creates: $THREADS_DIR/index.html
# Open in browser for dashboard view
```

### Git Workflow

```bash
# After each significant update
git add "$THREADS_DIR"/
git commit -m "watercooler: claude-integration design review"
git push

# Team members pull to see updates
git pull
watercooler --threads-dir "$THREADS_DIR" list --open-only
```

---

## Complete Example: Feature Development

```bash
# 1. Human requests feature from Claude
watercooler --threads-dir "$THREADS_DIR" init-thread feature-search --ball claude

watercooler --threads-dir "$THREADS_DIR" say feature-search \
  --agent Team \
  --role pm \
  --title "Feature Request: Search" \
  --body "Need full-text search for blog. Requirements: fuzzy match, autocomplete."

# 2. Claude designs approach
watercooler --threads-dir "$THREADS_DIR" say feature-search \
  --agent Claude \
  --role planner \
  --title "Search Design" \
  --type Plan \
  --body "Use PostgreSQL tsvector + GIN index. Frontend: debounced autocomplete."

# 3. Human approves and delegates to Codex
watercooler --threads-dir "$THREADS_DIR" handoff feature-search \
  --agent Team \
  --note "Approved. Codex, please implement."

# 4. Codex implements
watercooler --threads-dir "$THREADS_DIR" say feature-search \
  --agent Codex \
  --role implementer \
  --title "Implementation Complete" \
  --body "Search implemented. PR #456. Tests passing."

# 5. Claude reviews code
watercooler --threads-dir "$THREADS_DIR" say feature-search \
  --agent Claude \
  --role critic \
  --title "Code Review" \
  --type Decision \
  --body "Looks good. Request: add input sanitization."

# 6. Codex fixes
watercooler --threads-dir "$THREADS_DIR" say feature-search \
  --agent Codex \
  --role implementer \
  --title "Sanitization Added" \
  --body "Added input validation. Updated tests."

# 7. Claude approves
watercooler --threads-dir "$THREADS_DIR" say feature-search \
  --agent Claude \
  --role critic \
  --title "Approved" \
  --type Decision \
  --body "LGTM"

# 8. Human merges and closes
watercooler --threads-dir "$THREADS_DIR" say feature-search \
  --agent Team \
  --role pm \
  --title "Deployed" \
  --type Closure \
  --body "PR merged. Deployed to production." \
  --status closed

git add "$THREADS_DIR"/feature-search.md
git commit -m "watercooler: feature-search deployed"
git push
```

---

## See Also

- [USE_CASES.md](USE_CASES.md) - Comprehensive use case examples
- [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md) - Entry format and metadata
- [AGENT_REGISTRY.md](AGENT_REGISTRY.md) - Agent configuration details
- [README.md](../../README.md) - Command reference and installation
