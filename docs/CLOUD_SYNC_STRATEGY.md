# Cloud Sync Strategy for Watercooler MCP

## Executive Summary

This document outlines the realistic architecture for syncing watercooler threads between multiple users in cloud-hosted MCP deployments.

**Key Constraint:** The Model Context Protocol (MCP) does **not support custom push notifications** to clients (Claude, Codex). This means we cannot implement real-time chat-like collaboration. Instead, we use a **pull-based async collaboration model** with git as the source of truth.

**Best Use Cases:**
- ✅ Async collaboration (planning, code review, handoffs)
- ✅ Multi-user project coordination
- ✅ Persistent conversation threads
- ❌ Not ideal for rapid-fire brainstorming (use chat instead)

---

## MCP Protocol Limitations

### What MCP Supports (Server → Client Push)

The MCP protocol only allows these **predefined notification types**:

- `notifications/tools/list_changed` - When tools are added/removed
- `notifications/resources/list_changed` - When resources change
- `notifications/prompts/list_changed` - When prompts change
- `notifications/progress` - Progress updates during tool execution
- `notifications/message` - Log messages

### What's Missing

**No custom notifications** for:
- Thread updates
- New entries posted
- Arbitrary data changes
- Real-time collaboration events

**Impact:** We cannot push "Codex just replied to your thread" notifications to Claude. Clients must **poll** by calling `read_thread()` when the user asks for updates.

---

## Recommended Architecture: Git-Based Sync with Optional Cloudflare

### High-Level Design

```
┌──────────────────────────────────────┐
│     GitHub/GitLab Repository         │
│         (Source of Truth)            │
│                                      │
│  ├── feature-x.md                   │
│  ├── bug-123.md                     │
│  └── planning.md                    │
└────────┬──────────────┬──────────────┘
         │              │
    ┌────▼──────┐  ┌───▼──────┐
    │  MCP A    │  │  MCP B   │
    │ (Codex)   │  │ (Claude) │
    └────┬──────┘  └───┬──────┘
         │             │
    User A         User B
```

### How It Works

**Read Operations:**
1. User asks: "Claude, what's the status of feature-x?"
2. Claude calls `read_thread("feature-x")`
3. MCP server performs `git pull`
4. Returns latest thread content (including updates from other agents)

**Write Operations:**
1. User asks: "Claude, tell Codex we need tests"
2. Claude calls `say("feature-x", "Please prioritize tests", ...)`
3. MCP server:
   - `git pull` (get latest)
   - Append entry to `feature-x.md`
   - `git commit -m "Claude: Please prioritize tests"`
   - `git push`
4. Other MCP servers see update on next `git pull`

**Latency:**
- Read: ~200-500ms (git pull + file read)
- Write: ~500ms-1s (git pull + append + commit + push)
- **Not real-time**, but acceptable for async collaboration

---

## Implementation: Git Sync Module

### Core Sync Manager

```python
"""Git-based synchronization for cloud-hosted watercooler MCP servers"""

import os
import subprocess
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar('T')

class GitSyncManager:
    """Manages git sync for threads directory (dedicated repo recommended)."""

    def __init__(
        self,
        repo_url: str,
        local_path: Path,
        ssh_key_path: Path | None = None,
        author_name: str = "Watercooler MCP",
        author_email: str = "mcp@watercooler.dev"
    ):
        self.repo_url = repo_url
        self.local_path = local_path
        self.ssh_key_path = ssh_key_path
        self.author_name = author_name
        self.author_email = author_email
        # Prepare git env once (propagated to all git ops)
        self._env = os.environ.copy()
        if self.ssh_key_path:
            self._env["GIT_SSH_COMMAND"] = f"ssh -i {self.ssh_key_path} -o IdentitiesOnly=yes"
        self._setup()

    def _setup(self):
        """Ensure repo is cloned and configured"""
        if not (self.local_path / ".git").exists():
            self._clone()
        self._configure_git()

    def _clone(self):
        """Clone the watercooler repo"""
        cmd = ["git", "clone", self.repo_url, str(self.local_path)]
        subprocess.run(cmd, env=self._env, check=True)

    def _configure_git(self):
        """Configure git user for commits"""
        subprocess.run(
            ["git", "config", "user.name", self.author_name],
            cwd=self.local_path, env=self._env, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", self.author_email],
            cwd=self.local_path, env=self._env, check=True
        )

    def pull(self) -> bool:
        """Pull latest changes. Returns True if successful."""
        try:
            subprocess.run(
                ["git", "pull", "--rebase", "--autostash"],
                cwd=self.local_path,
                capture_output=True,
                env=self._env,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            # Abort any in-progress rebase and signal failure
            subprocess.run(["git", "rebase", "--abort"], cwd=self.local_path, env=self._env)
            return False

    def commit_and_push(self, message: str, max_retries: int = 3) -> bool:
        """Commit changes and push with retry logic"""
        # Stage only changes within local_path (dedicated repo recommended)
        subprocess.run(["git", "add", "-A"], cwd=self.local_path, env=self._env, check=True)

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=self.local_path,
            env=self._env
        )
        if result.returncode == 0:
            # No changes
            return True

        # Commit
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.local_path,
            env=self._env,
            check=True
        )

        # Push with retry
        for attempt in range(max_retries):
            try:
                subprocess.run(
                    ["git", "push"],
                    cwd=self.local_path,
                    env=self._env,
                    check=True
                )
                return True
            except subprocess.CalledProcessError:
                if attempt < max_retries - 1:
                    # Pull latest, then retry push
                    if not self.pull():
                        return False
                    continue
                return False
        return False

    def with_sync(self, operation: Callable[[], T], commit_message: str) -> T:
        """Execute operation with git sync before and after"""
        # Pull latest
        if not self.pull():
            raise RuntimeError("Failed to sync latest changes")

        # Execute operation
        result = operation()

        # Commit and push
        if not self.commit_and_push(commit_message):
            raise RuntimeError("Failed to push changes")

        return result
```

### Integration with MCP Tools

```python
# In server.py
import os
from pathlib import Path
from .git_sync import GitSyncManager
from .config import get_threads_dir, get_agent_name

def get_git_sync_manager() -> GitSyncManager | None:
    """Get git sync manager if configured (cloud mode)"""
    repo_url = os.getenv("WATERCOOLER_GIT_REPO")
    if not repo_url:
        return None  # Local mode

    ssh_key = os.getenv("WATERCOOLER_GIT_SSH_KEY")
    return GitSyncManager(
        repo_url=repo_url,
        local_path=get_threads_dir(),
        ssh_key_path=Path(ssh_key) if ssh_key else None,
        author_name=os.getenv("WATERCOOLER_GIT_AUTHOR", "Watercooler MCP"),
        author_email=os.getenv("WATERCOOLER_GIT_EMAIL", "mcp@watercooler.dev")
    )


@mcp.tool()
def watercooler_v1_say(
    ctx: Context,
    topic: str,
    title: str,
    body: str,
    role: str = "implementer",
    entry_type: str = "Note"
) -> str:
    """Add entry and flip ball (with git sync in cloud mode)"""
    try:
        threads_dir = get_threads_dir()
        agent = get_agent_name(ctx.client_id)
        sync = get_git_sync_manager()

        def append_operation():
            commands.say(
                topic,
                threads_dir=threads_dir,
                agent=agent,
                role=role,
                title=title,
                entry_type=entry_type,
                body=body,
            )

        if sync:
            # Cloud mode: sync before and after
            entry_id = f"{agent}-{topic}-{__import__('time').strftime('%Y%m%dT%H%M%SZ')}"
            sync.with_sync(
                append_operation,
                commit_message=(
                    f"{agent}: {title} ({topic})\n"
                    f"Watercooler-Entry-ID: {entry_id}"
                ),
            )
        else:
            # Local mode: no sync
            append_operation()

        # Return confirmation
        thread_path = fs.thread_path(topic, threads_dir)
        _, status, ball, _ = thread_meta(thread_path)

        return (
            f"✅ Entry added to '{topic}'\n"
            f"Title: {title}\n"
            f"Role: {role} | Type: {entry_type}\n"
            f"Ball flipped to: {ball}\n"
            f"Status: {status}"
        )
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def watercooler_v1_read_thread(
    ctx: Context,
    topic: str,
    from_entry: int = 0,
    limit: int = 100,
    format: str = "markdown"
) -> str:
    """Read thread (with git sync in cloud mode)"""
    try:
        threads_dir = get_threads_dir()
        sync = get_git_sync_manager()

        # Pull latest before reading
        if sync:
            sync.pull()

        # Read thread
        thread_path = fs.thread_path(topic, threads_dir)
        if not thread_path.exists():
            return f"Error: Thread '{topic}' not found"

        content = thread_path.read_text()
        return content
    except Exception as e:
        return f"Error: {str(e)}"
```

---

## Operational Hardening

- Git environment propagation
  - Set `GIT_SSH_COMMAND` once and pass `env` to all git subprocess calls (clone, pull, commit, push) to avoid inconsistent transports.
- Dedicated threads repository (recommended)
  - Use a standalone repo where the repo root is the threads directory to minimize unrelated diffs and simplify staging. If co-located, restrict staging to the `.watercooler/` path.
- Idempotent writes
  - Generate an `Entry-ID` per append and include it in commit message footers and/or the appended markdown. Retry logic should detect duplicates and skip re-appending.
- Sparse/shallow strategies (if co-located)
  - Use sparse checkout limited to `.watercooler/` and `--filter=blob:none` for large monorepos.
- Conflict policy for metadata
  - Keep status/ball in a YAML front matter block. Consider a small `meta.json` per topic if header churn becomes frequent. Document last-writer-wins vs merge policy explicitly.
- Cloudflare Worker safeguards
  - Use conditional requests (ETag/If-None-Match and SHA preconditions) for read/write to prevent lost updates. R2 cache keys should incorporate commit SHA to avoid stale reads. Apply exponential backoff on 429/5xx.
- Observability & SLOs
  - Emit metrics: pull/push latency, conflict rate, retry counts, bytes transferred. Define target P95 read/write latencies and push-failure SLOs.
- Security
  - Prefer deploy keys with least privilege, avoid logging secrets/URLs, and consider signed commits (`commit.gpgsign=true`).
- Multi-tenant (future OAuth)
  - Per-user repo naming, encrypted token storage at rest, scoped app permissions.

## Cloudflare Integration Options

### Option 1: Cloudflare Workers for Edge MCP Hosting

**What:** Deploy MCP server as Cloudflare Worker (edge compute)

**Architecture:**
```
┌─────────────────────────────────────┐
│  Cloudflare Worker (Global Edge)   │
│  - Runs MCP server logic           │
│  - Proxies to GitHub API           │
│  - Caches in R2 (optional)         │
└──────────┬────────────┬─────────────┘
           │            │
       GitHub API    R2 Cache
```

**Worker Code:**
```javascript
// worker.js - Cloudflare Worker MCP Server

export default {
  async fetch(request, env) {
    const { tool, params } = await request.json();

    // Git sync: Pull latest from GitHub (use ETag/If-None-Match for efficiency)
    const threads = await fetchFromGitHub(
      env.GITHUB_TOKEN,
      env.GITHUB_REPO,
      '.watercooler'
    );

    // Execute MCP tool
    let result;
    switch (tool) {
      case 'read_thread':
        result = threads[params.topic];
        break;

      case 'say':
        // Append entry
        threads[params.topic] += formatEntry(params);

        // Git sync: Push to GitHub with preconditions (If-Match or current SHA)
        await pushToGitHub(
          env.GITHUB_TOKEN,
          env.GITHUB_REPO,
          '.watercooler',
          threads,
          `${params.agent}: ${params.title}`
        );
        result = "Entry added";
        break;
    }

    // Cache in R2 for fast reads (optional) — include version to prevent staleness
    await env.R2.put(`threads/${params.topic}@${threads.commitSha}`, result);

    return new Response(JSON.stringify({ result }));
  }
};

async function fetchFromGitHub(token, repo, path) {
  const response = await fetch(
    `https://api.github.com/repos/${repo}/contents/${path}`,
    { headers: { Authorization: `token ${token}` } }
  );
  const files = await response.json();

  const threads = {};
  for (const file of files) {
    const content = await fetch(file.download_url).then(r => r.text());
    threads[file.name.replace('.md', '')] = content;
  }
  return threads;
}

async function pushToGitHub(token, repo, path, threads, message) {
  // Use GitHub API to commit changes
  // (Implementation details omitted for brevity)
}
```

**Pros:**
- ✅ Global edge deployment (low latency)
- ✅ Serverless (no infrastructure management)
- ✅ Free tier available
- ✅ Can cache in R2 for faster reads

**Cons:**
- ⚠️ Still git-based (same latency as pull/push)
- ⚠️ GitHub API rate limits

---

### Option 2: Cloudflare R2 + Workers (Git Backup)

**What:** Primary storage in R2, periodic git backup

**Architecture:**
```
┌─────────────────────────────────────┐
│  Cloudflare Worker                  │
│  ├─ Read from R2 (fast)            │
│  ├─ Write to R2 (fast)             │
│  └─ Async backup to git (durable) │
└─────────────────────────────────────┘
```

**Benefits:**
- Faster reads/writes (R2 latency ~50-100ms)
- Git as backup/audit trail
- Cheaper than database

**Trade-offs:**
- Optimistic locking needed for conflicts
- Periodic git sync (not every operation)

---

### Option 3: Cloudflare D1 (SQL Storage)

**What:** Store threads in SQLite database

**Schema:**
```sql
CREATE TABLE threads (
  topic TEXT PRIMARY KEY,
  status TEXT,
  ball TEXT,
  created_at TEXT
);

CREATE TABLE entries (
  id INTEGER PRIMARY KEY,
  topic TEXT,
  agent TEXT,
  title TEXT,
  body TEXT,
  timestamp TEXT,
  FOREIGN KEY(topic) REFERENCES threads(topic)
);
```

**Query Example:**
```javascript
async function readThread(env, topic) {
  const entries = await env.D1.prepare(
    'SELECT * FROM entries WHERE topic = ? ORDER BY timestamp'
  ).bind(topic).all();

  return formatAsMarkdown(entries);
}
```

**Pros:**
- ✅ SQL queries (complex filtering)
- ✅ ACID transactions
- ✅ Fast (<100ms latency)

**Cons:**
- ⚠️ Loses "just markdown files" philosophy
- ⚠️ Still pull-based (no push to clients)
- ⚠️ Migration from file format

---

### Option 4: Cloudflare Durable Objects (Future)

**What:** Strongly consistent, stateful WebSocket servers

**Potential Future Use:**
- Each thread = one Durable Object
- WebSocket connections for future custom clients
- NOT usable with current MCP clients (no custom WS support)

**When to consider:**
- If MCP protocol adds custom notification support
- If building custom UI/client for watercooler
- For now: not practical

---

## Conflict Resolution

### Append-Only Nature Reduces Conflicts

Most operations append to files → rare true conflicts:
- `say()` - Appends entry
- `ack()` - Appends entry
- `handoff()` - Modifies metadata (potential conflict)
- `set_status()` - Modifies metadata (potential conflict)

### Resolution Strategy

**Git handles most conflicts automatically:**
```python
def append_with_retry(thread_path: Path, entry: str, max_retries: int = 3):
    """Append entry with automatic conflict resolution"""
    for attempt in range(max_retries):
        try:
            git_pull()

            with advisory_lock():
                content = thread_path.read_text()
                new_content = content + entry
                thread_path.write_text(new_content)

            git_commit_push(f"Add entry to {thread_path.stem}")
            break

        except GitPushRejected as e:
            if attempt < max_retries - 1:
                # Someone else pushed; pull and retry
                continue
            raise ConflictError("Failed after max retries")
```

**For metadata conflicts:**
- Git rebase handles line-level merging
- Rare manual intervention needed
- Advisory locks reduce contention

---

## Environment Configuration

### Local Mode (Current)
```bash
# No git sync - uses local .watercooler/
WATERCOOLER_DIR=/path/to/project/.watercooler
WATERCOOLER_AGENT=Claude
```

### Cloud Mode (Git Sync)
```bash
# Enable git sync
WATERCOOLER_GIT_REPO=git@github.com:org/watercooler-threads.git
WATERCOOLER_GIT_SSH_KEY=/path/to/deploy/key
WATERCOOLER_GIT_AUTHOR=Agent Name
WATERCOOLER_GIT_EMAIL=agent@example.com

# Optional: Agent override
WATERCOOLER_AGENT=Claude
```

### Cloudflare Worker Mode
```bash
# Worker environment variables
GITHUB_TOKEN=ghp_xxx
GITHUB_REPO=org/watercooler-threads
R2_BUCKET=watercooler-cache

# Optional: Cloudflare D1
D1_DATABASE=watercooler-db
```

---

## Deployment Architectures

### Architecture 1: Docker Containers + Git

```
┌─────────────────────────────────────┐
│         GitHub Repository           │
└──────────┬────────────┬─────────────┘
           │            │
    ┌──────▼──────┐  ┌──▼──────┐
    │ Container A │  │ Container B │
    │ (MCP)       │  │ (MCP)       │
    │ - git clone │  │ - git clone │
    │ - pull/push │  │ - pull/push │
    └──────┬──────┘  └──┬──────┘
           │            │
        User A      User B
```

**Setup:**
```dockerfile
FROM python:3.10

# Install git
RUN apt-get update && apt-get install -y git

# Copy watercooler MCP
COPY . /app
WORKDIR /app
RUN pip install -e .[mcp]

# Configure git sync
ENV WATERCOOLER_GIT_REPO=git@github.com:org/threads.git

# Run MCP server (Python 3.10+)
CMD ["python3", "-m", "watercooler_mcp"]
```

---

### Architecture 2: Cloudflare Workers + GitHub API

```
┌─────────────────────────────────────┐
│  Cloudflare Global Edge Network    │
│  ├─ Worker (US-East)                │
│  ├─ Worker (EU-West)                │
│  └─ Worker (Asia-Pacific)           │
└──────────┬──────────────────────────┘
           │
    ┌──────▼──────┐
    │   GitHub    │
    │  (via API)  │
    └─────────────┘
```

**Benefits:**
- Global low-latency access
- No container orchestration
- Auto-scaling

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

---

## Migration Path

### Phase 1: Local Only (Current)
- ✅ Already implemented
- Works great for single-user or manual git sync

### Phase 2A: Optional Git Sync
```python
# Auto-detect mode
sync = get_git_sync_manager()
if sync:
    # Cloud mode
    sync.with_sync(operation, message)
else:
    # Local mode
    operation()
```

**Benefit:** Backward compatible. Existing users see no change.

### Phase 2B: Cloudflare Workers (Optional)
- Deploy to Cloudflare for global edge
- Still uses GitHub as backend
- Optional R2 caching

### Phase 2C: OAuth Integration
- GitHub/GitLab OAuth for auth
- Per-user thread repos
- Multi-tenant support

---

## Authentication & Multi-Tenancy

### GitHub OAuth Flow

1. **User Setup:**
   - User creates repo: `myorg/watercooler-threads`
   - Grants OAuth access to watercooler MCP
   - OAuth token stored in user profile

2. **MCP Server:**
   - Receives OAuth token from user session
   - Clones user's threads repo
   - Uses token for git operations

3. **Security:**
   - Tokens encrypted at rest
   - Per-user repo isolation
   - Deploy keys for team repos

---

## Testing Strategy

### 1. Local Git Sync Testing
```bash
# Setup test repo
git init /tmp/test-watercooler
cd /tmp/test-watercooler
git remote add origin git@github.com:test/threads.git

# Run two MCP servers
WATERCOOLER_GIT_REPO=... python -m watercooler_mcp  # Server A
WATERCOOLER_GIT_REPO=... python -m watercooler_mcp  # Server B

# Test concurrent writes
```

### 2. Conflict Simulation
```python
# Simulate concurrent edits
def test_concurrent_append():
    # Server A appends
    server_a.say("test", "Entry 1", "...")

    # Server B appends (before pulling)
    server_b.say("test", "Entry 2", "...")

    # Both should succeed after retry
    assert both_entries_in_thread("test")
```

### 3. Load Testing
- 10+ agents writing concurrently
- Measure conflict rate
- Verify no data loss

---

## FAQ

### Q: Why not WebSocket/SSE for real-time?

**A:** MCP protocol doesn't support custom push notifications. We can only push predefined MCP events (tool changes, progress, logs), not "thread updated" events.

### Q: Can we build a custom client that does support real-time?

**A:** Yes, but it defeats the purpose of MCP. You'd need custom Claude/Codex clients, which is complex and breaks the standard MCP ecosystem.

### Q: What about Durable Objects WebSockets?

**A:** Durable Objects are great for future custom UIs, but don't help with current MCP clients (Claude, Codex) since they can't receive custom WebSocket events.

### Q: Is git fast enough?

**A:** For async collaboration, yes. 500ms-1s latency is acceptable when users explicitly check for updates. Not suitable for real-time chat, but watercooler is designed for persistent threads, not rapid conversation.

### Q: What if GitHub is down?

**A:**
- Local fallback mode (work offline, sync later)
- Or use GitLab/self-hosted git
- Or Cloudflare R2 with periodic git backup

### Q: How many concurrent users can this handle?

**A:** Git scales well for append-mostly workloads. Expected:
- 10-20 agents: No issues
- 50+ agents: Consider sharding by project
- 100+ agents: May need database (D1/Postgres)

---

## Recommendations

### For Small Teams (2-5 users)
- ✅ Git-based sync (simple, reliable)
- ✅ GitHub private repo
- ✅ Docker containers or bare metal
- ✅ Manual git sync if needed

### For Medium Teams (5-20 users)
- ✅ Git-based sync with Cloudflare Workers
- ✅ R2 caching for fast reads
- ✅ OAuth for multi-tenant
- ✅ Monitoring for conflicts

### For Large Scale (20+ users)
- Consider Cloudflare D1 (SQL storage)
- Shard threads by project/team
- Advanced conflict resolution
- May need custom UI (beyond MCP clients)

---

## Next Steps

1. **Validate git sync locally** (2-3 concurrent users)
2. **Prototype Cloudflare Worker** (test GitHub API limits)
3. **Measure latency** under realistic load
4. **Gather user feedback** on async collaboration UX
5. **Iterate** based on real-world usage
6. Plan/define a `list_updates` tool (return topics updated since a timestamp/commit) to improve pull-based UX

---

## Conclusion

**The realistic watercooler cloud sync strategy:**

1. **Storage:** Git (GitHub/GitLab) as source of truth
2. **Sync:** Pull before reads, commit+push after writes
3. **Hosting:** Cloudflare Workers (optional, for edge perf)
4. **Caching:** R2 for fast reads (optional)
5. **Collaboration Model:** Async (not real-time)
6. **Latency:** 500ms-1s per operation
7. **Conflicts:** Git handles automatically (append-only)

**This works within MCP constraints and provides solid async collaboration for distributed teams.**
