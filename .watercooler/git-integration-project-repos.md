---
Entry: Codex (caleb) 2025-10-25T00:22:00Z
Type: Plan
Title: Integrate Watercooler activity into project repos (design & rollout)

Scope
- Replace/augment dedicated threads repo with per‑project integration that keeps activity continuous and anchored to commits/PRs.

State
- Backend stores threads on disk (per user/project). Optional GitSync targets a single threads repo.

Goals
- Associate conversations to code (commits/PRs/branches) without polluting main diffs.
- Keep activity continuous; publish in batched, safe way.
- Support both local workspaces and central cloud projection.

Design (Recommended)
- Phase 1: Dedicated branch `watercooler` in each project repo; project mapping in KV → { repo_url, wc_branch }.
- Layout: `watercooler/index.json`, `watercooler/threads/<year>/<id>.md` with frontmatter anchors (commits/branch/PR/files).
- Push cadence: debounce (30–60s) and batch; bot identity; rebase+retry on conflict.
- Surface in PRs: minimal comment + link (Phase 2), optional Check.
- Advanced: Git notes for summaries (opt‑in) while keeping full content on branch.

Local vs Central
- Local: `.watercooler/` always active; `.gitignore` by default; `wc publish` to copy curated threads to project (PR or watercooler branch).
- Central: Backend clones repo and pushes to `watercooler` branch only.

Security
- GitHub App with limited repo permissions; no changes to protected default branches.

Rollout
1) Pilot on 1–2 repos; configure mapping; validate churn.
2) Add PR surfacing; owner feedback; adjust cadence.
3) Ship developer CLI (`wc publish`) and optional hooks.
4) Consider Git notes as opt‑in.

References
- Code: src/watercooler_mcp/git_sync.py, src/watercooler_mcp/config.py, cloudflare-worker/src/index.ts (cron trigger)
- Remote thread: git-integration-project-repos

