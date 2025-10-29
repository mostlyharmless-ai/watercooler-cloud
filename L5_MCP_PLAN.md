# L5: Watercooler MCP Server Implementation Plan

**Date:** 2025-10-07 (Updated: 2025-10-09)
**Status:** Phase 2A Complete - Cloud Sync Implemented
**Goal:** Create an MCP server for watercooler-collab using fastmcp 2.0, with cloud deployment options

## Background

During testing of watercooler-collab in a test project, we discovered a critical UX issue: when an AI agent (like Codex) starts fresh in a project with watercooler threads, they have no context about:
- What watercooler is
- How to use it
- That there are threads waiting for their response

**Solution:** Make watercooler an MCP server that exposes tools to AI agents automatically.

## Benefits of MCP Server Approach

### For Single Agent/Project
- **Auto-discovery:** AI sees watercooler tools available in environment
- **Self-documenting:** Tool descriptions explain the system
- **No manual setup:** Just works when AI starts
- **Seamless:** No need to read markdown files directly

### For Distributed Teams (Cloud Deployment)
- **Async collaboration:** Team members in different timezones
- **Unified interface:** Same tools for all AI agents (Claude, GPT, etc.)
- **Git-based sync:** Push/pull for updates
- **Concurrent access:** Advisory locking prevents conflicts

## Research Phase

### 1. fastmcp 2.0 API Research ✅ COMPLETE
Learned from Context7:
- [x] Core API for creating MCP server - `FastMCP(name="Server Name")`
- [x] Tool definition with decorators - `@mcp.tool` auto-infers name, description, schema from function signature
- [x] Tool schemas and descriptions - Uses type hints + docstrings
- [x] Authentication and user context handling - `Context` object can be injected
- [x] fastmcp cloud deployment process - HTTP transport with `mcp.run(transport="http", port=8000)`

**Key Findings:**
- Simple decorator pattern: `@mcp.tool` wraps Python functions
- Auto-schema generation from type hints (e.g., `def add(a: int, b: int) -> int`)
- Docstrings become tool descriptions for LLMs
- Both sync and async functions supported
- Resources use `@mcp.resource(uri)` decorator
- Default transport is STDIO, but HTTP available
- Can run locally or deploy to cloud

### 2. Cloudflare Deployment Research
Investigate:
- [ ] Cloudflare Workers for MCP server hosting
- [ ] Python/MCP server deployment on Cloudflare
- [ ] Compare with fastmcp cloud capabilities
- [ ] Pros/cons of each platform

### 3. Architecture Design ✅ COMPLETE

**Local MCP Server Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│ FastMCP Server (watercooler_mcp)                        │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  @mcp.tool decorated wrappers                            │
│  ├── list_threads()      → commands.list_threads()      │
│  ├── read_thread(topic)  → fs.read_body()               │
│  ├── say(...)            → commands.say()                │
│  ├── ack(...)            → commands.ack()                │
│  ├── handoff(...)        → commands.handoff()            │
│  ├── set_status(...)     → commands.set_status()         │
│  └── reindex()           → generate index                │
│                                                           │
│  Configuration:                                          │
│  ├── Auto-discover .watercooler/ in project             │
│  ├── Read WATERCOOLER_AGENT env var for identity        │
│  ├── Use local watercooler.commands API                 │
│  └── Advisory locking handled by watercooler lib        │
│                                                           │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
              ┌──────────────────────┐
              │ .watercooler/        │
              │ └── threads/         │
              │     ├── topic-1.md   │
              │     └── topic-2.md   │
              └──────────────────────┘
```

**Key Design Decisions:**

1. **Agent Identity:**
   - Read from `WATERCOOLER_AGENT` environment variable
   - Format: "AgentName" (e.g., "Codex", "Claude")
   - Falls back to "Agent" if not set
   - Configuration at MCP client level (not server)

2. **State Management:**
   - Local filesystem only for Phase 1
   - Direct access to `.watercooler/` directory
   - Uses existing watercooler-collab advisory locking
   - No git operations in local mode

3. **Tool Design:**
   - Thin wrappers around `watercooler.commands` functions
   - Preserve all watercooler-collab functionality
   - Rich docstrings for LLM understanding
   - Type hints for automatic schema generation

4. **Discovery:**
   - Auto-find `.watercooler/` in current directory
   - MCP tools are auto-discoverable by AI agents
   - No manual configuration needed

## MCP Tools to Implement

Map watercooler CLI commands → MCP tools with detailed signatures:

### 0. Health and Identity (Phase 1A)
```python
@mcp.tool
def health() -> str:
    """Return server health, version, and threads dir."""

@mcp.tool
def whoami() -> str:
    """Return resolved agent identity (e.g., "Codex")."""
```

### 1. `list_threads(open_only: bool | None = None, limit: int = 50, cursor: str | None = None, format: Literal["markdown","json"] = "markdown")`
```python
@mcp.tool
def list_threads(open_only: bool | None = None, limit: int = 50, cursor: str | None = None, format: str = "markdown") -> str:
    """List all watercooler threads.

    Shows open threads where you have the ball (actionable items),
    threads where you're waiting on others, and marks NEW entries
    since you last contributed.

    Returns a formatted summary with:
    - Threads where you have the ball (🎾 marker)
    - Threads with NEW entries for you to read
    - Thread status and last update time
    
    Phase 1A: `format` must be "markdown"; JSON planned for Phase 1B.
    """
```

### 2. `read_thread(topic: str, from_entry: int = 0, limit: int = 100, format: Literal["markdown","json"] = "markdown")`
```python
@mcp.tool
def read_thread(topic: str, from_entry: int = 0, limit: int = 100, format: str = "markdown") -> str:
    """Read the complete content of a watercooler thread.

    Args:
        topic: The thread topic identifier (e.g., "feature-auth")
        from_entry: Starting entry index for pagination
        limit: Max entries to include

    Returns the full markdown content including:
    - Thread metadata (status, ball owner, participants)
    - All entries with timestamps, authors, roles, and types
    - Current ball ownership status

    Phase 1A: `format` must be "markdown"; JSON planned for Phase 1B.
    """
```

### 3. `say(topic: str, title: str, body: str, role: str = "implementer", entry_type: str = "Note")`
```python
@mcp.tool
def say(
    topic: str,
    title: str,
    body: str,
    role: str = "implementer",
    entry_type: str = "Note"
) -> str:
    """Add your response to a thread and flip the ball to your counterpart.

    Use this when you want to contribute and pass the action to another agent.
    The ball automatically flips to your configured counterpart.

    Args:
        topic: Thread topic identifier
        title: Entry title (brief summary)
        body: Full entry content (markdown supported)
        role: Your role (planner/critic/implementer/tester/pm/scribe)
        entry_type: Entry type (Note/Plan/Decision/PR/Closure)

    Returns confirmation message with updated ball status.
    """
```

### 4. `ack(topic: str, title: str = "", body: str = "")`
```python
@mcp.tool
def ack(topic: str, title: str = "", body: str = "") -> str:
    """Acknowledge a thread without flipping the ball.

    Use this when you've read updates but don't need to pass the action.
    The ball stays with the current owner.

    Args:
        topic: Thread topic identifier
        title: Optional acknowledgment title
        body: Optional acknowledgment message

    Returns confirmation message.
    """
```

### 5. `handoff(topic: str, note: str = "", target_agent: str | None = None)`
```python
@mcp.tool
def handoff(topic: str, note: str = "", target_agent: str | None = None) -> str:
    """Hand off the ball; optional explicit target agent.

    If `target_agent` is None, use the default counterpart (maps to
    `commands.handoff`). If provided, explicitly set ball to `target_agent`
    by appending a structured entry.

    Args:
        topic: Thread topic identifier
        note: Optional handoff message explaining context
        target_agent: Agent name to receive the ball (optional)

    Returns confirmation with new ball owner.
    """
```

### 6. `set_status(topic: str, status: str)`
```python
@mcp.tool
def set_status(topic: str, status: str) -> str:
    """Update the status of a thread.

    Common statuses: OPEN, IN_REVIEW, CLOSED, BLOCKED

    Args:
        topic: Thread topic identifier
        status: New status value

    Returns confirmation message.
    """
```

### 7. `reindex()`
```python
@mcp.tool
def reindex() -> str:
    """Generate and return the index content summarizing all threads.

    Creates a summary view organized by:
    - Actionable threads (where you have the ball)
    - Open threads (waiting on others)
    - In Review threads
    - Closed threads excluded by default

    Returns the index content (Markdown) with links and status markers.
    """
```

## Implementation Philosophy

**MVP-First Approach:**
We'll implement in two phases to balance rapid validation against production readiness:

1. **Phase 1A (MVP)**: Get working quickly to validate the MCP concept with Codex
   - 7 core tools with markdown output only
   - Simple environment-based configuration
   - Basic error handling
   - Goal: Prove the concept works for AI agent collaboration

2. **Phase 1B (Production)**: Add robustness after validating core concept
   - JSON output format for programmatic clients
   - Pagination for large result sets
   - Tool namespacing for version compatibility
   - Additional tools and comprehensive testing
   - Goal: Production-ready multi-client MCP server

**Why MVP-First?**
- Validates the core idea before over-engineering
- Faster feedback loop with real Codex usage
- Can iterate based on actual needs vs. assumed requirements
- Reduces risk of building unused features
- All production features remain in scope, just staged appropriately

**Success Criteria for Phase 1A → 1B:**
- ✅ Codex can discover and use watercooler tools naturally
- ✅ AI agents can collaborate via threads without manual CLI commands
- ✅ Tools provide clear, actionable information for LLMs
- ✅ No major architectural limitations discovered

## Implementation Plan

### Phase 1A: MVP (Minimum Viable Product) ✅ COMPLETE

**Goal:** Get working MCP server for Codex validation (est. 2-3 hours)
**Actual delivery:** Completed with all tools and multi-tenant architecture (v0.1.0)

1. **Create Package Structure**
   ```
   src/watercooler_mcp/
   ├── __init__.py
   ├── server.py       # FastMCP server instance + tool wrappers
   └── config.py       # Simple agent identity and directory discovery
   ```

2. **Implement 7 Core Tools** (markdown output only)
   - `list_threads(open_only=None, limit=50, cursor=None, format="markdown")` - Show threads, ball status, NEW markers
   - `read_thread(topic, from_entry=0, limit=100, format="markdown")` - Full thread content
   - `say(topic, title, body, role, entry_type)` - Add entry, flip ball
   - `ack(topic, title, body)` - Acknowledge without ball flip
   - `handoff(topic, note="", target_agent=None)` - Handoff to counterpart or explicit agent
   - `set_status(topic, status)` - Update thread status
   - `reindex()` - Generate index summary (return content)

3. **Simple Configuration** (`config.py`)
   ```python
   import os
   from pathlib import Path

   def get_agent_name() -> str:
       """Get agent identity from WATERCOOLER_AGENT env var."""
       return os.getenv("WATERCOOLER_AGENT", "Agent")

   def get_threads_dir() -> Path:
       """Get threads directory from WATERCOOLER_DIR env or default."""
       dir_str = os.getenv("WATERCOOLER_DIR", ".watercooler")
       return Path(dir_str)
   ```

4. **Core Server Implementation** (`server.py`)
   ```python
   from fastmcp import FastMCP
   from watercooler import commands, fs
   from pathlib import Path
   from .config import get_agent_name, get_threads_dir

   mcp = FastMCP(name="Watercooler Collaboration")

   @mcp.tool
   def list_threads() -> str:
       """List all watercooler threads..."""
       # Implementation wrapping watercooler.commands
       pass

   # ... other 6 tools ...

   if __name__ == "__main__":
       mcp.run()  # Default STDIO transport
   ```

5. **Testing**
   - Add `fastmcp>=2.0` to pyproject.toml dependencies
   - Create MCP entry point: `python3 -m watercooler_mcp.server`
   - Test in `/Users/agent/projects/watercooler-test`
   - Configure Claude Desktop/Codex MCP settings
   - Verify each tool works with test thread

**Phase 1A Scope Boundaries:**
- ✅ Markdown output only (no JSON format parameter)
- ✅ No pagination (return full results)
- ✅ Tool namespacing implemented (`watercooler_v1_*`)
- ✅ Basic error handling (try/catch with messages)
- ✅ Simple env var config only

**Phase 1A Deliverables (Actual):**
- ✅ 9 MCP tools (7 core + 2 diagnostic)
- ✅ 1 MCP resource (watercooler://instructions)
- ✅ Multi-tenant client_id detection
- ✅ Python 3.10+ enforcement
- ✅ Entry point: `python3 -m watercooler_mcp`
- ✅ Comprehensive testing

### Phase 1B: Production Enhancements ✅ COMPLETE

**Goal:** Robust, multi-client production MCP server
**Actual delivery:** Upward directory search, comprehensive docs, Python 3.10+ enforcement (v0.2.0)

**Triggers for Phase 1B:**
- Phase 1A validated successfully with Codex
- Need for programmatic JSON access identified
- Large thread counts require pagination
- Multiple MCP clients need consistent interface

**Phase 1B Deliverables (Actual):**
- ✅ Upward directory search (git root/HOME boundaries)
- ✅ WATERCOOLER_DIR override preserved
- ✅ QUICKSTART.md (comprehensive setup guide)
- ✅ TROUBLESHOOTING.md (comprehensive troubleshooting)
- ✅ Python 3.10+ enforcement across all entry points
- ✅ Improved install script with interpreter detection

**Features Deferred (Evaluate based on usage):**
1. **Dual Format Support** - JSON output format (markdown sufficient for current needs)
2. **Pagination** - Limit/cursor for large result sets
3. **Additional Tools** - search_threads, create_thread, list_updates, break_lock
4. **Enhanced Validation** - Enum helpers, error classes, input sanitization

### Phase 2A: Git Sync Implementation ✅ COMPLETE

**Goal:** Enable cloud-based collaboration via git sync
**Actual delivery:** Full git sync with idempotency, retry logic, comprehensive testing

**Delivered Features:**

1. **GitSyncManager** (`src/watercooler_mcp/git_sync.py`)
   - ✅ Git environment propagation (GIT_SSH_COMMAND for SSH key support)
   - ✅ pull() with --rebase --autostash
   - ✅ commit_and_push() with retry logic on push rejection
   - ✅ with_sync() operation wrapper
   - ✅ Clean abort on rebase conflicts

2. **Entry-ID Idempotency System**
   - ✅ ULID-based Entry-IDs (lexicographically sortable by time)
   - ✅ Format: `{ULID}-{agent_slug}-{topic_slug}`
   - ✅ Commit footers: Watercooler-Entry-ID, Watercooler-Topic, Watercooler-Agent
   - ✅ Prevents duplicate entries during retry

3. **MCP Tool Integration**
   - ✅ watercooler_v1_say() with git sync wrapper
   - ✅ watercooler_v1_read_thread() with pull-before-read
   - ✅ Cloud mode detection via WATERCOOLER_GIT_REPO env var
   - ✅ Backward compatible (local mode unchanged)

4. **Observability** (`src/watercooler_mcp/observability.py`)
   - ✅ Structured JSON logging
   - ✅ Timing context managers
   - ✅ Action logging with duration/outcome tracking

5. **Comprehensive Testing**
   - ✅ 7 unit tests (git_sync operations)
   - ✅ 2 integration tests (sequential appends + concurrent conflict handling)
   - ✅ 3 observability tests
   - ✅ All tests passing

6. **Documentation**
   - ✅ Cloud sync setup in QUICKSTART.md
   - ✅ Git sync troubleshooting in TROUBLESHOOTING.md
   - ✅ CLOUD_SYNC_STRATEGY.md (comprehensive cloud deployment guide)

**Environment Variables (Cloud Mode):**
- `WATERCOOLER_GIT_REPO` - Git repository URL (enables cloud mode)
- `WATERCOOLER_GIT_SSH_KEY` - Optional path to SSH private key
- `WATERCOOLER_GIT_AUTHOR` - Git commit author name
- `WATERCOOLER_GIT_EMAIL` - Git commit author email

### Phase 2B/3: Cloud Deployment (Planned - Not Started)

**Options for future consideration:**

1. **Platform Deployment**
   - fastmcp cloud (native MCP deployment)
   - Cloudflare Workers (custom deployment)
   - Container deployment (Fly.io, Cloud Run, Railway)

2. **Advanced Features**
   - OAuth authentication
   - Multi-tenant isolation
   - Rate limiting and quotas
   - Metrics export (Prometheus/StatsD)

### Phase 3: Deployment

**Option A: fastmcp cloud**
- Native MCP deployment
- Simpler setup
- Managed infrastructure

**Option B: Cloudflare Workers**
- More control
- Custom configuration
- Potentially better performance

**Decision:** Research both, choose based on capabilities

## API Contract and Tool Responses

To make tools robust and future‑proof for multiple clients:

- Namespacing: expose tools as `watercooler_v1_*` (e.g., `watercooler_v1_list_threads`). Ship this in Phase 1A to avoid breaking changes.
- Output format: every read/list tool accepts `format: Literal["markdown","json"] = "markdown"`. Phase 1A supports only "markdown"; `format="json"` is planned for Phase 1B.
- Pagination:
  - `list_threads(open_only: bool | None = None, limit: int = 50, cursor: str | None = None)`
  - `read_thread(topic: str, from_entry: int = 0, limit: int = 100)`
- Enumerations: validate `status ∈ {OPEN, IN_REVIEW, BLOCKED, CLOSED}` and `role ∈ {planner, critic, implementer, tester, pm, scribe}`. Provide helpers `list_statuses()` and `list_roles()`.
- JSON shapes (abbreviated):
  - list_threads → `{ threads: [{ topic, status, ball, updated_at, have_ball, new_for_you }], cursor?: string, truncated?: boolean }`
  - read_thread → `{ topic, status, ball, participants, entries: [{ idx, at, author, role, type, title, body }], next_entry_index?: int, truncated?: boolean }`
- Large output: when truncated, set `truncated: true` and include guidance to paginate.

## Discovery and Configuration

Standardize where threads live and who the agent is:

- Threads directory precedence: `WATERCOOLER_DIR` env → upward search for `.watercooler/` from CWD to git root → fallback `Path.cwd()/'.watercooler'`.
  - Phase 1A: implement `WATERCOOLER_DIR` env and `Path.cwd()/'.watercooler'` fallback; defer upward search to Phase 1B.
- Agent identity precedence: `WATERCOOLER_AGENT` env → MCP client identity (if available) → `git config user.name` → "Agent".
- Counterpart mapping: optional `.watercooler/config.json` allowing `{ "counterpart": "Claude" }` and per‑topic overrides.

## Error Model and Concurrency

Make failures predictable and user‑friendly:

- Error classes (surface as MCP tool errors): `NOT_FOUND` (topic, agent), `INVALID_INPUT` (status/role), `LOCK_TIMEOUT`, `CONFLICT`.
- Locking: default wrapper timeout `lock_timeout_s: int = 2` (consistent with `AdvisoryLock`); clear message on contention with remaining wait guidance.
- Stale locks: detect and label; do not auto‑break. Expose a guarded `break_lock` tool (off by default).
- Input hygiene: sanitize `topic` to a safe slug; reject path traversal; validate `target_agent`.

## Additional Tools (Phase 1.5)

- `search_threads(query: str, status: str | None = None, ball: str | None = None, limit: int = 50, cursor: str | None = None, format: Literal["markdown","json"] = "markdown")`
  - Full‑text topic filter plus optional status/ball filters.
- `create_thread(topic: str, title: str, body: str, role: str = "implementer", status: str = "OPEN")`
  - Bootstrap a new thread with the standard template.
- `list_updates(since_iso: str | None = None, limit: int = 50, format: Literal["markdown","json"] = "markdown")`
  - Digest of entries updated since a timestamp for quick catch‑up.
- `break_lock(topic: str, force: bool = False)`
  - Admin/escape hatch for stale locks; gated by `WATERCOOLER_ALLOW_BREAK_LOCK=1` and prominent warnings.

## Reliability and Observability

- Logging: enable with `WATERCOOLER_DEBUG=1`; redact entry bodies unless debug; include request ids.
- Output safety: default to markdown for human‑readable responses; support JSON for programmatic clients.
- Determinism: sort listings by `updated_at` desc; stable pagination cursors.
- Validation: strict status/role enums; helpful messages listing allowed values.

## Testing Plan (Phase 1)

- Tempdir‑based integration tests using a disposable `.watercooler/`.
- Cases: health/whoami diagnostics; identity resolution; discovery precedence (env + cwd fallback in 1A); list/read markdown; open_only filter; pagination boundaries; invalid inputs; lock contention and timeouts (2s default mapping).
- Avoid network; exercise server wrappers directly where possible.

## Docs & Developer Experience

- Quickstart: `pip install .[mcp]` then `python3 -m watercooler_mcp.server`.
- Package extra: add `fastmcp` under `extras_require = {"mcp": ["fastmcp>=2"]}`.
- Docstrings: concise, LLM‑oriented examples per tool; include pagination/format hints.
- README: short MCP section linking to this plan and docs.

## Cloud Deployment Considerations

- Validate fastmcp cloud vs containerized HTTP (Fly.io, Cloud Run, Railway). Cloudflare Workers may not suit long‑lived Python MCP servers—verify runtime constraints early.
- Secrets & git: document minimal OAuth/token scopes and storage; support read‑only mode.

## Key Design Questions

### 1. Agent Identity
**Question:** How does MCP server know "I am Codex" vs "I am Claude"?

**Options:**
- Environment variable: `WATERCOOLER_AGENT=Codex`
- Configuration file: `.watercooler/config.json`
- Tool parameter: Agent specifies in each call
- Authentication context: From fastmcp cloud user identity

### 2. State Management (Cloud)
**Question:** Where does `.watercooler/` live?

**Options:**
- Server maintains local git clone
- Each request clones fresh (slow)
- Shared volume/storage
- Git-backed cloud storage

### 3. Git Repository
**Question:** Canonical source for threads?

**Requirements:**
- Hosted on GitHub/GitLab
- Team members have access
- Server has credentials
- Push/pull permissions

### 4. Deployment Platform
**Question:** fastmcp cloud or Cloudflare?

**Evaluation criteria:**
- Ease of deployment
- Cost
- Performance
- Control/customization
- Authentication support

## Test Project Status

**Location:** `/Users/agent/projects/watercooler-test/`

**Current state:**
- ✅ Git repository initialized
- ✅ Watercooler-collab installed (editable mode)
- ✅ `.watercooler/` directory created
- ✅ Thread created: `test-conversation`
- ✅ Initial message from agent to Codex
- ⏸️ Waiting for MCP server to enable Codex to respond naturally

**Thread content:**
```markdown
# test-conversation — Thread
Status: OPEN
Ball: agent (agent)
Topic: test-conversation
Created: 2025-10-07T14:56:41Z

---
Entry: agent (agent) 2025-10-07T14:58:04Z
Type: Note
Title: Initial greeting

Hey Codex, this is a test of the watercooler-collab system.
Can you confirm you can see this and respond?
```

## Implementation Timeline

### Completed Phases ✅

**Phase 1A - MVP (v0.1.0)** - COMPLETE
1. ✅ Research fastmcp 2.0 API
2. ✅ Design local architecture
3. ✅ Align on phased implementation strategy
4. ✅ Build Phase 1A MVP
   - Created `src/watercooler_mcp/` package structure
   - Implemented 9 tools (7 core + 2 diagnostic), namespaced as `watercooler_v1_*`
   - Added `config.py` with WATERCOOLER_DIR and WATERCOOLER_AGENT support
   - Implemented health() and whoami() diagnostics
   - Added watercooler://instructions resource
   - Multi-tenant client_id detection
5. ✅ Test MVP with Codex - Validated successfully

**Phase 1B - Production Enhancements (v0.2.0)** - COMPLETE
6. ✅ Implement upward directory search (git root/HOME boundaries)
7. ✅ Comprehensive documentation (QUICKSTART.md, TROUBLESHOOTING.md)
8. ✅ Python 3.10+ enforcement across all entry points
9. ✅ Improved install script with interpreter detection
10. ✅ Comprehensive test suite

**Phase 2A - Git Sync Implementation** - COMPLETE
11. ✅ GitSyncManager implementation with retry logic
12. ✅ Entry-ID idempotency system (ULID-based)
13. ✅ MCP tool integration (say, read_thread with cloud sync)
14. ✅ Observability helpers (structured logging, timing)
15. ✅ Comprehensive testing (10 unit tests, 2 integration tests)
16. ✅ Cloud sync documentation and troubleshooting
17. ✅ All features merged to main

### Next Steps - Evaluate & Decide

**Deferred Phase 1B Features** (evaluate based on usage):
- JSON format support for programmatic clients
- Pagination (limit/cursor) for large result sets
- Additional tools: search_threads, create_thread, list_updates, break_lock
- Enhanced validation and error handling

**Optional Phase 2B/3 - Cloud Deployment:**
- Research platform options (fastmcp cloud, Cloudflare Workers, containers)
- Design cloud architecture (OAuth, multi-tenant, rate limiting)
- Implement deployment automation
- Production monitoring and metrics

### Decision Points

1. **Deferred Features**: Based on real-world usage over next 1-2 weeks, determine which deferred Phase 1B features add value
2. **Cloud Deployment**: Evaluate need for managed cloud deployment vs git-based sync
3. **Advanced Features**: Assess demand for JSON output, pagination, additional tools

---

**Current Status:** Phase 2A Complete - Production Ready for Local & Git-Based Cloud Sync
**Latest Version:** v0.2.0 (Phase 1B) + Phase 2A git sync features
**All PRs Merged:** #1 (MCP server), #2 (git sync), #3 (install script), #4 (auto-create directory)

## Related Files

- `/Users/agent/projects/watercooler-collab/` - Main library
- `/Users/agent/projects/watercooler-test/` - Test project
- `/Users/agent/projects/watercooler-collab/IMPLEMENTATION_PLAN.md` - Original L1-L4 plan
- `/Users/agent/projects/watercooler-collab/docs/integration.md#python-api-reference` - Python API reference
- `/Users/agent/projects/watercooler-collab/docs/integration.md` - Integration guide

## Success Criteria

**Local MCP Server (Phase 1A/1B):**
- ✅ AI agent can discover watercooler tools
- ✅ AI agent can list threads where they have the ball
- ✅ AI agent can read thread content
- ✅ AI agent can respond with say/ack
- ✅ AI agent can handoff to another agent
- ✅ All tools have clear descriptions
- ✅ Comprehensive documentation and troubleshooting
- ✅ Python 3.10+ enforcement
- ✅ Upward directory search

**Git-Based Cloud Sync (Phase 2A):**
- ✅ Git sync works automatically (pull before read, commit+push after write)
- ✅ Concurrent access handled safely (retry logic, rebase)
- ✅ Entry-ID idempotency prevents duplicates
- ✅ SSH key support for private repositories
- ✅ Clean abort on merge conflicts
- ✅ Comprehensive testing (unit + integration)
- ✅ Observability with structured logging

**Managed Cloud Deployment (Phase 2B/3 - Not Started):**
- [ ] Multiple team members can connect via hosted service
- [ ] OAuth authentication works correctly
- [ ] Multi-tenant isolation implemented
- [ ] Performance is acceptable (latency targets met)
- [ ] Deployment is reproducible and automated
- [ ] Monitoring and alerting in place

## Notes

- This is **L5** in the implementation plan - beyond original L1-L4 scope
- Requires coordination with fastmcp 2.0 capabilities
- Cloud deployment is optional but highly valuable for distributed teams
- Local MCP server is valuable even without cloud deployment
