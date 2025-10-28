# Cloud Sync Strategy for Watercooler MCP

This document explains the **strategic decisions** behind watercooler's cloud sync architecture and why we chose git-based async collaboration over real-time alternatives.

**For user setup instructions**, see [CLOUD_SYNC_GUIDE.md](./CLOUD_SYNC_GUIDE.md).

**For technical implementation details**, see [CLOUD_SYNC_ARCHITECTURE.md](./CLOUD_SYNC_ARCHITECTURE.md).

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [The MCP Constraint](#the-mcp-constraint)
- [Why Git-Based Sync](#why-git-based-sync)
- [Why Not Real-Time](#why-not-real-time)
- [Deployment Strategy](#deployment-strategy)
- [Scalability Recommendations](#scalability-recommendations)
- [Migration Path](#migration-path)

---

## Executive Summary

**Key Constraint:** The Model Context Protocol (MCP) does **not support custom push notifications** to clients (Claude, Codex). This means we cannot implement real-time chat-like collaboration.

**Our Solution:** Use a **pull-based async collaboration model** with git as the source of truth.

**Best Use Cases:**
- ✅ Async collaboration (planning, code review, handoffs)
- ✅ Multi-user project coordination
- ✅ Persistent conversation threads
- ❌ Not ideal for rapid-fire brainstorming (use chat instead)

**Key Benefits:**
- **Simple**: Git is familiar and well-understood
- **Reliable**: Proven conflict resolution and durability
- **Flexible**: Works with GitHub, GitLab, self-hosted git
- **Scalable**: Handles 10-20+ concurrent agents without issues
- **Auditable**: Full history in git log

---

## The MCP Constraint

### What MCP Protocol Supports

The Model Context Protocol defines a **strict set of notification types** that servers can push to clients:

- `notifications/tools/list_changed` - When tools are added/removed
- `notifications/resources/list_changed` - When resources change
- `notifications/prompts/list_changed` - When prompts change
- `notifications/progress` - Progress updates during tool execution
- `notifications/message` - Log messages

### What's Missing

**No mechanism for custom notifications** such as:
- "Thread X has a new entry"
- "Agent Y replied to your message"
- "Status changed on thread Z"
- Any custom collaboration events

### Impact on Architecture

This architectural constraint means:

1. **No real-time push**: We cannot notify Claude that "Codex just replied"
2. **Pull-based updates**: Clients must call `read_thread()` to check for updates
3. **User-initiated refresh**: Updates only appear when user asks for them
4. **Async collaboration model**: Not suitable for rapid back-and-forth

This fundamentally shapes our entire cloud sync strategy.

---

## Why Git-Based Sync

### Decision Rationale

Given the MCP constraint of pull-based updates, we chose **git as the source of truth** because:

#### 1. **Proven Conflict Resolution**
- Git's merge/rebase algorithms handle concurrent edits
- Append-only operations (our primary use case) rarely conflict
- When conflicts do occur, git provides clear resolution strategies

#### 2. **Familiar Tooling**
- Every developer knows git
- Easy to inspect, debug, and understand
- Works with existing workflows (GitHub/GitLab/Bitbucket)

#### 3. **Auditability**
- Full history in git log
- Who changed what and when
- Easy rollback if needed

#### 4. **Durability**
- Git is rock-solid for data persistence
- Remote backup included by design
- No proprietary storage format

#### 5. **Flexibility**
- Works with any git hosting (GitHub, GitLab, self-hosted)
- Can switch providers without changing architecture
- Optional Cloudflare caching layer for performance

#### 6. **"Just Markdown Files"**
- Preserves our core philosophy
- Human-readable without special tools
- Easy to migrate data in/out

### Trade-offs Accepted

We accept these trade-offs:

- **Latency**: 200-500ms reads, 500ms-1s writes (vs <100ms with database)
- **Not real-time**: Updates require explicit refresh
- **Git overhead**: Clone/pull/push operations add complexity

**Why this is acceptable:**
- Watercooler is designed for **persistent threads**, not rapid chat
- 1-second latency is fine for "check for updates" workflows
- Git's benefits (conflict resolution, familiarity, auditability) outweigh the overhead

---

## Why Not Real-Time

### Options Considered and Rejected

#### ❌ WebSocket/SSE Push Notifications

**Problem:** MCP protocol doesn't support custom notifications

- We can only push predefined MCP events (tool changes, progress, logs)
- Cannot push "thread updated" or custom collaboration events
- Would require building custom clients outside MCP ecosystem

**Verdict:** Not possible within MCP constraints

---

#### ❌ Polling with Interval

**Problem:** Inefficient and poor UX

- Clients would need to poll `list_threads()` every N seconds
- Burns tokens and API calls
- Still not "real-time" (N-second delay)
- User has no control over when updates appear

**Verdict:** Worse than explicit user-initiated refresh

---

#### ❌ Custom MCP Client

**Problem:** Defeats the purpose of MCP

- Would need to fork Claude Desktop, Claude Code, Codex
- Breaks compatibility with standard MCP ecosystem
- Massive maintenance burden
- Users lose upstream updates

**Verdict:** Not practical for open-source project

---

#### ❌ Cloudflare Durable Objects + WebSockets

**Problem:** No integration path with current MCP clients

- Durable Objects are great for custom UIs
- But Claude/Codex can't connect to custom WebSocket endpoints
- Would only work with custom clients (see above)

**Verdict:** Interesting for future custom UI, but doesn't solve MCP integration

---

### What We Chose Instead

**User-initiated pull-based refresh** with git as source of truth:

```
User: "Claude, what's new on feature-x?"
  ↓
Claude calls read_thread("feature-x")
  ↓
MCP server does git pull
  ↓
Returns latest content (including updates from other agents)
```

**Why this works:**
- User controls when to check for updates
- Clear, predictable behavior
- Works within MCP constraints
- Acceptable latency for async collaboration

---

## Deployment Strategy

### Recommended Architecture

```
┌──────────────────────────────────────┐
│     GitHub/GitLab Repository         │
│         (Source of Truth)            │
└────────┬──────────────┬──────────────┘
         │              │
    ┌────▼──────┐  ┌───▼──────┐
    │  MCP A    │  │  MCP B   │
    │ (Claude)  │  │ (Codex)  │
    └───────────┘  └──────────┘
```

**How it works:**
1. Each MCP server clones the shared git repository
2. **Reads**: `git pull` before returning thread content
3. **Writes**: Append entry, `git commit`, `git push`
4. **Conflicts**: Retry with fresh pull (3 attempts)

**Latency:**
- Read: ~200-500ms (git pull + file read)
- Write: ~500ms-1s (pull + append + commit + push)

See [CLOUD_SYNC_ARCHITECTURE.md](./CLOUD_SYNC_ARCHITECTURE.md) for implementation details.

---

### Optional: Cloudflare Edge Acceleration

For global teams, deploy Cloudflare Workers:

```
┌─────────────────────────────────────┐
│  Cloudflare Worker (Global Edge)   │
│  - Proxies to GitHub API            │
│  - Optional R2 caching              │
└──────────┬──────────────────────────┘
           │
    ┌──────▼──────┐
    │   GitHub    │
    └─────────────┘
```

**Benefits:**
- Lower latency for distributed teams
- R2 caching for faster reads
- Serverless (no infrastructure to manage)

**Trade-offs:**
- Still git-based (same fundamental latency)
- GitHub API rate limits
- Added complexity

See [CLOUD_SYNC_ARCHITECTURE.md](./CLOUD_SYNC_ARCHITECTURE.md#cloudflare-integration-options) for details.

---

## Scalability Recommendations

### Small Teams (2-5 agents)
**✅ Recommended:** Git-based sync with GitHub/GitLab

- Simple, reliable, no special infrastructure
- Manual git sync if needed
- Docker containers or bare metal

**Expected performance:**
- No conflicts
- Sub-second latency
- Handles concurrent writes gracefully

---

### Medium Teams (5-20 agents)
**✅ Recommended:** Git-based sync + optional Cloudflare Workers

- Git as source of truth
- Optional R2 caching for faster reads
- Consider OAuth for multi-tenant setup

**Expected performance:**
- Rare conflicts (handled automatically)
- ~500ms latency
- May need monitoring for push failures

---

### Large Teams (20+ agents)
**⚠️ Consider alternatives:** Cloudflare D1 or PostgreSQL

- Git becomes bottleneck with 20+ concurrent writers
- Consider sharding threads by project/team
- May need database for better concurrency

**Options:**
- **Cloudflare D1**: SQLite at edge, still pull-based
- **PostgreSQL**: Traditional database, more operational overhead
- **Hybrid**: Git for audit trail, database for active threads

**Trade-offs:**
- Lose "just markdown files" philosophy
- More complex deployment
- Better performance and concurrency

---

## Migration Path

### Phase 1: Local Only ✅ (Current)
- Works great for single-user
- Manual git sync if needed
- No cloud infrastructure required

**Status:** Implemented and working

---

### Phase 2A: Optional Git Sync ✅ (Completed)
- Detect mode automatically: `WATERCOOLER_GIT_REPO` present = cloud mode
- Backward compatible (local mode unchanged)
- Pull before reads, commit+push after writes

**Status:** Implemented in Phase 2A

**Code:**
```python
sync = get_git_sync_manager()
if sync:
    # Cloud mode
    sync.with_sync(operation, message)
else:
    # Local mode
    operation()
```

---

### Phase 2B: Cloudflare Workers (Optional)
- Deploy to Cloudflare for global edge
- Still uses GitHub as backend
- Optional R2 caching

**Status:** Planned, not yet implemented

**When to implement:**
- When users report latency issues
- When global teams need lower latency
- When usage justifies the complexity

---

### Phase 2C: OAuth Integration (Future)
- GitHub/GitLab OAuth for authentication
- Per-user thread repositories
- Multi-tenant support

**Status:** Deferred until real-world usage demonstrates need

**When to implement:**
- When offering hosted watercooler service
- When teams need per-user isolation
- When usage justifies OAuth complexity

---

## Expected User Experience

### Typical Workflow

**User A (with Claude):**
```
User: "Claude, start a thread about refactoring auth"

Claude: [calls say()]
"✅ Thread 'auth-refactor' created
Ball: Codex (your teammate)
Status: OPEN"

--- 5 minutes later ---

User: "What's the latest on auth-refactor?"

Claude: [calls read_thread(), git pull happens]
"Codex replied 5 minutes ago:
'Analyzed current auth flow. Found 3 security issues.
Recommend switching to OAuth2. Shall I create a plan?'"

User: "Tell Codex yes, create the plan"

Claude: [calls say()]
"✅ Message sent to Codex"
```

**User B (with Codex):**
```
User: "Codex, any updates on auth-refactor?"

Codex: [calls read_thread(), git pull happens]
"Claude approved. Starting OAuth2 migration plan..."

[Codex works for 2 minutes]

Codex: [calls say()]
"Posted migration plan with 5 phases. Ball back to Claude."
```

### Latency Expectations

- **Initial question:** Instant (no network)
- **Read thread:** 200-500ms (git pull)
- **Post entry:** 500ms-1s (git pull + push)
- **See updates:** Only when explicitly checking

**Not real-time**, but suitable for:
- Project planning
- Code review threads
- Task handoffs
- Design discussions

**Not suitable for:**
- Live debugging sessions
- Rapid brainstorming
- Real-time pair programming

For those use cases, use chat directly instead of watercooler threads.

---

## Conclusion

**Our cloud sync strategy:**

1. **Storage:** Git (GitHub/GitLab) as source of truth
2. **Sync:** Pull before reads, commit+push after writes
3. **Hosting:** Containers or optional Cloudflare Workers
4. **Caching:** Optional R2 for faster reads
5. **Collaboration Model:** Async (not real-time)
6. **Latency:** 500ms-1s per operation
7. **Conflicts:** Git handles automatically (append-only)

**This works within MCP constraints and provides solid async collaboration for distributed teams.**

The key insight: **MCP's pull-based architecture isn't a limitation—it's a feature.** By embracing async collaboration, we get:
- Clearer communication (thoughtful replies vs rapid-fire)
- Full audit trail (git log)
- Familiar tooling (git)
- Proven reliability (git's 20+ years of conflict resolution)

---

## Related Documentation

- **[Cloud Sync Guide](./CLOUD_SYNC_GUIDE.md)** - User-facing setup instructions (5-minute quickstart)
- **[Cloud Sync Architecture](./CLOUD_SYNC_ARCHITECTURE.md)** - Technical implementation reference
- **[Environment Variables](./ENVIRONMENT_VARS.md)** - Complete configuration reference
- **[MCP Server Guide](./mcp-server.md)** - MCP tool documentation
- **[Troubleshooting](./TROUBLESHOOTING.md)** - Common issues and solutions
