# Agent Registry Guide

The agent registry configures how watercooler-collab manages agents, their canonical names, counterpart relationships, and multi-agent collaboration chains.

> Replace any repo-local threads folder in the examples with the canonical path to your threads repository (e.g., `$HOME/.watercooler-threads/<org>/<repo>-threads`).

```bash
THREADS_DIR="$HOME/.watercooler-threads/<org>/<repo>-threads"
```

## Table of Contents

- [Overview](#overview)
- [Registry Structure](#registry-structure)
- [Agent Format](#agent-format)
- [Canonical Names](#canonical-names)
- [Counterpart Mappings](#counterpart-mappings)
- [Multi-Agent Chains](#multi-agent-chains)
- [Default Ball Owner](#default-ball-owner)
- [Using Agent Registry](#using-agent-registry)
- [Complete Examples](#complete-examples)
- [User Tagging](#user-tagging)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)
- [Advanced Patterns](#advanced-patterns)
- [See Also](#see-also)

## Overview

The agent registry is a JSON file that defines:
- **Canonical names**: How agent names are formatted (e.g., `codex` → `Codex`)
- **Counterpart mappings**: Who gets the ball next (e.g., `Codex` → `Claude`)
- **Multi-agent chains**: Complex handoff sequences (e.g., `A` → `B` → `C`)
- **Default ball owner**: Fallback agent for new threads

## Registry Structure

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

## Agent Format

Agents are represented as: `Agent (user)`

Examples:
- `Claude (agent)` - Claude agent used by user agent
- `Codex (sarah)` - Codex agent used by user sarah
- `Team (alex)` - Generic team entry by user alex

The user tag is automatically added based on:
1. Existing tag in input (if provided)
2. Git username (from git config)
3. OS username (fallback)

## Canonical Names

The `canonical` mapping standardizes agent name capitalization and formatting.

### Built-in Defaults

```json
{
  "canonical": {
    "claude": "Claude",
    "codex": "Codex",
    "team": "Team"
  }
}
```

### How It Works

Input (case-insensitive) → Output (canonical):
- `codex` → `Codex`
- `CODEX` → `Codex`
- `Codex` → `Codex`
- `claude` → `Claude`
- `team` → `Team`

### Custom Canonical Names

Add your own agents:

```json
{
  "canonical": {
    "claude": "Claude",
    "codex": "Codex",
    "team": "Team",
    "gpt4": "GPT-4",
    "gemini": "Gemini",
    "copilot": "GitHub Copilot"
  }
}
```

Usage:

```bash
watercooler --threads-dir "$THREADS_DIR" say topic \
  --agents-file agents.json \
  --agent gpt4 \
  --title "Review" \
  --body "Looks good"
# Creates entry with: "GPT-4 (username)"
```

## Counterpart Mappings

The `counterpart` mapping defines ball auto-flip behavior.

### Built-in Defaults

Simple two-way flip between Claude and Codex:

```json
{
  "counterpart": {
    "Codex": "Claude",
    "Claude": "Codex"
  }
}
```

Behavior:
- `say` from Codex → ball goes to Claude
- `say` from Claude → ball goes to Codex

### Custom Counterparts

#### Three-Agent Rotation

```json
{
  "canonical": {
    "planner": "Planner",
    "reviewer": "Reviewer",
    "implementer": "Implementer"
  },
  "counterpart": {
    "Planner": "Reviewer",
    "Reviewer": "Implementer",
    "Implementer": "Planner"
  }
}
```

Flow: Planner → Reviewer → Implementer → Planner → ...

Usage:

```bash
# Planner starts
watercooler --threads-dir "$THREADS_DIR" say topic --agent Planner --title "Design" --body "Plan created"
# Ball now with Reviewer

# Reviewer provides feedback
watercooler --threads-dir "$THREADS_DIR" say topic --agent Reviewer --title "Review" --body "Approved"
# Ball now with Implementer

# Implementer codes
watercooler --threads-dir "$THREADS_DIR" say topic --agent Implementer --title "Done" --body "Implemented"
# Ball back to Planner
```

#### Team → AI Agent Flow

```json
{
  "counterpart": {
    "Team": "Claude",
    "Claude": "Codex",
    "Codex": "Team"
  }
}
```

Flow: Team → Claude → Codex → Team → ...

#### Multiple AI Agents

```json
{
  "canonical": {
    "claude": "Claude",
    "gpt4": "GPT-4",
    "gemini": "Gemini"
  },
  "counterpart": {
    "Claude": "GPT-4",
    "GPT-4": "Gemini",
    "Gemini": "Claude"
  }
}
```

## Multi-Agent Chains

For complex workflows with more than two agents:

### Specialization Chain

```json
{
  "canonical": {
    "architect": "Architect",
    "backend": "Backend",
    "frontend": "Frontend",
    "qa": "QA",
    "devops": "DevOps"
  },
  "counterpart": {
    "Architect": "Backend",
    "Backend": "Frontend",
    "Frontend": "QA",
    "QA": "DevOps",
    "DevOps": "Architect"
  }
}
```

Workflow:
1. Architect designs
2. Backend implements API
3. Frontend builds UI
4. QA tests
5. DevOps deploys
6. Back to Architect for next iteration

### Review Pipeline

```json
{
  "canonical": {
    "developer": "Developer",
    "peer": "Peer Reviewer",
    "senior": "Senior Reviewer",
    "security": "Security Team"
  },
  "counterpart": {
    "Developer": "Peer Reviewer",
    "Peer Reviewer": "Senior Reviewer",
    "Senior Reviewer": "Security Team",
    "Security Team": "Developer"
  }
}
```

## Default Ball Owner

The `default_ball` field sets the fallback agent for new threads:

```json
{
  "default_ball": "Team"
}
```

Usage:

```bash
# Without specifying --ball
watercooler --threads-dir "$THREADS_DIR" init-thread topic --agents-file agents.json
# Ball defaults to "Team"

# With explicit --ball
watercooler --threads-dir "$THREADS_DIR" init-thread topic --agents-file agents.json --ball codex
# Ball is "codex" (overrides default)
```

## Using Agent Registry

### CLI Argument

```bash
watercooler --threads-dir "$THREADS_DIR" say topic \
  --agents-file /path/to/agents.json \
  --agent codex \
  --title "Done" \
  --body "Implementation complete"
```

### Per-Command Override

```bash
# Use custom registry for specific command
watercooler --threads-dir "$THREADS_DIR" say feature-auth \
  --agents-file ./team-agents.json \
  --agent backend \
  --title "API Ready" \
  --body "Endpoints implemented"

# Use default registry for another command
watercooler --threads-dir "$THREADS_DIR" say feature-ui \
  --agent claude \
  --title "UI Sketch" \
  --body "Wireframes attached"
```

### Project Configuration

Create a project-specific registry:

```bash
# Create project registry
THREADS_DIR="$HOME/.watercooler-threads/<org>/<repo>-threads"

cat > "$THREADS_DIR"/agents.json <<EOF
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
EOF

# Use in commands
watercooler say topic --threads-dir "$THREADS_DIR" --agents-file "$THREADS_DIR"/agents.json --agent codex --title "Update" --body "Done"
```

## Complete Examples

### Example 1: AI Coding Team

**Scenario**: Multiple AI agents with specialized roles

`agents.json`:
```json
{
  "canonical": {
    "claude": "Claude",
    "codex": "Codex",
    "copilot": "Copilot",
    "team": "Team"
  },
  "counterpart": {
    "Team": "Claude",
    "Claude": "Codex",
    "Codex": "Copilot",
    "Copilot": "Team"
  },
  "default_ball": "Team"
}
```

**Workflow**:
```bash
# Team creates plan
watercooler --threads-dir "$THREADS_DIR" init-thread feature-x --agents-file agents.json --ball team
watercooler --threads-dir "$THREADS_DIR" say feature-x --agents-file agents.json --agent team --title "Kickoff" --body "Build feature X"
# Ball → Claude

# Claude designs
watercooler --threads-dir "$THREADS_DIR" say feature-x --agents-file agents.json --agent claude --title "Design" --body "Architecture proposal"
# Ball → Codex

# Codex implements
watercooler --threads-dir "$THREADS_DIR" say feature-x --agents-file agents.json --agent codex --title "Implementation" --body "Core logic done"
# Ball → Copilot

# Copilot reviews
watercooler --threads-dir "$THREADS_DIR" say feature-x --agents-file agents.json --agent copilot --title "Review" --body "LGTM"
# Ball → Team

# Team closes
watercooler --threads-dir "$THREADS_DIR" say feature-x --agents-file agents.json --agent team --title "Complete" --body "Shipped!"
```

### Example 2: Human + AI Pair Programming

**Scenario**: Human developer working with AI assistant

`agents.json`:
```json
{
  "canonical": {
    "agent": "agent",
    "claude": "Claude"
  },
  "counterpart": {
    "agent": "Claude",
    "Claude": "agent"
  },
  "default_ball": "agent"
}
```

**Workflow**:
```bash
# agent starts
watercooler --threads-dir "$THREADS_DIR" init-thread bug-fix --agents-file agents.json --ball agent
watercooler --threads-dir "$THREADS_DIR" say bug-fix --agents-file agents.json --agent agent --title "Bug Found" --body "Login fails on Safari"
# Ball → Claude

# Claude analyzes
watercooler --threads-dir "$THREADS_DIR" say bug-fix --agents-file agents.json --agent claude --title "Root Cause" --body "Cookie SameSite issue"
# Ball → agent

# agent implements fix
watercooler --threads-dir "$THREADS_DIR" say bug-fix --agents-file agents.json --agent agent --title "Fixed" --body "Updated cookie settings"
# Ball → Claude

# Claude verifies
watercooler --threads-dir "$THREADS_DIR" say bug-fix --agents-file agents.json --agent claude --title "Verified" --body "Tests pass"
# Ball → agent
```

### Example 3: Specialized Reviewers

**Scenario**: Different reviewers for different aspects

`agents.json`:
```json
{
  "canonical": {
    "developer": "Developer",
    "security": "Security-AI",
    "performance": "Performance-AI",
    "ux": "UX-AI"
  },
  "counterpart": {
    "Developer": "Security-AI",
    "Security-AI": "Performance-AI",
    "Performance-AI": "UX-AI",
    "UX-AI": "Developer"
  },
  "default_ball": "Developer"
}
```

**Workflow**:
```bash
# Developer implements
watercooler --threads-dir "$THREADS_DIR" say feature --agents-file agents.json --agent developer --title "Feature Done" --body "Login with OAuth"
# Ball → Security-AI

# Security review
watercooler --threads-dir "$THREADS_DIR" say feature --agents-file agents.json --agent security --title "Security Check" --body "CSRF protection needed"
# Ball → Performance-AI

# Performance review
watercooler --threads-dir "$THREADS_DIR" say feature --agents-file agents.json --agent performance --title "Perf Check" --body "Response time good"
# Ball → UX-AI

# UX review
watercooler --threads-dir "$THREADS_DIR" say feature --agents-file agents.json --agent ux --title "UX Check" --body "Error messages unclear"
# Ball → Developer

# Developer addresses feedback
watercooler --threads-dir "$THREADS_DIR" say feature --agents-file agents.json --agent developer --title "Updated" --body "CSRF + UX fixes"
```

## User Tagging

User tags are automatically appended to agent names:

### Automatic Tagging

```bash
# Agent name: codex
# Git user: agent
# Result: Codex (agent)
watercooler --threads-dir "$THREADS_DIR" say topic --agent codex --title "Update" --body "Done"
```

Entry appears as:
```markdown
---
Entry: Codex (agent) 2025-10-06T12:34:56Z
...
```

### Explicit Tagging

Provide tag directly:

```bash
watercooler --threads-dir "$THREADS_DIR" say topic --agent "Claude (sarah)" --title "Review" --body "Approved"
```

Entry appears as:
```markdown
---
Entry: Claude (sarah) 2025-10-06T12:34:56Z
...
```

### Team Environments

In shared environments, tagging identifies who invoked which agent:

```bash
# agent uses Claude
watercooler --threads-dir "$THREADS_DIR" say topic --agent claude --title "Analysis" --body "Findings..."
# Entry: Claude (agent)

# Sarah uses Codex
watercooler --threads-dir "$THREADS_DIR" say topic --agent codex --title "Implementation" --body "Code..."
# Entry: Codex (sarah)
```

## Troubleshooting

### Counterpart Not Working

Check canonical names match:

```json
{
  "canonical": {
    "codex": "Codex"  // Lowercase key
  },
  "counterpart": {
    "Codex": "Claude"  // Capitalized key must match canonical output
  }
}
```

### Agent Name Not Capitalized

Ensure agent is in canonical mapping:

```json
{
  "canonical": {
    "myagent": "MyAgent"  // Add custom agents
  }
}
```

### Ball Not Auto-Flipping

Verify:
1. Using `say` not `ack` (ack preserves ball)
2. Counterpart defined in registry
3. Canonical names match in counterpart map

### User Tag Missing

User tag requires:
1. Git username configured, OR
2. OS username available, OR
3. Explicit tag in input: `--agent "Claude (user)"`

## Best Practices

### 1. Version Control Registry

Commit registry to git:

```bash
git add "$THREADS_DIR"/agents.json
git commit -m "Add watercooler agent registry"
```

### 2. Document Your Workflow

Add comments to registry (JSON doesn't support comments, use README):

```markdown
# Agent Registry

Our workflow: Team → Claude (design) → Codex (implementation) → Team
```

### 3. Consistent Naming

Use consistent canonical names:

✅ Good:
```json
{"canonical": {"claude": "Claude", "codex": "Codex"}}
```

❌ Bad:
```json
{"canonical": {"claude": "claude-3.5", "codex": "OpenAI-Codex"}}
```

### 4. Test Your Chains

Verify multi-agent chains work:

```bash
# Test each step in chain
watercooler --threads-dir "$THREADS_DIR" say test --agents-file agents.json --agent a --title "A" --body "From A"
watercooler --threads-dir "$THREADS_DIR" say test --agents-file agents.json --agent b --title "B" --body "From B"
watercooler --threads-dir "$THREADS_DIR" say test --agents-file agents.json --agent c --title "C" --body "From C"
```

### 5. Default to Simple

Start with simple two-agent flip, add complexity as needed:

```json
{
  "canonical": {"claude": "Claude", "codex": "Codex"},
  "counterpart": {"Codex": "Claude", "Claude": "Codex"}
}
```

## Advanced Patterns

### Conditional Counterparts

While registry doesn't support conditionals, you can use different registry files:

```bash
# Code review workflow
watercooler --threads-dir "$THREADS_DIR" say topic --agents-file review-agents.json --agent dev --title "PR" --body "Ready"

# Security workflow
watercooler --threads-dir "$THREADS_DIR" say topic --agents-file security-agents.json --agent dev --title "Scan" --body "Running"
```

### Role-Based Routing

Combine with structured entries:

```json
{
  "canonical": {
    "planner": "Planner-AI",
    "implementer": "Implementer-AI",
    "critic": "Critic-AI"
  },
  "counterpart": {
    "Planner-AI": "Implementer-AI",
    "Implementer-AI": "Critic-AI",
    "Critic-AI": "Planner-AI"
  }
}
```

Match agent names to roles:

```bash
watercooler --threads-dir "$THREADS_DIR" say topic --agents-file agents.json --agent planner --role planner --title "Design" --body "Plan..."
watercooler --threads-dir "$THREADS_DIR" say topic --agents-file agents.json --agent implementer --role implementer --title "Code" --body "Done..."
watercooler --threads-dir "$THREADS_DIR" say topic --agents-file agents.json --agent critic --role critic --title "Review" --body "LGTM..."
```

## See Also

- [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md) - Agent roles and entry types
- [TEMPLATES.md](TEMPLATES.md) - Template customization
- [README.md](../README.md) - General usage
