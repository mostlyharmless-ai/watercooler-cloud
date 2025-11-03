# Threads Repository Lifecycle

This document captures the authoritative lifecycle for pairing a code repository
with its sibling `<repo>-threads` repository, covering every combination of
local/remote state, branch publication, and auto-provisioning. It defines the
sequence of operations the MCP server must perform before and after each
threads write so that conversations remain consistent with their paired code
history.

## Terminology
- **Code repo** – the git repository containing application code.
- **Threads repo** – the companion git repository (named `<repo>-threads`).
- **Local clone** – the on-disk checkout used by the MCP server or CLI.
- **Remote** – the upstream git hosting service (GitHub, GitLab, etc.).
- **Published branch** – a code branch with an upstream tracking ref
  (`branch@{upstream}` exists). When the code branch is published, the
  threads branch must sync with the remote; otherwise entries stay local until
  the code branch is promoted.

## Repository Bootstrap Matrix

| Remote threads repo | Local clone present | Auto-provision | Action sequence |
|---------------------|---------------------|----------------|-----------------|
| ✅ Accessible        | ✅ Yes              | _N/A_          | Reuse existing checkout; configure git user. |
| ✅ Accessible        | ❌ No               | _N/A_          | `git clone` → configure git user. |
| ❌ Missing          | ✅ Yes              | `0` / unset    | Keep local repo; operate in local-only mode (no pushes). |
| ❌ Missing          | ❌ No               | `0` / unset    | `git init` → add `origin` remote for later promotion. |
| ❌ Missing          | ❌ No               | `1`            | Run `WATERCOOLER_THREADS_CREATE_CMD` → reattempt clone. |
| 🚫 Unreachable      | any                 | any            | Abort operation; surface `GitPullError`/`GitPushError` so the caller can retry once connectivity returns. |

Notes:
- Auto-provisioning is enabled by default; set
  `WATERCOOLER_THREADS_AUTO_PROVISION=0` to disable it.
- Auto-provisioning only triggers for SSH remotes in dynamic contexts (no
  explicit `WATERCOOLER_DIR`).
- When provisioning succeeds, the clone is retried immediately. If the repo is
  still unavailable, we fall back to local init but record the provisioning
  output for diagnostics.
- “Unreachable” includes network failures, sandbox denials, or authentication
  errors. These are fatal for published branches because we must never advance
  the conversation without first syncing with the remote state.

## Branch Instantiation & Sync States

| Code branch state        | Threads branch state                | Expected behaviour |
|-------------------------|-------------------------------------|--------------------|
| Not published (no upstream) | Branch missing locally & remotely    | Create local branch (`git checkout -b`). No remote pull/push. |
| Not published            | Branch already local                | Reuse local branch, skip remote interaction. |
| Published, remote branch present | Local branch missing            | `git checkout -b <branch>` then set upstream (`git push -u origin <branch>`). |
| Published, remote branch present | Local branch present without upstream | `git branch --set-upstream-to=origin/<branch>` and pull. |
| Published, remote branch missing | Local branch present            | Create branch locally; first push will promote it when remote becomes available. |

The MCP server automatically calls `GitSyncManager.ensure_branch(branch)` when
`WATERCOOLER_AUTO_BRANCH` is enabled (default). This helper creates the branch
if needed, keeps the working copy on the correct branch, and configures tracking
when the remote is available.

## Operation Sequences

Watercooler supports two synchronization modes that share the same safety
guarantees. Synchronous mode performs all git operations inline (legacy
behaviour). Async mode records commits locally and lets a background worker pull
and push in batches. Async mode is the default on Windows and can be enabled
everywhere via `WATERCOOLER_ASYNC_SYNC=1`.

### Common groundwork
1. Resolve code context and threads directory (`resolve_thread_context`).
2. Instantiate or reuse `GitSyncManager`. If the local checkout was removed,
   `_ensure_local_repo_ready()` re-clones (or re-initialises) the threads repo.
3. Perform repository bootstrap as described earlier (provisioning, init,
   remote detection).
4. Ensure the threads branch matches the code branch (`ensure_branch`). When the
   remote branch already exists, `ensure_branch` fetches it and sets upstream
   tracking so the local branch is aligned with the remote tip before new
   commits are recorded.

### Synchronous mode (legacy)
1. Pull latest (`git pull --rebase --autostash`). Failure raises `GitPullError`.
2. Execute the operation (append entry, status update, etc.).
3. Stage, commit, and push with retry (`commit_and_push`). Network/auth failures
   raise `GitPushError`; concurrent pushes trigger pull + retry up to three
   times before failing.
4. Local-only branches stop after the commit; once the branch is published the
   next write will push the backlog automatically.

### Async mode
1. Execute the operation immediately—no blocking pull.
2. Stage and commit locally (`commit_local`). Each entry still maps to a single
   git commit with the canonical footer block.
3. Enqueue the commit for the async worker. The queue persists to
   `.watercooler-pending-sync/queue.jsonl`.
4. The worker runs continuously:
   - Performs a background pull every `WATERCOOLER_SYNC_INTERVAL` seconds to keep
     read operations fresh without blocking the caller.
   - Pulls with rebase before pushing (preserves conflict guarantees) when local
     commits are queued.
   - Pushes all queued commits in a single operation.
   - Retries with exponential backoff on network failures.
5. Priority operations trigger an immediate flush (ball hand-offs, `say` calls,
   `set_status(..., CLOSED)`). Other writes flush on the 5‑second batch window,
   when 50 commits are queued, or after a 30‑second ceiling.
6. `flush_now` / `watercooler sync --now` forces an immediate push, and
   `list_threads` surfaces a ⏳ marker for entries awaiting sync.
7. `list_threads` and `read_thread` return immediately using the cached view,
   annotating the output with the last refresh age and pending local updates.

### Post-write accounting
- Every commit records the standard footer block (`Watercooler-Entry-ID`,
  `Watercooler-Topic`, `Code-*`, `Spec`).
- Async mode logs auto-merges as system entries whenever the worker replays
  concurrent commits.
- Errors captured during async flush (pull/push) bubble up as `GitPushError`
  when a priority flush is requested so agents can react immediately.

## Async Configuration

Environment variables controlling async behaviour:

| Variable | Default | Notes |
|----------|---------|-------|
| `WATERCOOLER_ASYNC_SYNC` | auto (`1` on Windows, `0` elsewhere) | Force async (`1`) or synchronous (`0`) mode. |
| `WATERCOOLER_BATCH_WINDOW` | `5` seconds | Soft delay before batching commits. |
| `WATERCOOLER_MAX_BATCH_DELAY` | `30` seconds | Hard ceiling; worker flushes even if retries are pending. |
| `WATERCOOLER_MAX_BATCH_SIZE` | `50` commits | Flush once this many pending commits accumulate. |
| `WATERCOOLER_MAX_SYNC_RETRIES` | `5` | Push retry attempts per flush cycle. |
| `WATERCOOLER_MAX_BACKOFF` | `300` seconds | Maximum backoff delay after repeated failures. |
| `WATERCOOLER_SYNC_INTERVAL` | `30` seconds | Background pull cadence that keeps reads fresh. |
| `WATERCOOLER_STALE_THRESHOLD` | `60` seconds | Age after which `list_threads` marks the cache as stale. |

Queue files live next to the threads repo (`.watercooler-pending-sync/`). Each
line stores the commit metadata plus a checksum so the worker can resume safely
after crashes. Removing the directory is safe—the next write will re-create it.

## Failure Modes & Recovery

| Failure | Detection | Response |
|---------|-----------|----------|
| Network/auth failure reaching remote | `git ls-remote` or `git push` fails | Abort with `GitPullError`/`GitPushError`. User re-runs after restoring connectivity. |
| Remote branch deleted upstream | `git pull` reports “could not find remote ref” | Treat as non-fatal; continue locally until remote branch is recreated. |
| Rebase conflict | `git pull --rebase` exits 1 | Abort, run `git rebase --abort`, then investigate conflict manually before retrying. |
| Provisioning misconfigured | Provision command exits non-zero | Raise `GitSyncError` during bootstrap with captured stderr. |

## Implementation References
- `GitSyncManager._initialise_repository` – clones or bootstraps the threads repo.
- `GitSyncManager._ensure_remote_repo_exists` – detects remote availability,
  auto-provisions when enabled, records diagnostic errors, and flags brand-new
  remotes with no refs so the initial pull can be skipped safely.
- `GitSyncManager.pull` – enforces remote synchronization before reads/writes.
- `GitSyncManager.commit_and_push` – stages, commits, and pushes with retry,
  honouring the local-only mode for unpublished branches.
- `GitSyncManager.ensure_branch` – keeps the threads branch aligned with the
  code branch and configures upstream tracking.
- `server.run_with_sync` – wraps agent operations with the pull/commit/push flow.

Keep this document aligned with the implementation: every code change affecting
bootstrap, branching, or sync policy must update both this lifecycle and the
associated tests under `tests/test_git_sync.py`.

## Appendix: Why Not Unify Code and Threads Repos?

Watercooler intentionally maintains a sibling repository (`<repo>-threads`)
rather than colocating collaboration history inside the code repository.

**Reasons:**
- **Signal preservation** – application commits stay focused on code while
  threads capture high-frequency planning and hand-offs without polluting the
  code history.
- **Operational isolation** – thread commits avoid triggering CI/CD pipelines,
  and the async queue can push independently of application deploys.
- **Access control** – collaboration logs often have different retention or
  sharing requirements than code; separate repos make policy enforcement easier.
- **Branch pairing semantics** – the “intentional sharing” contract (local
  branches stay local, published branches push) is clearer when collaboration
  history lives in a peer repo.

Alternatives considered:
- **Unified repo (`.watercooler/threads/` subdirectory)** – reduces git traffic
  but clutters code history and entangles CI pipelines.
- **Git notes** – keeps history clean but hides context behind tooling that most
  developers and hosted platforms don’t surface.

Given these constraints the sibling-pattern remains the most predictable option,
and the new async sync path removes the primary performance pain for Windows
without changing the repository contract.
