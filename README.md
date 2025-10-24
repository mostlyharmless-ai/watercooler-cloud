# watercooler-collab

File-based collaboration protocol for agentic coding projects.

## Status

✅ **Full feature parity with acpmonkey achieved** - All phases (L1-L3) complete with 56 passing tests covering all features including structured entries, agent registry, and template system.

## Design Principles

- **Stdlib-only**: No external runtime dependencies
- **File-based**: Git-friendly markdown threads with explicit Status/Ball tracking
- **Zero-config**: Works out-of-box for standard project layouts
- **CLI parity**: Drop-in replacement for existing watercooler.py workflows

## Architecture

Thread-based collaboration with:
- **Status tracking**: OPEN, IN_REVIEW, CLOSED, and custom statuses
- **Ball ownership**: Explicit tracking of who has the next action
- **Structured entries**: Agent, Role, Type, Title metadata for each entry
- **Agent registry**: Canonical names, counterpart mappings, multi-agent chains
- **Template system**: Customizable thread and entry templates with placeholder support
- **Advisory file locking**: PID-aware locks with TTL for concurrent safety
- **Automatic backups**: Rolling backups per thread in `.bak/<topic>/`
- **Index generation**: Actionable/Open/In Review summaries with NEW markers

## Features

- **12 CLI Commands**: init-thread, append-entry, say, ack, handoff, set-status, set-ball, list, reindex, search, web-export, unlock
- **6 Agent Roles**: planner, critic, implementer, tester, pm, scribe
- **5 Entry Types**: Note, Plan, Decision, PR, Closure
- **Agent Format**: `Agent (user)` with user tagging (e.g., "Claude (jay)")
- **Ball Auto-Flip**: say() flips to counterpart, ack() preserves current ball
- **Template Discovery**: CLI > env var > project-local > bundled
- **NEW Markers**: Flags when last entry author ≠ ball owner
- **CLOSED Filtering**: Exclude closed/done/merged/resolved threads
- **Test Coverage**: 56 passing tests (comprehensive coverage of all CLI commands and modules)

## Installation

Not yet published. For development:

```bash
git clone https://github.com/mostlyharmless-ai/watercooler-collab.git
cd watercooler-collab
pip install -e .
```

## Remote MCP Deployment — Quick Checklist

- Full guide: see `docs/DEPLOYMENT.md`.
- Cloudflare Worker
  - Set `BACKEND_URL` to your Render URL and `INTERNAL_AUTH_SECRET` (via Wrangler Secret or CF UI).
  - Deploy: `npx wrangler secret put INTERNAL_AUTH_SECRET` then `npx wrangler deploy`.
- Render Backend
  - Env: `INTERNAL_AUTH_SECRET` (match Worker), `BASE_THREADS_ROOT=/data/wc-cloud`, `WATERCOOLER_DIR=/data/wc-cloud`.
  - Optional Git backup: `WATERCOOLER_GIT_REPO`, `WATERCOOLER_GIT_AUTHOR`, `WATERCOOLER_GIT_EMAIL`, `GIT_SSH_PRIVATE_KEY` (PEM).
  - Start: copy a one‑liner from `scratch.txt` into Render → Settings → Start command.
  - Disk: attach a persistent disk mounted at `/data`.
- Test end‑to‑end
  - Backend direct: `POST /mcp/watercooler_v1_health | _say | _read_thread` with `X-Internal-Auth`.
  - Worker path: `GET /sse` → `initialize` → `tools/list` → `tools/call`.

### MCP Server (AI Agent Integration)

Enable AI agents (Claude, Codex) to discover and use watercooler tools automatically:

```bash
# Install with MCP support
pip install -e ".[mcp]"

# Quick setup for Claude Code (recommended)
./scripts/install-mcp.sh

# Or manually register
fastmcp install claude-code src/watercooler_mcp/server.py \
  --env WATERCOOLER_AGENT=Claude
```

See setup guides:
- **[Claude Code Setup](docs/CLAUDE_CODE_SETUP.md)** - For Claude Code CLI
- **[Claude Desktop Setup](docs/CLAUDE_DESKTOP_SETUP.md)** - For Claude Desktop app
- **[MCP Server Guide](docs/mcp-server.md)** - Complete tool reference

### Git Configuration (Multi-User Collaboration)

For team collaboration, configure git merge strategies and pre-commit hooks:

```bash
# Required: Enable "ours" merge driver
git config merge.ours.driver true

# Recommended: Enable pre-commit hook (enforces append-only protocol)
git config core.hooksPath .githooks
```

See [.github/WATERCOOLER_SETUP.md](.github/WATERCOOLER_SETUP.md) for detailed setup guide.

## Quick Examples

### Basic Thread Management

```bash
# Initialize a thread with custom metadata
watercooler init-thread feature-auth \
  --owner Jay \
  --participants "Jay, Claude, Codex" \
  --ball codex

# Add structured entry with role and type
watercooler append-entry feature-auth \
  --agent Claude \
  --role critic \
  --title "Security Review Complete" \
  --type Decision \
  --body "Authentication approach approved"

# Quick team note with auto-ball-flip
watercooler say feature-auth \
  --agent Team \
  --role pm \
  --title "Timeline Update" \
  --body "Target: end of sprint"

# Acknowledge without flipping ball
watercooler ack feature-auth

# Explicit handoff to counterpart
watercooler handoff feature-auth \
  --agent Codex \
  --note "Ready for implementation"

# Update status
watercooler set-status feature-auth in-review

# Note: All commands default to .watercooler directory
# Use --threads-dir to override
```

### Agent Registry and Templates

```bash
# Use custom agent registry
watercooler say feature-auth \
  --agents-file ./agents.json \
  --agent codex \
  --role implementer \
  --title "Implementation Complete" \
  --body "All tests passing"

# Use custom templates
export WATERCOOLER_TEMPLATES=/path/to/custom/templates
watercooler init-thread new-topic
```

### Listing and Search

```bash
# List all open threads
watercooler list

# List only closed threads
watercooler list --closed-only

# Search across threads
watercooler search "security"

# Generate markdown index
watercooler reindex

# Export HTML index
watercooler web-export

# Override default directory
watercooler list --threads-dir ./custom-threads
```

## Structured Entry Format

Each entry includes rich metadata:

```markdown
---
Entry: Agent (user) 2025-10-06T12:00:00Z
Role: critic
Type: Decision
Title: Security Review Complete

Authentication approach approved. All edge cases covered.
```

**Agent Roles:**
- `planner` - Architecture and design decisions
- `critic` - Code review and quality assessment
- `implementer` - Feature implementation
- `tester` - Test coverage and validation
- `pm` - Project management and coordination
- `scribe` - Documentation and notes

**Entry Types:**
- `Note` - General observations and updates
- `Plan` - Design proposals and roadmaps
- `Decision` - Architectural or technical decisions
- `PR` - Pull request related entries
- `Closure` - Thread conclusion and summary

## Development

Run tests:
```bash
pip install -e ".[dev]"
pytest tests/ -v

# Run specific test suites
pytest tests/test_templates.py -v
pytest tests/test_config.py -v
pytest tests/test_structured_entries.py -v
```

## 📚 Documentation

### Getting Started
- **[Documentation Hub](docs/README.md)** - Complete documentation index
- **[Use Cases Guide](docs/USE_CASES.md)** - 6 comprehensive workflow examples:
  - Multi-agent collaboration with role specialization
  - Extended context for LLM sessions
  - Handoff workflows (developer→reviewer, human→agent)
  - Async team collaboration across timezones
  - Decision tracking and architectural records
  - PR review workflow from design to deployment
- **[Claude Collaboration](docs/claude-collab.md)** - Practical patterns for working with Claude
- **[FAQ](docs/FAQ.md)** - Frequently asked questions and troubleshooting

### Configuration & Reference
- **[API Reference](docs/api.md)** - Python library API documentation
- **[Integration Guide](docs/integration.md)** - Installation and integration tutorial
- **[MCP Server Guide](docs/mcp-server.md)** - AI agent integration via Model Context Protocol
- **[Claude Code Setup](docs/CLAUDE_CODE_SETUP.md)** - Register watercooler with Claude Code
- **[Claude Desktop Setup](docs/CLAUDE_DESKTOP_SETUP.md)** - Register watercooler with Claude Desktop
- **[Structured Entries](docs/STRUCTURED_ENTRIES.md)** - Entry format, 6 roles, 5 types, ball auto-flip
- **[Agent Registry](docs/AGENT_REGISTRY.md)** - Agent configuration and counterpart mappings
- **[Templates](docs/TEMPLATES.md)** - Customizing thread and entry templates
- **[Git Setup](./github/WATERCOOLER_SETUP.md)** - Merge strategies and pre-commit hooks
- **[Migration Guide](docs/MIGRATION.md)** - Migrating from acpmonkey

## License

MIT License - see LICENSE file

## Links

- Repository: https://github.com/mostlyharmless-ai/watercooler-collab
- Issues: https://github.com/mostlyharmless-ai/watercooler-collab/issues
