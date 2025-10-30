# Watercooler Use Cases

This guide provides practical use cases demonstrating when and how to use watercooler-cloud effectively in your development workflows.

> Examples may reference `$THREADS_DIR/`. Substitute your actual threads directory (for example, `../<repo>-threads`).

```bash
THREADS_DIR="../<repo>-threads"
```

## Table of Contents

- [Multi-Agent Collaboration](#multi-agent-collaboration)
- [Extended Context for LLM Sessions](#extended-context-for-llm-sessions)
- [Handoff Workflows](#handoff-workflows)
- [Async Team Collaboration](#async-team-collaboration)
- [Decision Tracking](#decision-tracking)
- [PR Review Workflow](#pr-review-workflow)

---

## Multi-Agent Collaboration

### Problem

Modern development often involves multiple AI agents with different capabilities:
- Code generation agents (Codex, Copilot)
- Reasoning agents (Claude, GPT)
- Specialized agents (security scanners, test generators)
- Human reviewers and project managers

Without coordination, agents:
- Duplicate work or conflict with each other
- Lack context about what others have done
- Can't track who owns the next action
- Have no structured way to hand off tasks

### Solution

Watercooler provides role-based agent coordination with explicit ball ownership:

1. **Role Specialization**: Assign each agent a specific role (planner, implementer, critic, tester, pm, scribe)
2. **Ball Tracking**: Clear ownership of who has the next action
3. **Structured Handoffs**: Explicit transitions between agents using `say`, `ack`, or `handoff`
4. **Persistent Context**: All entries logged in versioned markdown files

### Example: Multi-Agent Code Review Workflow

```bash
# Step 1: Planner (Claude) creates architecture proposal
watercooler init-thread api-redesign \
  --title "API Redesign for v2.0" \
  --owner Team \
  --participants "Claude, Codex, agent" \
  --ball codex

watercooler say api-redesign \
  --agent Claude \
  --role planner \
  --title "Architecture Proposal" \
  --type Plan \
  --body @design-proposal.md
# Ball auto-flips to: codex

# Step 2: Implementer (Codex) implements the design
watercooler say api-redesign \
  --agent Codex \
  --role implementer \
  --title "Implementation Complete" \
  --type Note \
  --body "Implemented REST endpoints. Tests at 85% coverage. See commit abc123."
# Ball auto-flips to: claude

# Step 3: Critic (Claude) reviews implementation
watercooler say api-redesign \
  --agent Claude \
  --role critic \
  --title "Security Review" \
  --type Decision \
  --body "Auth looks good. Request: add rate limiting to /api/users endpoint."
# Ball auto-flips to: codex

# Step 4: Implementer addresses feedback
watercooler say api-redesign \
  --agent Codex \
  --role implementer \
  --title "Rate Limiting Added" \
  --body "Added rate limiting middleware. Updated tests."
# Ball auto-flips to: claude

# Step 5: Critic approves
watercooler say api-redesign \
  --agent Claude \
  --role critic \
  --title "Approved" \
  --type Decision \
  --body "All concerns addressed. Ready for merge." \
  --ball team
# Explicitly set ball to: team (human review)

# Step 6: PM (Human) closes thread
watercooler say api-redesign \
  --agent Team \
  --role pm \
  --title "Merged to main" \
  --type Closure \
  --body "PR #123 merged. Deployed to staging." \
  --status closed
```

**Resulting Thread Structure:**
```markdown
# api-redesign — Thread
Status: closed
Ball: team
...

---
Entry: Claude (agent) 2025-10-07T10:00:00Z
Role: planner
Type: Plan
Title: Architecture Proposal

[Design proposal content...]

---
Entry: Codex (agent) 2025-10-07T11:30:00Z
Role: implementer
Type: Note
Title: Implementation Complete

Implemented REST endpoints. Tests at 85% coverage. See commit abc123.

---
Entry: Claude (agent) 2025-10-07T12:15:00Z
Role: critic
Type: Decision
Title: Security Review

Auth looks good. Request: add rate limiting to /api/users endpoint.

---
[Additional entries...]
```

### Best Practices

1. **Define Agent Roles Early**: Assign roles based on agent capabilities
   - Claude: planner, critic (reasoning-heavy)
   - Codex: implementer, tester (code-focused)
   - Humans: pm, scribe (coordination)

2. **Use Counterpart Mappings**: Configure agent registry for auto-flip
   ```json
   {
     "agents": {
       "claude": {"counterpart": "codex"},
       "codex": {"counterpart": "claude"},
       "team": {"counterpart": "codex"}
     }
   }
   ```

3. **Match Entry Types to Phase**:
   - `Plan`: Initial design and proposals
   - `Note`: Implementation updates and progress
   - `Decision`: Reviews and approvals
   - `PR`: Pull request coordination
   - `Closure`: Final summary

4. **Explicit vs Auto-Flip**:
   - Use `say` for standard back-and-forth (auto-flips to counterpart)
   - Use `handoff` when explicitly passing to specific agent
   - Use `ack` to respond without changing ball owner

5. **Check Ball Status**: Run `watercooler list` to see NEW markers
   ```bash
   $ watercooler list
   2025-10-07T12:15:00Z  open  codex  NEW  API Redesign  api-redesign.md
   ```
   NEW marker indicates ball is with codex but last entry was from claude

---

## Extended Context for LLM Sessions

### Problem

LLM conversations face context limitations:
- **Context window limits**: Even large models (200K tokens) run out eventually
- **Session boundaries**: Starting fresh loses all previous context
- **Expensive re-explanation**: Summarizing past work wastes tokens
- **Lost decisions**: No record of why choices were made

When working on long-running projects, repeatedly explaining background context is inefficient and error-prone.

### Solution

Watercooler threads provide **persistent context** that survives session boundaries:

1. **Write-once, reference-forever**: Decisions and context logged permanently
2. **Structured history**: Chronological entries with metadata for easy scanning
3. **Git-versioned**: Context travels with the codebase
4. **Searchable**: `watercooler search` finds relevant past discussions

Instead of re-explaining context, LLMs can read thread files directly.

### Example: Resume After Context Exhaustion

**Day 1 - Initial Design Session:**
```bash
# Start architecture discussion
watercooler init-thread database-migration \
  --title "PostgreSQL to DynamoDB Migration" \
  --ball claude

# Claude analyzes and proposes approach
watercooler say database-migration \
  --agent Claude \
  --role planner \
  --title "Migration Strategy" \
  --type Plan \
  --body @migration-plan.md
# (Long detailed plan: 5000 tokens)

# Team reviews and decides
watercooler say database-migration \
  --agent Team \
  --role pm \
  --title "Approach Approved" \
  --type Decision \
  --body "Use dual-write pattern during transition. Target: 2 week migration window."

# Context window getting full (~180K tokens)...
```

**Day 2 - Resume Work:**
```bash
# New session - instead of re-explaining everything:
# Just reference the thread!

# Human prompt to Claude:
"Please read $THREADS_DIR/database-migration.md and continue implementation.
Focus on the dual-write pattern we decided on."

# Claude reads the thread, sees:
# - Original migration plan (Plan entry)
# - Approved approach (Decision entry)
# - Ball currently with: claude
# - All context preserved!

watercooler say database-migration \
  --agent Claude \
  --role implementer \
  --title "Dual-Write Layer Complete" \
  --body "Implemented AbstractRepository with DynamoDB and PostgreSQL backends. See commit def456."
```

**Day 7 - Week Later:**
```bash
# Search for context
watercooler search "dual-write"
# Returns: database-migration.md:42: Use dual-write pattern during transition

# Read specific thread
cat $THREADS_DIR/database-migration.md
# Entire history available - no context lost!

# Continue work exactly where we left off
watercooler say database-migration \
  --agent Claude \
  --role tester \
  --title "Migration Testing Complete" \
  --type Note \
  --body "Verified data consistency across 1M records. Ready for production cutover."
```

### Pattern: Context File as LLM Input

**Instead of this** (wasteful):
```
Human: "We're migrating from PostgreSQL to DynamoDB. Last week we discussed
using a dual-write pattern. Claude suggested implementing an abstract repository.
We approved the approach and targeted 2 weeks. Now we need to implement the
migration script. The key concerns were data consistency and rollback safety.
We decided to use a feature flag for gradual rollout. The team includes..."
(1000+ tokens just re-explaining)
```

**Do this** (efficient):
```
Human: "Read $THREADS_DIR/database-migration.md for full context.
Now implement the migration script focusing on rollback safety."

Claude: *reads 50 structured entries in thread file*
"Based on the Decision entry from 2025-10-01, I'll implement the rollback
mechanism using the versioning strategy you approved..."
(No wasted tokens, full context preserved)
```

### Best Practices

1. **Reference Threads in Prompts**:
   ```
   "Read $THREADS_DIR/feature-auth.md then implement OAuth2 flow"
   ```

2. **Use Search to Find Relevant Threads**:
   ```bash
   watercooler search "authentication"
   # Finds all threads discussing auth
   ```

3. **Structured Entries Make Scanning Easy**:
   - LLMs can quickly find Decision and Plan entries
   - Metadata (Role, Type, Title) helps locate relevant context
   - Chronological order preserves evolution of thinking

4. **Link Threads to Code**:
   ```markdown
   Entry: Claude (agent) 2025-10-07T14:00:00Z
   Type: Note

   Implemented in: src/auth/oauth.py:145-230
   Related threads: $THREADS_DIR/security-review.md
   ```

5. **Update Threads as Context Evolves**:
   - Don't just stop using a thread - close it properly
   - Use Closure entry type to summarize final state
   - Link to follow-up threads if work continues elsewhere

6. **Combine with Other Context Tools**:
   - Watercooler: High-level decisions and coordination
   - Code comments: Implementation details
   - ADRs: Architectural decisions (can reference watercooler threads)
   - Git commits: Link to relevant threads in commit messages

---

## Handoff Workflows

### Problem

Development work involves many transitions:
- Developer finishes feature → reviewer needs to check it
- Human delegates task → AI agent implements it
- One agent completes analysis → different agent acts on findings
- Work blocked on dependency → hand off to unblock

Without explicit handoffs:
- Unclear who owns next action
- Work sits idle waiting for attention
- Context lost during transitions
- No audit trail of responsibility

### Solution

Watercooler provides three handoff mechanisms with different semantics:

1. **`say`** - Quick update with auto-flip to counterpart
2. **`handoff`** - Explicit handoff with target specified
3. **`ack`** - Acknowledge without changing owner

### Example: Developer-to-Reviewer Handoff

```bash
# Developer completes feature
watercooler say feature-search \
  --agent Codex \
  --role implementer \
  --title "Search Implementation Complete" \
  --body "Full-text search with fuzzy matching. PR #456 ready for review."
# Ball auto-flips to counterpart (claude)

# Reviewer acknowledges (doesn't flip ball back)
watercooler ack feature-search \
  --agent Claude \
  --role critic \
  --title "Review In Progress"
# Ball stays with: claude (reviewer retains ownership)

# Reviewer completes review
watercooler say feature-search \
  --agent Claude \
  --role critic \
  --title "Requested Changes" \
  --type Note \
  --body "1. Add input validation, 2. Improve error messages, 3. Add tests for edge cases"
# Ball auto-flips back to: codex

# Developer addresses feedback
watercooler say feature-search \
  --agent Codex \
  --role implementer \
  --title "Feedback Addressed" \
  --body "All three items fixed. Updated PR."
# Ball auto-flips to: claude

# Reviewer approves and hands off to PM
watercooler handoff feature-search \
  --agent Claude \
  --role pm \
  --note "Approved - ready to merge"
# Ball explicitly set to: team (not counterpart)
```

### Example: Human-to-Agent Delegation

```bash
# Human delegates research task to agent
watercooler init-thread performance-analysis \
  --title "Analyze Query Performance" \
  --ball claude

watercooler say performance-analysis \
  --agent Team \
  --role pm \
  --title "Research Request" \
  --body "Queries taking 2+ seconds. Investigate slow queries in logs/slow-query.log and propose optimizations."
# Ball auto-flips to: claude

# Agent performs analysis
watercooler say performance-analysis \
  --agent Claude \
  --role critic \
  --title "Analysis Complete" \
  --type Decision \
  --body "Found 3 missing indexes. Proposed indexes: users.email, posts.created_at, comments.post_id. Est. 80% speedup."
# Ball auto-flips to: team

# Human approves and delegates implementation
watercooler handoff performance-analysis \
  --agent Team \
  --note "Approved - Codex, please implement the indexes"
# Ball set to: codex

# Implementation agent executes
watercooler say performance-analysis \
  --agent Codex \
  --role implementer \
  --title "Indexes Added" \
  --body "Migration created: db/migrations/002_add_indexes.sql. Applied to staging."
# Ball auto-flips to: team
```

### Example: Agent-to-Agent Transition

```bash
# Planning agent designs feature
watercooler say api-versioning \
  --agent Claude \
  --role planner \
  --title "Versioning Strategy" \
  --type Plan \
  --body "Use URL-based versioning (/v1/, /v2/). Maintain v1 for 6 months after v2 release."
# Ball auto-flips to: codex (counterpart)

# Implementation agent builds it
watercooler say api-versioning \
  --agent Codex \
  --role implementer \
  --title "V2 Endpoints Created" \
  --body "Added /v2/ routes with backward compatibility layer."
# Ball auto-flips to: claude

# Review agent checks quality
watercooler say api-versioning \
  --agent Claude \
  --role critic \
  --title "Code Review" \
  --type Decision \
  --body "Looks good. One request: add deprecation warnings to v1 endpoints."
# Ball auto-flips to: codex

# Back to implementation
watercooler say api-versioning \
  --agent Codex \
  --role implementer \
  --title "Deprecation Warnings Added" \
  --body "Added X-API-Deprecated header to all v1 responses."
# Ball auto-flips to: claude
```

### Best Practices

1. **Choose the Right Handoff Mechanism**:
   - `say`: Standard work update (auto-flips to counterpart)
   - `handoff`: Explicit pass to specific person/agent
   - `ack`: Acknowledge without taking ownership

2. **Configure Counterpart Mappings**:
   ```json
   {
     "agents": {
       "claude": {"counterpart": "codex"},
       "codex": {"counterpart": "claude"},
       "team": {"counterpart": "claude"}
     }
   }
   ```
   Enables automatic ball-flip without manual --ball arguments

3. **Include Context in Handoff**:
   ```bash
   watercooler handoff feature-auth \
     --note "Blocked on security review. Need approval for OAuth scopes."
   ```
   Don't just flip the ball - explain why

4. **Use NEW Markers for Attention**:
   ```bash
   $ watercooler list
   2025-10-07T15:30:00Z  open  team  NEW  Performance Analysis  performance-analysis.md
   ```
   NEW marker shows ball-holder differs from last entry author (needs attention!)

5. **Combine with Status Updates**:
   ```bash
   watercooler say feature-auth \
     --agent Claude \
     --title "Security Review Complete" \
     --body "Approved" \
     --status in-review  # Update status and flip ball
   ```

6. **Track Handoff Chains**:
   Read thread file to see full handoff history:
   ```bash
   grep "^Entry:" $THREADS_DIR/feature-auth.md
   # Entry: Team (agent) 2025-10-07T10:00:00Z
   # Entry: Claude (agent) 2025-10-07T11:00:00Z
   # Entry: Codex (agent) 2025-10-07T12:00:00Z
   # Entry: Claude (agent) 2025-10-07T13:00:00Z
   ```

---

## Async Team Collaboration

### Problem

Distributed teams face coordination challenges:
- Different time zones (East Coast finishes, West Coast starts)
- Asynchronous work (no overlap for real-time meetings)
- Context loss (what happened while I was offline?)
- Unclear ownership (who's working on what?)

Email and chat tools lack structure for technical coordination. Code comments and commit messages scatter context.

### Solution

Watercooler enables **async-first collaboration** through git-versioned threads:

1. **Git-based sharing**: Threads committed and pushed like code
2. **Append-only protocol**: Safe concurrent work (union merge)
3. **Ball tracking**: Clear ownership at all times
4. **NEW markers**: Highlights threads needing attention
5. **Structured entries**: Easy to scan for relevant updates

### Example: 24-Hour Development Cycle

**8am ET (East Coast - Morning)**
```bash
# East Coast dev starts work
git pull  # Get latest from West Coast

# Check for NEW threads (ball assigned to me)
watercooler list
# 2025-10-07T01:00:00Z  open  alice  NEW  Bug #789  bug-789.md

# Read thread to see West Coast progress
cat $THREADS_DIR/bug-789.md
# Last entry: Bob (West Coast) identified root cause at 1am ET

# Continue work
watercooler say bug-789 \
  --agent Alice \
  --role implementer \
  --title "Fix Applied" \
  --body "Fixed off-by-one error in pagination. Added regression test."

# Commit and push (ball flips to Bob - counterpart)
git add $THREADS_DIR/bug-789.md
git commit -m "watercooler: bug-789 fix applied"
git push
```

**1pm ET / 10am PT (West Coast - Morning)**
```bash
# West Coast dev starts work (5 hours later)
git pull  # Get East Coast updates

# Check threads
watercooler list
# 2025-10-07T13:00:00Z  open  bob  NEW  Bug #789  bug-789.md

# Read Alice's fix
cat $THREADS_DIR/bug-789.md
# Last entry: Alice applied fix + test

# Verify and approve
watercooler say bug-789 \
  --agent Bob \
  --role tester \
  --title "Verified on Staging" \
  --body "Tested pagination with 10K records. Fix works correctly."

# Hand off to PM for deployment
watercooler handoff bug-789 \
  --note "Tested and approved - ready for production"

git add $THREADS_DIR/bug-789.md
git commit -m "watercooler: bug-789 verified"
git push
```

**2pm ET / 11am PT (Overlap Hour)**
```bash
# PM (in overlap window) deploys
watercooler say bug-789 \
  --agent Team \
  --role pm \
  --title "Deployed to Production" \
  --type Closure \
  --body "Deployed at 2025-10-07T14:00:00Z. Monitoring for 24h." \
  --status closed

git add $THREADS_DIR/bug-789.md
git commit -m "watercooler: bug-789 deployed"
git push
```

### Example: Concurrent Work on Same Thread

**Developer A (East Coast) - Working on feature**
```bash
watercooler say feature-search \
  --agent Alice \
  --role implementer \
  --title "Backend API Complete" \
  --body "Search API implemented. Returns JSON. Endpoint: /api/search"

git add $THREADS_DIR/feature-search.md
git commit -m "watercooler: backend API done"
git push
```

**Developer B (West Coast) - Working in parallel (before pulling A's changes)**
```bash
watercooler say feature-search \
  --agent Bob \
  --role implementer \
  --title "Frontend UI Complete" \
  --body "Search box with autocomplete. Debounced at 300ms."

git add $THREADS_DIR/feature-search.md
git commit -m "watercooler: frontend UI done"
git pull  # Merge happens here!
```

**Git Merge (Automatic!)**
```bash
# Git uses merge=union for $THREADS_DIR/*.md files
# Both entries preserved automatically:

Auto-merging $THREADS_DIR/feature-search.md
Merge made by the 'ort' strategy.
```

**Resulting Thread (Both Entries Present)**
```markdown
---
Entry: Alice (alice) 2025-10-07T08:00:00Z
Role: implementer
Title: Backend API Complete

Search API implemented. Returns JSON. Endpoint: /api/search

---
Entry: Bob (bob) 2025-10-07T10:30:00Z
Role: implementer
Title: Frontend UI Complete

Search box with autocomplete. Debounced at 300ms.
```

No manual conflict resolution needed! Both entries preserved in chronological order.

### Best Practices

1. **Pull Before Starting Work**:
   ```bash
   git pull && watercooler list
   ```
   Check for NEW threads needing your attention

2. **Push Frequently**:
   ```bash
   # After each significant watercooler entry:
   git add $THREADS_DIR/*.md
   git commit -m "watercooler: [topic] [brief summary]"
   git push
   ```

3. **Use NEW Markers**:
   ```bash
   $ watercooler list
   2025-10-07T13:00:00Z  open  alice  NEW  Feature Search  feature-search.md
   ```
   NEW means: ball is with alice, but last entry wasn't from alice (needs attention!)

4. **Configure Git Merge Strategies**:
   ```bash
   # Required setup (one-time):
   git config merge.ours.driver true
   git config core.hooksPath .githooks
   ```
   See [.github/WATERCOOLER_SETUP.md](../.github/WATERCOOLER_SETUP.md)

5. **Regenerate Index After Merge**:
   ```bash
   git pull
   watercooler reindex  # Update index.md with latest threads
   git add $THREADS_DIR/index.md
   git commit -m "watercooler: reindex after merge"
   ```

6. **Use HTML Export for Team Dashboard**:
   ```bash
   watercooler web-export
   # Creates $THREADS_DIR/index.html
   # Open in browser to see all threads + NEW markers
   ```

7. **Commit Thread Creation and Closure**:
   ```bash
   # Thread lifecycle milestones:
   watercooler init-thread new-feature
   git add $THREADS_DIR/new-feature.md
   git commit -m "watercooler: start new-feature thread"

   # ... work happens ...

   watercooler say new-feature --type Closure --status closed --body "Complete"
   git add $THREADS_DIR/new-feature.md
   git commit -m "watercooler: close new-feature thread"
   ```

---

## Decision Tracking

### Problem

Software projects make hundreds of technical decisions:
- Why did we choose PostgreSQL over MongoDB?
- Why REST instead of GraphQL?
- What security approach did we decide?
- Why did we change our minds about caching strategy?

These decisions are often lost in:
- Scattered Slack/email threads (not searchable)
- Undocumented code (implicit decisions)
- Lost institutional knowledge (person leaves)
- Meeting notes (hard to find later)

Traditional ADRs (Architecture Decision Records) help but exist outside normal workflow.

### Solution

Watercooler threads provide **embedded decision tracking**:

1. **Decision Entry Type**: Explicit marking of decisions
2. **Chronological Evolution**: See how thinking evolved
3. **Git-Versioned**: Travel with the code
4. **Searchable**: Find decisions with `watercooler search`
5. **Role-Based**: Track who proposed vs who approved
6. **Status Lifecycle**: open → in-review → closed

### Example: Database Migration Decision

```bash
# Start decision thread
watercooler init-thread db-migration-decision \
  --title "Database: PostgreSQL to DynamoDB?" \
  --owner Team \
  --participants "Team, Claude, Codex" \
  --ball claude

# Initial analysis (planner)
watercooler say db-migration-decision \
  --agent Claude \
  --role planner \
  --title "Migration Analysis" \
  --type Plan \
  --body @migration-analysis.md
# (Detailed analysis: pros/cons, risks, timeline)

# Implementation feasibility check
watercooler say db-migration-decision \
  --agent Codex \
  --role implementer \
  --title "Feasibility Assessment" \
  --type Note \
  --body "Estimated 3-4 weeks for dual-write implementation. Risk: data consistency during transition."

# Security review
watercooler say db-migration-decision \
  --agent Claude \
  --role critic \
  --title "Security Concerns" \
  --type Note \
  --body "DynamoDB fine-grained access control requires IAM policy overhaul. Current RBAC simpler in PostgreSQL."

# Team discussion and decision
watercooler say db-migration-decision \
  --agent Team \
  --role pm \
  --title "Decision: Stay with PostgreSQL" \
  --type Decision \
  --body "Decided to stay with PostgreSQL. Reasons: (1) Security model simpler, (2) Team expertise, (3) Query flexibility needed. Will revisit in 6 months if scale requires it." \
  --status closed

# Record rationale in commit
git add $THREADS_DIR/db-migration-decision.md
git commit -m "decision: stay with PostgreSQL for now

See $THREADS_DIR/db-migration-decision.md for full analysis.
Key factors: security model, team expertise, query flexibility.
Will revisit in 6 months if scale requires."
```

**6 Months Later - Revisiting Decision:**
```bash
# Search for previous decision
watercooler search "DynamoDB"
# Returns: db-migration-decision.md:35: Database: PostgreSQL to DynamoDB?

# Read previous analysis
cat $THREADS_DIR/db-migration-decision.md
# Full context available: analysis, concerns, decision, rationale

# Start new thread referencing old decision
watercooler init-thread db-scaling-2025 \
  --title "Database Scaling Strategy 2025" \
  --ball claude

watercooler say db-scaling-2025 \
  --agent Team \
  --role pm \
  --title "Context" \
  --body "6 months ago we decided to stay with PostgreSQL (see $THREADS_DIR/db-migration-decision.md). Now at 10M users, need to revisit. Claude, please analyze current bottlenecks."
```

### Example: Architectural Decision Record (ADR) Style

```bash
# ADR-style decision tracking
watercooler init-thread adr-auth-approach \
  --title "ADR: Authentication Strategy" \
  --ball team

# Context
watercooler say adr-auth-approach \
  --agent Team \
  --role pm \
  --title "Context" \
  --type Note \
  --body "Need auth for API. Options: (1) JWT, (2) Session cookies, (3) OAuth2. Requirements: mobile app support, API access, social login."

# Options analysis
watercooler say adr-auth-approach \
  --agent Claude \
  --role planner \
  --title "Options Analysis" \
  --type Plan \
  --body "JWT: stateless, mobile-friendly, but token revocation hard. Session: simple, but mobile harder. OAuth2: best for social, but complex."

# Decision
watercooler say adr-auth-approach \
  --agent Team \
  --role pm \
  --title "Decision: JWT + OAuth2" \
  --type Decision \
  --body "Use JWT for API access. Add OAuth2 for social login. Accept token revocation complexity - will implement token blacklist."

# Consequences
watercooler say adr-auth-approach \
  --agent Claude \
  --role planner \
  --title "Consequences" \
  --type Note \
  --body "Positive: mobile support, social login, stateless API. Negative: need token blacklist service, refresh token rotation complexity."

# Implementation
watercooler say adr-auth-approach \
  --agent Codex \
  --role implementer \
  --title "Implementation Complete" \
  --type PR \
  --body "Implemented JWT auth + OAuth2. PR #789. Token blacklist in Redis."

# Closure
watercooler say adr-auth-approach \
  --agent Team \
  --role pm \
  --title "ADR Finalized" \
  --type Closure \
  --body "Decision recorded. Implementation complete. Deployed 2025-10-07." \
  --status closed
```

### Example: Decision Evolution (Changing Mind)

```bash
# Initial decision
watercooler init-thread caching-strategy \
  --title "Caching Strategy" \
  --ball claude

watercooler say caching-strategy \
  --agent Claude \
  --role planner \
  --title "Proposal: Redis" \
  --type Plan \
  --body "Use Redis for caching. TTL-based invalidation."

watercooler say caching-strategy \
  --agent Team \
  --role pm \
  --title "Decision: Redis Approved" \
  --type Decision \
  --body "Approved. Codex, please implement."

# Implementation uncovers issues
watercooler say caching-strategy \
  --agent Codex \
  --role implementer \
  --title "Redis Performance Issues" \
  --type Note \
  --body "Network latency to Redis cluster causing 100ms+ delays. Cache hit rate only 40%."

# Revisit decision
watercooler say caching-strategy \
  --agent Claude \
  --role critic \
  --title "Recommendation: In-Memory Cache" \
  --type Decision \
  --body "Switch to in-process cache (Caffeine). Reduce latency to <1ms. Trade-off: cache per instance, but hit rate better with LRU."

watercooler say caching-strategy \
  --agent Team \
  --role pm \
  --title "Decision Changed: In-Memory" \
  --type Decision \
  --body "Approved switch to in-memory cache. Original Redis decision was correct given info at time, but implementation revealed latency issue." \
  --status closed
```

### Best Practices

1. **Use Decision Entry Type Explicitly**:
   ```bash
   watercooler say topic --type Decision --body "..."
   ```
   Makes decisions searchable: `grep "Type: Decision" $THREADS_DIR/*.md`

2. **Structure Decision Threads**:
   - Context: Problem statement and requirements
   - Analysis: Options and trade-offs (Plan type)
   - Discussion: Concerns and questions (Note type)
   - Decision: Final choice and rationale (Decision type)
   - Consequences: Expected outcomes (Note type)
   - Closure: Implementation status (Closure type)

3. **Link Decisions to Code**:
   ```bash
   git commit -m "implement auth with JWT

   Decision recorded in $THREADS_DIR/adr-auth-approach.md
   See thread for full rationale and alternatives considered."
   ```

4. **Search for Past Decisions**:
   ```bash
   # Find all decisions
   grep -r "Type: Decision" $THREADS_DIR/

   # Search by keyword
   watercooler search "authentication"
   watercooler search "migration"
   ```

5. **Date-Stamp Decisions**:
   - Timestamps automatic in Entry metadata
   - Useful for "why did we decide this 6 months ago?"
   - Shows evolution of thinking over time

6. **Don't Fear Changing Decisions**:
   - New information is valid reason to change
   - Document why decision changed
   - Preserve history (append-only protocol)
   - Shows learning and adaptation

7. **Close Decision Threads**:
   ```bash
   watercooler say topic \
     --type Closure \
     --status closed \
     --body "Decision implemented and deployed."
   ```

---

## PR Review Workflow

### Problem

Pull request reviews often suffer from:
- Scattered feedback (GitHub comments, Slack, email)
- Lost context (why was this approach chosen?)
- Review bottlenecks (unclear who's reviewing)
- No pre-PR discussion (surprises in review)
- Rework delays (back-and-forth on approach)

GitHub PR comments are ephemeral - once PR merged, context harder to find.

### Solution

Watercooler provides **structured PR workflow** with:

1. **Pre-PR Discussion**: Design before coding
2. **Review Coordination**: Ball tracking shows who's reviewing
3. **Persistent Context**: Reviews survive PR merge
4. **Status Progression**: open → in-review → merged
5. **Cross-Reference**: Link thread ↔ PR

### Example: Full PR Workflow

**Phase 1: Pre-PR Design Discussion**
```bash
# Before writing code - discuss approach
watercooler init-thread pr-search-feature \
  --title "Feature: Full-Text Search" \
  --owner Team \
  --participants "Team, Claude, Codex" \
  --ball claude

# Propose design
watercooler say pr-search-feature \
  --agent Team \
  --role pm \
  --title "Feature Request" \
  --body "Need full-text search for blog posts. Requirements: fuzzy matching, highlight results, autocomplete."

# Design review
watercooler say pr-search-feature \
  --agent Claude \
  --role planner \
  --title "Design Proposal" \
  --type Plan \
  --body "Use PostgreSQL full-text search (tsvector). Add GIN index. Frontend: debounced autocomplete. Highlight with ts_headline."

# Approve design
watercooler say pr-search-feature \
  --agent Team \
  --role pm \
  --title "Approach Approved" \
  --type Decision \
  --body "Approved. Codex, please implement."
```

**Phase 2: Implementation**
```bash
# Implement feature
watercooler say pr-search-feature \
  --agent Codex \
  --role implementer \
  --title "Implementation Complete" \
  --body "Implemented search with tsvector. PR #456: https://github.com/org/repo/pull/456"

# Update status
watercooler set-status pr-search-feature in-review
```

**Phase 3: Code Review**
```bash
# Reviewer starts review
watercooler ack pr-search-feature \
  --agent Claude \
  --role critic \
  --title "Review Started"
# Ball stays with claude (reviewer)

# Reviewer provides feedback
watercooler say pr-search-feature \
  --agent Claude \
  --role critic \
  --title "Review Feedback" \
  --type Note \
  --body "Issues found: (1) Missing input sanitization (SQL injection risk), (2) No pagination, (3) Tests missing edge cases. See PR comments for details."
# Ball flips to codex

# Developer addresses feedback
watercooler say pr-search-feature \
  --agent Codex \
  --role implementer \
  --title "Feedback Addressed" \
  --body "(1) Added parameterized queries, (2) Added pagination with LIMIT/OFFSET, (3) Added 5 new test cases. Updated PR."
# Ball flips to claude

# Reviewer approves
watercooler say pr-search-feature \
  --agent Claude \
  --role critic \
  --title "LGTM" \
  --type Decision \
  --body "All feedback addressed. Approved for merge."
# Ball flips to team (PM)
```

**Phase 4: Merge and Closure**
```bash
# PM merges PR
watercooler say pr-search-feature \
  --agent Team \
  --role pm \
  --title "Merged to main" \
  --type PR \
  --body "PR #456 merged at 2025-10-07T16:00:00Z. Commit: abc123. Deployed to staging."

# Close thread
watercooler say pr-search-feature \
  --agent Team \
  --role pm \
  --title "Deployed to Production" \
  --type Closure \
  --body "Deployed to production 2025-10-07T18:00:00Z. Search feature live." \
  --status closed

# Commit final state
git add $THREADS_DIR/pr-search-feature.md
git commit -m "watercooler: pr-search-feature deployed"
git push
```

**Result: Complete PR History**
```markdown
# pr-search-feature — Thread
Status: closed
Ball: team
...

---
Entry: Team (agent) 2025-10-07T09:00:00Z
Role: pm
Type: Note
Title: Feature Request

Need full-text search for blog posts...

---
Entry: Claude (agent) 2025-10-07T09:30:00Z
Role: planner
Type: Plan
Title: Design Proposal

Use PostgreSQL full-text search...

---
Entry: Team (agent) 2025-10-07T10:00:00Z
Role: pm
Type: Decision
Title: Approach Approved

Approved. Codex, please implement.

---
Entry: Codex (agent) 2025-10-07T14:00:00Z
Role: implementer
Type: Note
Title: Implementation Complete

Implemented search with tsvector. PR #456...

---
Entry: Claude (agent) 2025-10-07T15:00:00Z
Role: critic
Type: Note
Title: Review Feedback

Issues found: (1) SQL injection risk...

---
Entry: Codex (agent) 2025-10-07T15:30:00Z
Role: implementer
Type: Note
Title: Feedback Addressed

(1) Added parameterized queries...

---
Entry: Claude (agent) 2025-10-07T16:00:00Z
Role: critic
Type: Decision
Title: LGTM

All feedback addressed. Approved for merge.

---
Entry: Team (agent) 2025-10-07T16:30:00Z
Role: pm
Type: PR
Title: Merged to main

PR #456 merged at 2025-10-07T16:00:00Z...

---
Entry: Team (agent) 2025-10-07T18:00:00Z
Role: pm
Type: Closure
Title: Deployed to Production

Deployed to production 2025-10-07T18:00:00Z. Search feature live.
```

### Example: Multi-Reviewer PR

```bash
# Two reviewers needed: security + performance
watercooler say pr-api-endpoint \
  --agent Codex \
  --role implementer \
  --title "API Endpoint Complete" \
  --body "New /api/users endpoint. PR #789. Needs security and performance review."

# Security reviewer
watercooler ack pr-api-endpoint \
  --agent Claude \
  --role critic \
  --title "Security Review Started" \
  --body "Checking auth and input validation."

watercooler say pr-api-endpoint \
  --agent Claude \
  --role critic \
  --title "Security: Approved" \
  --type Decision \
  --body "Auth correct. Input validation solid. Rate limiting present."

# Performance reviewer (different agent)
watercooler ack pr-api-endpoint \
  --agent PerformanceBot \
  --role critic \
  --title "Performance Review Started" \
  --body "Load testing 1000 req/sec."

watercooler say pr-api-endpoint \
  --agent PerformanceBot \
  --role critic \
  --title "Performance: Needs Work" \
  --body "Latency p99: 800ms. Issue: N+1 query in user.posts. Add eager loading."

# Developer fixes
watercooler say pr-api-endpoint \
  --agent Codex \
  --role implementer \
  --title "Fixed N+1 Query" \
  --body "Added .includes(:posts). Latency now p99: 120ms."

# Performance re-review
watercooler say pr-api-endpoint \
  --agent PerformanceBot \
  --role critic \
  --title "Performance: Approved" \
  --type Decision \
  --body "Latency acceptable. Approved."

# Both reviews complete - merge
watercooler handoff pr-api-endpoint \
  --agent Team \
  --note "Both reviews approved - merging"
```

### Best Practices

1. **One Thread Per PR**:
   - Thread name matches PR scope (not PR number)
   - Link PR number in entries: "PR #456"
   - Cross-reference in PR description: "See $THREADS_DIR/pr-search-feature.md"

2. **Pre-PR Design Discussion**:
   - Start thread before writing code
   - Get design approval first (Plan → Decision)
   - Reduces rework during review

3. **Use PR Entry Type**:
   ```bash
   watercooler say topic --type PR --body "PR #456 merged"
   ```
   Clearly marks PR-related entries

4. **Track Review Progress with Ball**:
   ```bash
   $ watercooler list
   2025-10-07T15:00:00Z  in-review  claude  NEW  PR: Search Feature  pr-search-feature.md
   ```
   Ball shows who's reviewing, NEW shows needs attention

5. **Preserve Context After PR Merge**:
   - GitHub PR closed → comments harder to find
   - Watercooler thread preserved in git
   - Complete history: design → implementation → review → merge

6. **Link Commits to Threads**:
   ```bash
   git commit -m "implement full-text search

   Implements design from $THREADS_DIR/pr-search-feature.md
   PR #456"
   ```

7. **Close Thread After Deployment**:
   ```bash
   watercooler say topic \
     --type Closure \
     --status closed \
     --body "Deployed to production. Feature live."
   ```

8. **Use for Pre-Commit Review**:
   ```bash
   # Before creating PR - get early feedback
   watercooler say feature-design \
     --agent Team \
     --title "RFC: New Approach" \
     --body "Thinking of refactoring auth. Draft code: https://gist.github.com/..."

   # Get feedback before formal PR
   watercooler say feature-design \
     --agent Claude \
     --title "Feedback" \
     --body "Approach looks good. Suggest: add caching layer."
   ```

---

## See Also

- [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md) - Detailed guide to roles, types, and entry format
- [AGENT_REGISTRY.md](AGENT_REGISTRY.md) - Agent configuration and counterpart mappings
- [TEMPLATES.md](TEMPLATES.md) - Customizing thread and entry templates
- [.github/WATERCOOLER_SETUP.md](../.github/WATERCOOLER_SETUP.md) - Git configuration for collaboration
- [README.md](../README.md) - Quick start and command reference
