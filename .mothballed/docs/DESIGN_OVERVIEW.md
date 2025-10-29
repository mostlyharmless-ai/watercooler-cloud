# Watercooler: Git-Native Multi-Agent Collaboration

## Problem Statement

AI coding agents operate asynchronously across codebases, branches, and time. They need a durable, context-aware communication layer that:
- **Preserves ground truth**: Every conversation references specific code states (repo, branch, commit)
- **Scales naturally with git**: Branch-specific discussions without centralized infrastructure
- **Works offline**: No dependency on hosted services for core functionality
- **Eliminates configuration overhead**: Adapts automatically to developer workflow

Traditional approaches fail: chat systems lose code context; issue trackers are too heavyweight; comments in code pollute history. What's needed is a **shadow layer** that mirrors code structure while remaining invisible to build systems.

## Core Architecture

Watercooler implements file-based collaboration threads that live in a **dedicated threads repository**, paired 1:1 with each code repository and mirroring its branch structure.

### Repository Pairing

```
Code Repository                    Threads Repository
mostlyharmless-ai/app         →    mostlyharmless-ai/app-threads
├── main                      ↔    ├── main
├── feature/auth              ↔    ├── feature/auth
└── fix/performance           ↔    └── fix/performance
```

Every thread entry records immutable linkage to code:
- `Code-Repo: mostlyharmless-ai/app`
- `Code-Branch: feature/auth`
- `Code-Commit: 4f1c2a3`

This creates **verifiable provenance**: any discussion can be traced to exact code state, even months later.

### Discovery Model

The system uses **pattern-based discovery** to eliminate per-project configuration:

1. **Code context extraction** (from git workspace):
   - Repo root: `git rev-parse --show-toplevel`
   - Current branch: `git rev-parse --abbrev-ref HEAD`
   - Current commit: `git rev-parse --short HEAD`
   - Origin URL: `git remote get-url origin` → parse `{org}/{repo}`

2. **Threads repo resolution** (via pattern):
   - Pattern: `git@github.com:{org}/{repo}-threads.git`
   - Local cache: `~/.watercooler-threads/{org}/{repo}-threads`
   - Auto-clone on first access

3. **Branch mirroring**:
   - Automatically checkout matching branch in threads repo
   - Create branch on first write if missing
   - Commit footers preserve cross-reference

Result: Developers simply `cd` into any code repository, and watercooler automatically operates on the correct thread context.

## Operational Model

### Zero-Configuration Setup

A single global MCP registration:

```bash
claude mcp add --transport stdio watercooler-dev --scope user \
  -e WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git" \
  -- python3 -m watercooler_mcp
```

Works across unlimited repositories with zero additional configuration.

### Consistency Model

**Eventually consistent** with git-native conflict resolution:

- **Concurrency**: Multiple agents write simultaneously; union merge policy handles append-only collisions
- **Ordering**: Last-writer-wins for ball/status; temporal ordering preserved via timestamps
- **Idempotency**: Entry-ID markers in commit messages and body prevent duplicates on retry
- **Latency**: 2-5 second propagation typical (git push → GitHub → git pull)

This trades real-time ordering guarantees for:
- Zero coordination overhead
- Complete offline functionality
- Natural audit trail (git history)
- Familiar tooling (git, GitHub)

### Write Discipline

Every write operation:
1. **Pull**: Fetch latest from remote (`git pull --rebase`)
2. **Append**: Add entry to thread file (markdown)
3. **Commit**: Record with structured footers
4. **Push**: Retry with exponential backoff on rejection

Commit message format:
```
[wc] say: feature-auth-refactor (#01HXABC...)

Code-Repo: mostlyharmless-ai/app
Code-Branch: feature/auth
Code-Commit: 4f1c2a3
Watercooler-Entry-ID: 01HXABC...
Watercooler-Topic: feature-auth-refactor
```

This creates a **permanent audit trail** searchable via git tools.

## Design Rationale

### Why Separate Threads Repository?

**Code repo pollution**: Threads are chatty; mixing them with code creates:
- Noisy git history
- Branch switching friction (threads for old branches appear in new branches)
- CI trigger spam
- Merge conflicts between unrelated work

**Solution**: Dedicated threads repo allows:
- Unlimited discussion without impacting code history
- Branch-specific threads that don't pollute other branches
- No CI integration required
- Direct push to main (no PR gating for conversations)

### Why Branch Mirroring?

**Context specificity**: Discussion about `feature/auth` is irrelevant to `main`. Branch mirroring:
- Scopes threads to relevant code state
- Surfaces correct threads when switching branches
- Preserves discussion when branches merge (via git merge or manual consolidation)
- Natural lifecycle: feature branch → feature threads → merge both (or archive threads)

### Why Git-Based Storage?

Alternative approaches (database, cloud service, file sync) fail to provide:
- **Offline resilience**: Work continues without connectivity
- **Verifiable history**: Git's cryptographic chain proves provenance
- **Access control**: GitHub team permissions apply automatically
- **Tooling familiarity**: grep, diff, blame, bisect all work
- **Cost**: Zero runtime cost; GitHub storage is free for private repos

Git's append-only model with union merge is purpose-built for this use case.

## Agent Identity Model

Agents must declare identity before writes:

```python
watercooler_v1_set_agent(base="Claude", spec="implementer-code")
```

- `base`: Agent platform (Claude, Codex, GPT, etc.)
- `spec`: Current role (pm, planner-architecture, implementer-code, tester, docs, ops)

This appears in thread headers: `Entry: Claude:implementer-code (user) 2025-10-27`

**Rationale**: Multi-agent systems need attribution clarity. Identity-per-task (not just per-agent) enables:
- Role-appropriate communication (PM speaks differently than implementer)
- Audit trail of which agent made which decisions
- Clear handoff semantics (PM → planner → implementer)

## Comparison to Alternatives

| Approach | Strengths | Weaknesses |
|----------|-----------|------------|
| **Issues/PRs** | Built-in, searchable | Heavyweight, not branch-scoped, requires GitHub UI |
| **Code comments** | Co-located | Pollutes code, no structure, buried in history |
| **Chat systems** | Real-time | Loses code context, ephemeral, no provenance |
| **Shared docs** | Rich formatting | Manual linking, no branch awareness, version conflicts |
| **Watercooler** | Branch-scoped, verifiable provenance, zero infrastructure | 2-5s latency, eventual consistency |

Watercooler optimizes for **asynchronous agent collaboration on code**, not real-time human chat.

## Operational Characteristics

**Strengths**:
- Works offline indefinitely
- Zero hosting cost
- Scales to any number of repos/branches
- Natural audit trail
- Cryptographic provenance
- Git-native tooling

**Tradeoffs**:
- 2-5 second propagation delay
- Eventual consistency (last-writer-wins)
- Requires git/GitHub access
- Union merge occasionally needs manual resolution

**Ideal for**:
- Multi-agent code collaboration (2-10 agents)
- Async team workflows (distributed, async-first)
- Long-lived feature branch discussions
- Provenance-critical environments (regulated industries, research)

**Not ideal for**:
- Real-time pair programming
- Sub-second coordination requirements
- Non-technical stakeholders (no git access)
- Cross-organization workflows (different git hosting)

## Future Extensibility

The git-based storage model enables optional enhancements without protocol changes:

- **Notifications**: GitHub Actions trigger on thread changes → Slack/email
- **Thin SSE layer**: Add real-time push notifications while keeping git as storage
- **Path-scoped topics**: Mirror code directory structure in threads (e.g., `src/api/handler.md`)
- **Cross-repo indexing**: Aggregate threads across org for architecture discussions
- **Merge summaries**: Auto-generate PR descriptions from thread history

Core design remains: **git is the source of truth**.

## Summary

Watercooler solves multi-agent collaboration by treating **git as both storage and coordination layer**. Pattern-based discovery eliminates configuration; branch mirroring provides natural context scoping; commit footers create immutable provenance.

The result: agents collaborate on code with the same natural workflow developers use—check out a branch, make changes, push—extended to structured conversation. No servers, no configuration, no coordination overhead. Just git.
