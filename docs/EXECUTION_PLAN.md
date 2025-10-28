# Watercooler — One‑Rollout Plan (Elegant, Git‑Native, By Dawn)

Guiding principles
- Keep it simple: one universal dev server; zero per‑project MCP config.
- Git is the source of context: derive repo, branch, commit from the code workspace.
- Shadow model: the threads repo is a straightforward shadow of the code repo, branch‑for‑branch.
- Immutable linkage: every write records Code‑Repo/Branch/Commit; conflict policy is git‑friendly.

Roles
- Claude — GitHub/system integration, repo settings, user config snippets, external coordination.
- Codex — Design integrity, implementation, docs, and end‑to‑end functional validation.

---

Objective (single rollout)
- Deliver a universal, context‑aware MCP that mirrors developer workflow across repos and branches with no per‑project setup.
- Mothball the remote stack (kept for reactivation) and fully document the new local‑first path.

Scope (what’s in)
- Universal dev mode: dynamic discovery of code repo + branch; dynamic threads repo resolution by pattern; optional auto‑branch ensure.
- Commit footers on all writes; idempotency marker on say; small push backoff.
- Clean user setup: one global MCP entry; identity pre‑flight rule.
- Docs updated coherently; legacy path left documented but marked mothballed.

Scope (what’s out for now)
- Full file‑space mirroring under threads (future option).
- Notifications; org‑wide cross‑project threads; hosted bus.

---

Implementation blueprint (minimal, powerful)

1) Universal dev mode — context discovery (Codex)
- Add dynamic threads repo resolution when `WATERCOOLER_GIT_REPO` is unset:
  - New env (all optional, with sensible defaults):
    - `WATERCOOLER_THREADS_BASE` (default: `~/.watercooler-threads`)
    - `WATERCOOLER_THREADS_PATTERN` (default: `git@github.com:{org}/{repo}-threads.git`)
    - `WATERCOOLER_AUTO_BRANCH` (default: `1` → ensure branch before write)
  - From the active code workspace (CWD) or `code_path` (future):
    - Repo root: `git rev-parse --show-toplevel`
    - Branch: `git rev-parse --abbrev-ref HEAD`
    - Commit: `git rev-parse --short HEAD`
    - Origin URL: `git remote get-url origin` → parse `{org}/{repo}`
  - Compose threads URL via pattern; local clone path: `{THREADS_BASE}/{org}/{repo}-threads` (auto‑clone/open).

2) GitSyncManager — make branch mirroring a first‑class feature (Codex)
- Add `ensure_branch(branch)`:
  - Checkout/create local branch; set upstream to `origin/<branch>` if missing; push `-u` on first creation.
- Integrate ensure_branch into write flow when `WATERCOOLER_AUTO_BRANCH=1`.
- Keep pull‑rebase + small exponential backoff on push rejections.

3) Tool flow — pull freshness and write linkage (Codex)
- Before list/read: discover context → open threads repo → (optional) ensure branch → pull.
- On write (say/ack/handoff/set_status):
  - Ensure branch (if enabled) → append → commit → push.
  - Commit message footers (always):
    - `Code-Repo: <org>/<repo>`
    - `Code-Branch: <branch>`
    - `Code-Commit: <short-sha>`
    - `Watercooler-Entry-ID: <ULID>`
    - `Watercooler-Topic: <topic>`
  - say(): also append `<!-- Entry-ID: <ULID> -->` in the entry body for idempotency.

3a) Identity enforcement in the new local server (Codex)
- Add optional write‑time identity guard toggled by env:
  - `WATERCOOLER_REQUIRE_IDENTITY=1` → writes must resolve a non‑default identity (base + spec) or fail fast with a helpful error.
- Identity sources (strongest → weakest):
  1) Tool parameters: `agent_base`, `spec`
  2) HTTP headers: `X-Agent-Name`, `X-Agent-Spec`
  3) Env vars: `WATERCOOLER_AGENT`, `WATERCOOLER_SPEC`
  4) Client ID mapping (e.g., “Claude Desktop” → “Claude”)
  5) Fallback ("Agent") — rejected when enforcement is on
- Add local `watercooler_v1_set_agent` to persist identity (small JSON under user dir) for session continuity.

4) Backwards compatibility & toggles (Codex)
- If `WATERCOOLER_GIT_REPO` is set → use it (explicit override) and skip pattern resolution.
- Let users pin `WATERCOOLER_CODE_REPO` when origin parsing is atypical.
- Disable branch ensure via `WATERCOOLER_AUTO_BRANCH=0` if desired.

5) Unified user setup (Claude & Codex)
- Register one global MCP entry (user scope):
  - `claude mcp add --transport stdio watercooler-dev --scope user \
    -e WATERCOOLER_AGENT="Claude@Code" \
    -e WATERCOOLER_THREADS_BASE="$HOME/.watercooler-threads" \
    -e WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git" \
    -- python3 -m watercooler_mcp`
  - (Optional) Codex CLI equivalent:
    - `codex mcp add watercooler-dev \
       -e WATERCOOLER_AGENT=Codex \
       -e WATERCOOLER_THREADS_BASE=$HOME/.watercooler-threads \
       -e WATERCOOLER_THREADS_PATTERN=git@github.com:{org}/{repo}-threads.git \
       -- python3 -m watercooler_mcp`
- Identity pre‑flight rule: call `watercooler_v1_set_agent(base="Claude|Codex", spec="<pm|planner|implementer|tester|docs|ops|general-purpose>")` before any write.

6) Documentation and protocol (Codex)
- Update `docs/LOCAL_QUICKSTART.md` with “Universal dev mode” and the single add command above.
- Keep `docs/BRANCH_PAIRING.md` as the conceptual anchor.
- Ensure `AGENTS.md` and `~/.claude/CLAUDE.md` reflect identity pre‑flight and branch pairing.
- Keep remote path mothballed in `docs/DEPLOYMENT_QUICK_START.md`.

7) Functional validation (team)
- Repo switch: cd into two different code repos; run list/read/say; confirm threads resolve to `{repo}-threads` automatically.
- Branch switch: checkout `feature/x` then write; verify threads branch is `feature/x` (auto‑created on first push) and footers show correct branch/commit.
- Contention: two clients write within 1–3s; confirm union merges; push backoff reduces retries.
- Offline: write while offline, reconnect, push; verify branch and footers.
- Identity: verify header author reflects `set_agent`; no “Entry: Agent (…)” defaults.

8) Cutover & rollback (Claude)
- Cutover: share one‑liner setup; retire per‑project configs (optional); keep remote path mothballed.
- Rollback: set `WATERCOOLER_GIT_REPO` explicitly to force the old behavior or re‑enable the remote stack using the Reactivation Playbook.

Acceptance (by dawn)
- One universal dev MCP entry configured; identity rule followed.
- All list/read/write operations infer repo/branch from git and operate on the correct threads repo/branch without manual config.
- Every write carries Code‑Repo/Branch/Commit footers; say entries include body Entry‑ID.
- Functional tests across multiple repos/branches complete with seconds‑level propagation and no manual conflicts.
 - Identity enforcement (when enabled): no writes with “Entry: Agent (…)”; effective base/spec present in each write.

Notes on future elegance (post‑rollout)
- Path‑scoped topics: allow storing topics in subpaths mirroring code filespace; requires recursive listing and path‑friendly topic IDs.
- Notifications: tiny GH Action for Slack; keep storage model unchanged.
- Thin hosted bus: if sub‑second awareness is ever required; preserve git storage.
