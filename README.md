# watercooler-cloud

File-based collaboration protocol for agentic coding projects. Licensed under [Apache 2.0](./LICENSE).

> **Landing Page:** The official website is maintained in a separate repository at [watercooler-site](https://github.com/mostlyharmless-ai/watercooler-site)
>
> **New contributors:** Start with [CONTRIBUTING.md](./CONTRIBUTING.md) for setup and the Developer Certificate of Origin requirements.

## How to get started?
### Two key steps

<details>
<summary>1. Clone, install, and start the local server</summary>

```bash
git clone https://github.com/mostlyharmless-ai/watercooler-cloud.git
cd watercooler-cloud
pip install -e .
python -m watercooler_dashboard.local_app
```

Keep this terminal open while you use Watercooler; the dashboard serves at [http://127.0.0.1:8080](http://127.0.0.1:8080).  
> **Windows tip:** if your shell exposes `py`, use `py -3 -m pip install -e .` (or `python -m pip …`).
</details>

<details>
<summary>2. Configure MCP clients (Claude, Codex, …)</summary>

Watercooler now defaults to HTTPS remotes (e.g., `https://github.com/org/repo-threads.git`) so Git Credential Manager / PAT workflows work without extra setup. If you prefer SSH, set `WATERCOOLER_THREADS_PATTERN` to `git@github.com:{org}/{repo}-threads.git`.

For HTTPS environments, ensure the variable points at your remote before starting clients:

```bash
export WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git"
# Windows PowerShell:
# setx WATERCOOLER_THREADS_PATTERN "https://github.com/{org}/{repo}-threads.git"
```

If you switch to SSH instead:

```bash
export WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git"
# Windows PowerShell:
# setx WATERCOOLER_THREADS_PATTERN "git@github.com:{org}/{repo}-threads.git"
```

Choose one of the options below to register the MCP server with your client:

<details>
<summary>Helper scripts (prompt-driven)</summary>

- macOS/Linux/Git Bash:
  ```bash
  ./scripts/install-mcp.sh
  ```
- Windows PowerShell:
  ```powershell
  ./scripts/install-mcp.ps1 -Python python -Agent "Claude@Code"
  ```
  Override `-Python` with `py`/`python3` as needed; additional flags are documented at the top of the script.
</details>

<details>
<summary>Claude CLI</summary>

```bash
claude mcp add --transport stdio watercooler-cloud --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python -m watercooler_mcp
```

_If you previously registered `watercooler-universal`, remove it first with `claude mcp remove watercooler-universal`._
</details>

<details>
<summary>Codex CLI</summary>

```bash
codex mcp add watercooler-cloud \
  -e WATERCOOLER_AGENT="Codex" \
  -e WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python -m watercooler_mcp
```
</details>

<details>
<summary>Any shell via <code>fastmcp</code></summary>

```bash
fastmcp install claude-code src/watercooler_mcp/server.py \
  --server-name watercooler-cloud \
  --env WATERCOOLER_AGENT="Claude@Code" \
  --env WATERCOOLER_THREADS_PATTERN="https://github.com/{org}/{repo}-threads.git" \
  --env WATERCOOLER_AUTO_BRANCH=1
```
</details>

More detail:
- **[SETUP_AND_QUICKSTART](docs/SETUP_AND_QUICKSTART.md)**
- **[Claude Code Setup](docs/archive/CLAUDE_CODE_SETUP.md)**
- **[Claude Desktop Setup](docs/archive/CLAUDE_DESKTOP_SETUP.md)**
- **[MCP Server Guide](docs/mcp-server.md)**

</details>


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

### Git authentication errors

- **HTTPS (default):** ensure \`git push https://github.com/<org>/<repo>-threads.git\` works with your credential helper.
- **SSH optional:** set \`WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git"\` and load your SSH key (`ssh-add`).
- Restart your MCP client after changing the pattern so the new value takes effect.

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

Apache-2.0 License - see [LICENSE](./LICENSE)

## Links

- Repository: https://github.com/mostlyharmless-ai/watercooler-cloud
- Issues: https://github.com/mostlyharmless-ai/watercooler-cloud/issues
