# Watercooler-Cloud Roadmap

**Project Status:** Production Ready
**Current Version:** 0.0.1
**Last Updated:** 2025-10-09

---

## 🎯 Project Evolution

Watercooler-cloud has evolved from a simple CLI library extraction (acpmonkey) to a comprehensive file-based collaboration protocol with AI agent integration.

### Project Phases
1. **L1-L4**: CLI library extraction from acpmonkey ✅
2. **L5**: MCP server implementation (Phases 1A/1B/2A) ✅
3. **Future**: Enhanced features and cloud deployment (as needed)

---

## ✅ Completed Phases

### Phase L1-L4: CLI Library (Complete)
**Goal:** Extract watercooler functionality from acpmonkey as reusable stdlib-only library

**Status:** ✅ COMPLETE - Full feature parity achieved

**Delivered:**
- Core utilities (fs, lock, header, agents, templates, metadata)
- Complete CLI with 12 commands
- Structured entries with 6 roles and 5 types
- Agent registry with counterpart mappings
- Template system with customization
- Advisory file locking with PID tracking
- 56 passing tests

**Documentation:**
- See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) (archived - historical reference)
- All features documented in [docs/](docs/)

---

### Phase 1A: MCP Server MVP (v0.1.0) ✅
**Goal:** Enable AI agents to discover and use watercooler tools automatically

**Status:** ✅ COMPLETE

**Delivered:**
- 9 MCP tools (7 core + 2 diagnostic):
  - `watercooler_v1_health` - Server health check
  - `watercooler_v1_whoami` - Get agent identity
  - `watercooler_v1_list_threads` - List threads with ball status
  - `watercooler_v1_read_thread` - Read full thread content
  - `watercooler_v1_say` - Add entry and flip ball (primary workflow)
  - `watercooler_v1_ack` - Acknowledge without flipping ball
  - `watercooler_v1_handoff` - Hand off to specific agent
  - `watercooler_v1_set_status` - Update thread status
  - `watercooler_v1_reindex` - Generate index summary
- 1 MCP resource: `watercooler://instructions` (comprehensive agent guide)
- Multi-tenant architecture with automatic client detection
- Tool namespacing (`watercooler_v1_*` for version compatibility)
- Entry point: `python3 -m watercooler_mcp`
- FastMCP 2.12.4 integration
- STDIO transport

**Timeline:** Completed 2025-10-08
**Documentation:** [docs/mcp-server.md](docs/mcp-server.md), [L5_MCP_PLAN.md](L5_MCP_PLAN.md)

---

### Phase 1B: Production Enhancements (v0.2.0) ✅
**Goal:** Add robustness and polish for production use

**Status:** ✅ COMPLETE

**Delivered:**
- Upward directory search (finds `.watercooler/` from any subdirectory)
  - Searches from CWD → git root or HOME
  - Respects WATERCOOLER_DIR override
  - Automatic fallback to CWD/.watercooler
- Comprehensive documentation:
  - [QUICKSTART.md](docs/QUICKSTART.md) - Fast onboarding
  - [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - MCP setup issues
  - [CLAUDE_CODE_SETUP.md](docs/CLAUDE_CODE_SETUP.md) - Step-by-step guide
  - [CLAUDE_DESKTOP_SETUP.md](docs/CLAUDE_DESKTOP_SETUP.md) - Desktop app setup
- Python 3.10+ enforcement across all entry points
- Improved install script (`scripts/install-mcp.sh`) with interpreter detection
- Comprehensive test suite

**Timeline:** Completed 2025-10-08
**Documentation:** [L5_MCP_PLAN.md](L5_MCP_PLAN.md)

---

### Phase 2A: Git-Based Cloud Sync ✅
**Goal:** Enable distributed team collaboration via git sync

**Status:** ✅ COMPLETE

**Delivered:**
- **GitSyncManager** (`src/watercooler_mcp/git_sync.py`):
  - Git environment propagation (GIT_SSH_COMMAND for SSH key support)
  - pull() with --rebase --autostash
  - commit_and_push() with retry logic on push rejection
  - with_sync() operation wrapper
  - Clean abort on rebase conflicts
- **Entry-ID Idempotency System:**
  - ULID-based Entry-IDs (lexicographically sortable by time)
  - Format: `{ULID}-{agent_slug}-{topic_slug}`
  - Commit footers: Watercooler-Entry-ID, Watercooler-Topic, Watercooler-Agent
  - Prevents duplicate entries during retry
- **MCP Tool Integration:**
  - watercooler_v1_say() with cloud sync wrapper
  - watercooler_v1_read_thread() with pull-before-read
  - Cloud mode detection via WATERCOOLER_GIT_REPO env var
  - Backward compatible (local mode unchanged)
- **Observability:**
  - Structured JSON logging (`src/watercooler_mcp/observability.py`)
  - Timing context managers
  - Action logging with duration and outcome tracking
- **Comprehensive Testing:**
  - 7 unit tests (git_sync operations)
  - 2 integration tests (sequential appends + concurrent conflict handling)
  - 3 observability tests
  - All tests passing

**Environment Variables (Cloud Mode):**
- `WATERCOOLER_GIT_REPO` - Git repository URL (enables cloud mode)
- `WATERCOOLER_GIT_SSH_KEY` - Optional path to SSH private key
- `WATERCOOLER_GIT_AUTHOR` - Git commit author name
- `WATERCOOLER_GIT_EMAIL` - Git commit author email

**Timeline:** Completed 2025-10-08
**Documentation:** [docs/CLOUD_SYNC_STRATEGY.md](docs/CLOUD_SYNC_STRATEGY.md), [L5_MCP_PLAN.md](L5_MCP_PLAN.md)

---

## 📋 Deferred Features (Evaluate Based on Usage)

These features were planned for Phase 1B but deferred to avoid over-engineering. They can be implemented if real-world usage demonstrates the need.

### JSON Format Support
**Status:** Deferred (markdown sufficient for current needs)

**What it would provide:**
- `format: Literal["markdown","json"]` parameter for all list/read tools
- Structured JSON responses for programmatic clients
- Pagination metadata in responses

**When to implement:**
- Building UI/dashboard that consumes MCP tools
- Integration with other tools requiring structured data
- Programmatic analysis of threads

---

### Pagination
**Status:** Deferred (current thread counts manageable without pagination)

**What it would provide:**
- `list_threads(limit: int = 50, cursor: str | None = None)`
- `read_thread(topic, from_entry: int = 0, limit: int = 100)`
- Stable cursors for consistent iteration

**When to implement:**
- Projects with >50 active threads
- Threads with >100 entries
- Performance issues with large result sets

---

### Additional MCP Tools
**Status:** Deferred (core tools cover main workflows)

**Potential tools:**
- `search_threads(query, status, ball, limit, cursor, format)` - Full-text search
- `create_thread(topic, title, body, role, status)` - Explicit thread creation (say already auto-creates)
- `list_updates(since_iso, limit, format)` - Digest of recent changes
- `break_lock(topic, force)` - Admin tool for stuck locks

**When to implement:**
- Search becomes frequent user need
- Explicit thread creation (without entry) is required
- Need "what's new since X" functionality
- Lock contention issues arise

---

### Enhanced Validation
**Status:** Deferred (basic validation sufficient)

**What it would provide:**
- Enum helpers: `list_statuses()`, `list_roles()`
- Enhanced error classes: NOT_FOUND, INVALID_INPUT, LOCK_TIMEOUT, CONFLICT
- Input sanitization (topic slugs, path traversal prevention)
- Configurable lock timeouts

**When to implement:**
- User-facing errors need better clarity
- Security concerns with user input
- Custom timeout requirements

---

## 🚧 Planned (When Needed)

### Phase 2B/3: Managed Cloud Deployment
**Status:** Not started - Evaluate need based on usage patterns

**Goal:** Hosted MCP server for teams (alternative to git-based sync)

**Potential features:**
- OAuth authentication (GitHub, WorkOS)
- Multi-tenant isolation
- Rate limiting and quotas
- Metrics export (Prometheus/StatsD)
- Web UI for thread browsing
- Platform deployment:
  - Option A: fastmcp cloud (native MCP)
  - Option B: Cloudflare Workers (custom deployment)
  - Option C: Container deployment (Fly.io, Cloud Run, Railway)

**When to implement:**
- Git-based sync proves insufficient for large teams
- Need for hosted service (no git setup required)
- Access control requirements beyond git permissions
- Real-time collaboration needs

**Estimation:** 2-4 weeks for MVP hosted service

---

## 🎯 Current Focus

**Status:** Production ready, monitoring usage patterns

**Priorities:**
1. **Gather usage feedback** - Understand real-world usage of Phase 1A/1B/2A features
2. **Documentation refinement** - Continue improving docs based on user questions
3. **Bug fixes** - Address any issues discovered in production use
4. **Evaluate deferred features** - Determine which (if any) are needed based on evidence

**Decision triggers:**
- **JSON format**: User requests programmatic access or builds UI
- **Pagination**: Performance issues or >50 threads reported
- **Additional tools**: Repeated manual workflows that could be automated
- **Cloud deployment**: Git-based sync proves limiting for teams

---

## 📊 Success Metrics

### Phase 1A/1B (Complete)
- ✅ AI agent can discover watercooler tools
- ✅ AI agent can list threads where they have the ball
- ✅ AI agent can read thread content
- ✅ AI agent can respond with say/ack
- ✅ AI agent can handoff to another agent
- ✅ All tools have clear descriptions
- ✅ Comprehensive documentation and troubleshooting
- ✅ Python 3.10+ enforcement
- ✅ Upward directory search

### Phase 2A (Complete)
- ✅ Git sync works automatically (pull before read, commit+push after write)
- ✅ Concurrent access handled safely (retry logic, rebase)
- ✅ Entry-ID idempotency prevents duplicates
- ✅ SSH key support for private repositories
- ✅ Clean abort on merge conflicts
- ✅ Comprehensive testing (unit + integration)
- ✅ Observability with structured logging

### Current (Ongoing)
- Monitor adoption and usage patterns
- Track feature requests and pain points
- Identify documentation gaps
- Measure performance (latency, conflict rates)

---

## 📝 Version History

| Version | Release Date | Phase | Key Features |
|---------|-------------|-------|--------------|
| 0.0.1   | -           | L1-L4 | CLI library with full acpmonkey parity |
| 0.1.0   | 2025-10-08  | 1A    | MCP server MVP (9 tools + 1 resource) |
| 0.2.0   | 2025-10-08  | 1B    | Upward search, docs, Python 3.10+ |
| -       | 2025-10-08  | 2A    | Git-based cloud sync |

---

## 🤝 Contributing to Roadmap

Have feedback on priorities? Suggestions for new features?

1. **Open an issue**: https://github.com/mostlyharmless-ai/watercooler-cloud/issues
2. **Start a discussion**: Create a watercooler thread in your project
3. **Submit a PR**: Improvements to roadmap welcome

---

*Last updated: 2025-10-09*
