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

### Pre-write / Read Refresh
1. Resolve code context and threads directory (`resolve_thread_context`).
2. Instantiate or reuse `GitSyncManager`. If the local checkout was removed,
   `_ensure_local_repo_ready()` re-clones (or re-initialises) the threads repo
   before any git commands execute.
3. Perform repository bootstrap as
   described above.
4. Ensure the threads branch matches the code branch (`ensure_branch`).
   - When the remote branch already exists, `ensure_branch` fetches it and sets
     upstream tracking so the local branch is fast-forward to the remote tip
     before any commits occur.
5. If the code branch is published, require a successful `git pull --rebase
   --autostash`. Failure (network outage, auth error, rebase conflict) raises
   `GitPullError` and cancels the operation. When the code branch is local-only,
   pull is skipped gracefully. If the remote threads repo exists but has no
   refs yet (brand new project), the pull is also skipped so the first commit
   can establish upstream state.

### Write (say/ack/handoff/set_status)
1. Repeat the pre-write refresh.
2. Execute the requested operation (append entry, update status, etc.).
3. Stage and commit all changes in the threads repo root.
4. If the code branch is published:
   - Verify the remote is reachable using `git ls-remote origin` (after any
     auto-provision attempt).
   - Push with retry-on-rejection. Network/auth failures cause
     `GitPushError`; rejections trigger pull + retry up to three times before
     failing.
5. If the code branch is local-only, keep commits local. Once the code branch is
   published, the next write will push the backlog.

### Post-Write Accounting
- Every commit records the commit footers from `_build_commit_footers`, including
  topic, ULID, code repo/branch, code commit SHA, and agent spec.
- Callers should surface any `GitPullError`/`GitPushError` details to the agent
  so they can retry after resolving connectivity issues.

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
