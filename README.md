# watercooler-cloud

File-based collaboration protocol for agentic coding projects.

> **Landing Page:** The official website is maintained in a separate repository at [watercooler-site](https://github.com/mostlyharmless-ai/watercooler-site)

## Local MCP Quickstart (Recommended)

Run the MCP server locally and sync threads to a dedicated GitHub repo. This is the default workflow for small teams.

- Canonical guide: `docs/SETUP_AND_QUICKSTART.md`
- Remote (Cloudflare/Render) deployment is mothballed; see `.mothballed/docs/DEPLOYMENT_QUICK_START.md` for the archival instructions.

### 2‑Step Install & Register (Claude example)

```bash
# 1. Install with MCP extras
python -m pip install -e ".[mcp]"

# 2. Register the server with Claude Code (swap python/python3/py as needed)
claude mcp add watercooler-cloud \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -- python -m watercooler_mcp
```

> Prefer the helper scripts? See `./scripts/install-mcp.sh` (bash) or `./scripts/install-mcp.ps1` (PowerShell) for the same commands with argument prompts.

### Branch Pairing
Keep code and threads tightly linked:
- Pair each code repo with `<repo>-threads`
- Mirror branches 1:1 between code and threads
- Use commit footers to record `Code-Repo`, `Code-Branch`, and `Code-Commit`
- See `docs/BRANCH_PAIRING.md` for details

### Tester Setup
For a minimal validation loop (Claude + universal dev server) see:
- `docs/archive/TESTER_SETUP.md`

### Archived Remote Stack
The Cloudflare/Render remote deployment has been mothballed. All related code and docs are being
gathered under `.mothballed/` for later deletion. Prefer the local stdio MCP universal dev mode.

## Status

✅ **Full feature parity with acpmonkey achieved** - All phases (L1-L3) complete with 56 passing tests covering all features including structured entries, agent registry, and template system.

📋 Prerelease checklist lives in `docs/PRE_RELEASE_TODO.md` — keep it current as we finalize polish.

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
- **Agent Format**: `Agent (user)` with user tagging (e.g., "Claude (agent)")
- **Ball Auto-Flip**: say() flips to counterpart, ack() preserves current ball
- **Template Discovery**: CLI > env var > project-local > bundled
- **NEW Markers**: Flags when last entry author ≠ ball owner
- **CLOSED Filtering**: Exclude closed/done/merged/resolved threads
- **Test Coverage**: 56 passing tests (comprehensive coverage of all CLI commands and modules)

## Installation

Not yet published. For development:

```bash
git clone https://github.com/mostlyharmless-ai/watercooler-cloud.git
cd watercooler-cloud
pip install -e .
```

> **Note:** On Windows shells that expose `py` instead of `python3`, substitute `py -3 -m pip install -e .` (or `python -m pip ...`).

## Remote MCP Deployment — Archived

The hosted Cloudflare/Render deployment has been mothballed in favor of local universal dev mode. Historical notes and reactivation steps live under `.mothballed/` if you need to resurrect the stack.

### MCP Server (AI Agent Integration)

Enable AI agents (Claude, Codex) to discover and use watercooler tools automatically:

```bash
# Install with MCP support
python -m pip install -e ".[mcp]"
```

> If your system exposes `python3` or the Windows launcher `py`, replace the leading `python` with whichever command prints the correct Python 3 version (e.g., `python3 -m pip ...` or `py -m pip ...`).

### Quick registration commands

- **macOS / Linux / Git Bash** – use the helper script (requires Bash):

  ```bash
  ./scripts/install-mcp.sh
  ```

- **Windows PowerShell** – run the PowerShell helper (handles quoting automatically):

  ```powershell
  ./scripts/install-mcp.ps1 -Python python -Agent "Claude@Code"
  ```

  Override `-Python` with `py` or `python3` if needed. Additional flags are documented at the top of the script.
  If the MCP server already exists, the script will emit a warning and continue.
  Set `WATERCOOLER_THREADS_PATTERN` to an HTTPS URL if you prefer token/Git Credential Manager auth:

  ```powershell
  setx WATERCOOLER_THREADS_PATTERN "https://github.com/{namespace}/{repo}-threads.git"
  ```

- **Claude CLI command** – run directly from the repo root (swap `python` for `python3`/`py` if needed):

  ```bash
  claude mcp add --transport stdio watercooler-cloud --scope user \
    -e WATERCOOLER_AGENT="Claude@Code" \
    -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
    -e WATERCOOLER_AUTO_BRANCH=1 \
    -- python -m watercooler_mcp
  ```

  _If you previously registered `watercooler-universal`, remove it first with `claude mcp remove watercooler-universal`._

- **Codex CLI command** – same environment flags for Codex:

  ```bash
  codex mcp add watercooler-cloud \
    -e WATERCOOLER_AGENT="Codex" \
    -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
    -e WATERCOOLER_AUTO_BRANCH=1 \
    -- python -m watercooler_mcp
  ```

- **Any shell** – prefer an installer-style workflow? Use `fastmcp` (ensures identical behavior across platforms):

  ```bash
  fastmcp install claude-code src/watercooler_mcp/server.py \
    --server-name watercooler-cloud \
    --env WATERCOOLER_AGENT="Claude@Code" \
    --env WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
    --env WATERCOOLER_AUTO_BRANCH=1
  ```

See setup guides:
- **[Claude Code Setup](docs/archive/CLAUDE_CODE_SETUP.md)** - For Claude Code CLI
- **[Claude Desktop Setup](docs/archive/CLAUDE_DESKTOP_SETUP.md)** - For Claude Desktop app
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
  --owner agent \
  --participants "agent, Claude, Codex" \
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

## Troubleshooting

### Stale MCP Server Processes

If you interrupt the MCP server with CTRL-C, background processes may linger as orphaned daemons. This can cause issues with code updates not taking effect.

**Check for stale processes:**
```bash
./check-mcp-servers.sh
```

**Clean up stale processes:**
```bash
./cleanup-mcp-servers.sh
```

The check script warns about processes older than 1 hour. The cleanup script shows all watercooler MCP processes and prompts for confirmation before killing them.

**Manual cleanup:**
```bash
# Kill all watercooler MCP processes
pkill -f watercooler_mcp

# Or kill specific PIDs
ps aux | grep watercooler_mcp
kill <PID>
```

After cleanup, restart Claude Code (or your MCP client) to reconnect with fresh server processes.

## 📚 Documentation

### Getting Started
- **[Documentation Hub](docs/README.md)** - Complete documentation index
- **[Use Cases Guide](docs/archive/USE_CASES.md)** - 6 comprehensive workflow examples:
  - Multi-agent collaboration with role specialization
  - Extended context for LLM sessions
  - Handoff workflows (developer→reviewer, human→agent)
  - Async team collaboration across timezones
  - Decision tracking and architectural records
  - PR review workflow from design to deployment
- **[Claude Collaboration](docs/archive/claude-collab.md)** - Practical patterns for working with Claude
- **[FAQ](docs/FAQ.md)** - Frequently asked questions and troubleshooting

### Configuration & Reference
- **[API Reference](docs/archive/integration.md#python-api-reference)** - Python library API documentation
- **[Integration Guide](docs/archive/integration.md)** - Installation and integration tutorial
- **[MCP Server Guide](docs/mcp-server.md)** - AI agent integration via Model Context Protocol
- **[Claude Code Setup](docs/archive/CLAUDE_CODE_SETUP.md)** - Register watercooler with Claude Code
- **[Claude Desktop Setup](docs/archive/CLAUDE_DESKTOP_SETUP.md)** - Register watercooler with Claude Desktop
- **[Structured Entries](docs/STRUCTURED_ENTRIES.md)** - Entry format, 6 roles, 5 types, ball auto-flip
- **[Agent Registry](docs/archive/AGENT_REGISTRY.md)** - Agent configuration and counterpart mappings
- **[Templates](docs/archive/TEMPLATES.md)** - Customizing thread and entry templates
- **[Git Setup](./github/WATERCOOLER_SETUP.md)** - Merge strategies and pre-commit hooks
- **[Migration Guide](docs/MIGRATION.md)** - Migrating from acpmonkey

## License

MIT License - see LICENSE file

## Links

- Repository: https://github.com/mostlyharmless-ai/watercooler-cloud
- Issues: https://github.com/mostlyharmless-ai/watercooler-cloud/issues
