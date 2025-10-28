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
- Code branch renamed: first write auto‑creates the new threads branch; history remains
- Heavy concurrency: start with one file per topic and `*.md merge=union`; switch to per‑entry files only if conflicts are frequent

