# Watercooler Branch Pairing Contract

This document defines a simple, durable pairing between a code repository and its watercooler threads repository. It enables tight linkage between code changes and conversations with minimal moving parts.

## Principles
- 1:1 Repositories: Each code repo pairs with exactly one threads repo.
- 1:1 Branches: Each code branch has a same‑named branch in the threads repo.
- Ground Truth: Every thread entry commit records the code branch and exact commit SHA.

## Pairing
- Pair: `code: <org>/<repo>` ↔ `threads: <org>/<repo>-threads`
- Branch mirror: `code:<branch>` ↔ `threads:<branch>`
- Topics: Files at the root of the threads branch (one file per topic)

## Client Behavior (Local MCP)
### Read/List
1) Detect current code branch (if inside a git repo)
2) Checkout/create the same branch in the threads repo
3) Pull latest, then list/read

### Write (say/ack/handoff/set_status)
1) Ensure a same‑named branch exists in the threads repo
2) Append entry and commit
3) Push with rebase + retry on rejection
4) Include the following footers in the commit message:
```
Code-Repo: <org>/<repo>
Code-Branch: <branch>
Code-Commit: <short-sha>
Watercooler-Entry-ID: <ULID>
Watercooler-Topic: <topic>
```

## Why this is effective
- Clean separation: No CI noise in the code repo; threads can be chatty
- Strong linkage: Branch name + commit SHA make relationships verifiable
- Natural workflow: Checking out a code branch naturally scopes threads
- Minimal friction: No hosted infra needed; just consistent git discipline

## Authoring Rules
- Topic slugs are flat (e.g., `feature-auth-refactor`)
- Entries include a visible `Spec: <value>` (session specialization) and a Role aligned to the spec
- Include code pointers in body when relevant (branch, commit, PR)

## Closure Strategy
- On code PR merge:
  - Option A (simple): Post a Closure entry on the threads branch referencing the merged PR
  - Option B (optional): Merge the threads branch into `threads:main` with a summary; only if you want a canonical main log

## Edge Cases
- Not in a git repo: default to `threads:main`
- Code branch renamed: first write auto-creates the new threads branch; history remains
- Heavy concurrency: start with one file per topic and `*.md merge=union`; switch to per-entry files only if conflicts are frequent
- Threads repo missing: enable `WATERCOOLER_THREADS_AUTO_PROVISION` and provide
  `WATERCOOLER_THREADS_CREATE_CMD` so the MCP server can run your approved
  provisioning command when the initial clone fails. Otherwise, create the
  `<repo>-threads` repository manually before writing.

## Real-World Example: v0.1.0 Launch (November 2025)

This section documents the actual execution of the branch pairing protocol during the watercooler-cloud v0.1.0 open source launch.

### Context
- **Code Repo**: `mostlyharmless-ai/watercooler-cloud`
- **Threads Repo**: `mostlyharmless-ai/watercooler-cloud-threads`
- **Branch Pair**: `open-source-prep` (both repos)
- **Goal**: Merge both branches to `main` following branch pairing protocol

### Execution Timeline

**Phase 1: Code Repo Merge**
1. PR #7 created: `open-source-prep` → `main` in watercooler-cloud
2. All CI tests passing (81 tests across Python 3.10-3.12)
3. PR merged via GitHub UI
4. Tagged v0.1.0 on merged main (commit 383d50b)
5. Repository made public

**Phase 2: Threads Repo Merge**
- **Initial assumption**: threads already merged ❌
- **Reality**: `threads:main` had 1 file, `threads:open-source-prep` had 21 files
- **Critical learning**: Merging code branch does NOT automatically merge threads branch
- **Action required**: Explicit manual merge of threads branch

### Technical Details

**Command that worked:**
```bash
cd /path/to/watercooler-cloud-threads && \
  git checkout main && \
  git pull origin main && \
  git merge open-source-prep --no-ff -m "Merge open-source-prep threads to main following branch pairing protocol" && \
  git push origin main
```

**Why this approach:**
- **Absolute path with chained commands**: Working directory can reset between separate commands in some tool contexts
- **`--no-ff` flag**: Preserve branch history even when fast-forward possible
- **Explicit message**: Document protocol adherence in commit message

**Merge Result:**
- Commit: 104eab8
- Files merged: 21 threads
- Insertions: 8,696 lines
- Auto-merged: `open-source-launch.md` (updated on both branches)
- Merge strategy: `ort` (default, worked well)

### Key Learnings

1. **Branch pairing is not automatic** - Merging code branch does NOT trigger threads branch merge. Must explicitly merge threads branch separately.

2. **Timing matters** - Merge threads branch immediately after code branch to keep repos synchronized and prevent confusion.

3. **Working directory gotchas** - Individual `cd` commands may not persist across tool invocations. Solution: Use absolute paths + chained commands with `&&`.

4. **Merge message is documentation** - Explicit mention of "branch pairing protocol" helps future maintainers understand the why.

### Best Practices from This Execution

**When merging code branch → main:**
1. ✅ Merge code PR
2. ✅ Tag release on code repo (if applicable)
3. ✅ **Immediately** merge corresponding threads branch
4. ✅ Verify both repos show merged state

**Merge command template:**
```bash
# In threads repo
git checkout main
git pull origin main
git merge <branch-name> --no-ff -m "Merge <branch-name> threads to main following branch pairing protocol"
git push origin main
```

**Verification checklist:**
- [ ] Code branch merged to main
- [ ] Threads branch merged to main
- [ ] Both repos pushed to remote
- [ ] File counts match expectations
- [ ] Git log shows merge commits on both repos

### Future Automation Opportunities

**GitHub Actions workflow** (possible enhancement):
- Trigger on: code repo branch merge to main
- Action: Automatically merge corresponding threads branch or open PR
- Benefits: Enforces protocol, prevents human error
- Risks: Could merge threads with conflicts or outdated state

**Git hook approach**:
- Pre-push hook in code repo
- Check if corresponding threads branch exists and is ahead of main
- Warn if threads branch not merged

**MCP Server enhancement**:
- Watch for code branch state changes
- Prompt user to merge corresponding threads branch
- Verify both repos are synchronized

### Related Documentation
- Thread: `github-threads-integration` - Contains detailed case study of this execution
- Thread: `branch-lifecycle-mapping` - Comprehensive branch operations planning
- Thread: `open-source-launch` - The actual launch planning and execution
