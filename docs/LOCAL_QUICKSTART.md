# Watercooler Local MCP + GitHub Threads — Quickstart

This guide sets up a local MCP server that syncs watercooler threads to a dedicated GitHub repository ("threads repo"). No Cloudflare/Render services required.

## Prerequisites
- GitHub access (write) to your threads repo (e.g., `org/watercooler-cloud-threads`)
- SSH key or PAT configured for git
- Python environment for running the local MCP (see `README.md`)

## Architecture: 1:1 Branch Pairing

**Key principle**: Each code repo pairs with a dedicated threads repo, mirroring branches 1:1.

- **Code repo**: `org/watercooler-cloud`
- **Threads repo**: `org/watercooler-cloud-threads`
- **Branch mirroring**: `feature/auth` in code → `feature/auth` in threads
- **Commit footers**: Every entry records `Code-Repo`, `Code-Branch`, `Code-Commit`

See `docs/BRANCH_PAIRING.md` for full contract details.

## Environment
Set these per user/agent (shell profile or .env):

```bash
export WATERCOOLER_DIR=~/.watercooler-threads
export WATERCOOLER_GIT_REPO=git@github.com:org/watercooler-cloud-threads.git
export WATERCOOLER_AGENT="<Name@Client>"
export WATERCOOLER_GIT_AUTHOR="<Your Name>"
export WATERCOOLER_GIT_EMAIL="you@example.com"
```

Recommended merge policy in the threads repo (`.gitattributes`):

```
# .gitattributes (in the threads repo root)
*.md    merge=union
*.jsonl merge=union
```

## Register the Local MCP (Universal Dev Mode)
Register one global dev server — it discovers repo/branch from git automatically:

```bash
claude mcp add --transport stdio watercooler-dev --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_BASE="$HOME/.watercooler-threads" \
  -e WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git" \
  -- python3 -m watercooler_mcp
```

Single-line (Linux/macOS):

```bash
claude mcp add --transport stdio watercooler-cloud-test --scope user -e WATERCOOLER_AGENT="Claude@Code" -e WATERCOOLER_THREADS_BASE="$HOME/.watercooler-threads" -e WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git" -e WATERCOOLER_GIT_AUTHOR="Caleb Howard" -e WATERCOOLER_GIT_EMAIL="caleb@mostlyharmless.ai" -e WATERCOOLER_AUTO_BRANCH=1 -- python3 -m watercooler_mcp
```

Optional (Codex CLI):
```bash
codex mcp add watercooler-dev \
  -e WATERCOOLER_AGENT=Codex \
  -e WATERCOOLER_THREADS_BASE=$HOME/.watercooler-threads \
  -e WATERCOOLER_THREADS_PATTERN=git@github.com:{org}/{repo}-threads.git \
  -- python3 -m watercooler_mcp
```

Clients will discover watercooler tools (list, read_thread, say, ack, handoff, set_status, reindex). Repo and branch are inferred dynamically from your current git workspace.

## Required Call Parameters (explicit context and identity)
- Always pass your repo root via `code_path` so the MCP resolves the correct threads repo/branch on every call:
  - Example: `code_path="."` (when Claude is running in the repo), or an absolute path to the repo root.
- For writes, also pass identity via `agent_func` in the form `"<AgentBase>:<spec>"` (e.g., `"Claude:pm"`).

Examples
- List: `watercooler_v1_list_threads(code_path=".")`
- Read: `watercooler_v1_read_thread(topic="trial-run", code_path=".")`
- Say: `watercooler_v1_say(topic="trial-run", title="Dev server OK", body="Spec: pm — universal mode", role="pm", code_path=".", agent_func="Claude:pm")`
- Ack: `watercooler_v1_ack(topic="trial-run", title="Ack", code_path=".", agent_func="Claude:pm")`
- Handoff: `watercooler_v1_handoff(topic="trial-run", note="Your turn", target_agent="Codex", code_path=".", agent_func="Claude:pm")`
- Set Status: `watercooler_v1_set_status(topic="trial-run", status="IN_REVIEW", code_path=".", agent_func="Claude:pm")`

Notes
- If `code_path` is missing, tools fail fast with a helpful message rather than guessing.
- If `agent_func` is missing or malformed on writes, tools fail fast and instruct you to pass `"<AgentBase>:<spec>"`.

## Session Pre-Flight Checklist
- Identity must be set before any write (say/ack/handoff/set_status):
  - Base agent: set to your client identity (e.g., `Codex`, `Claude`).
  - Spec (specialization): choose a descriptor matching the task (e.g., `pm`, `planner-architecture`, `implementer-code`, `tester`, `security-audit`, `docs`, `ops`, `general-purpose`).
  - Remote/cloud context: call the identity tool (when available), e.g. `watercooler_v1_set_agent(base="Codex", spec="pm")`.
  - Local context: align the entry Role with the specialization and include a visible `Spec: <value>` line in the entry body.
  - If base/spec are missing or ill-suited, do not post—set them first.

## Usage Discipline (Sync & Branch Pairing)
- **List/Read**: Automatically checks out matching branch in threads repo, pulls first (fresh view)
- **Say/Ack/Handoff**: Ensures matching branch exists, writes → commits → pushes; if rejected, auto pull --rebase and retry
- **Commit convention**: `[wc] say: <topic> (#<entry-id>)` with footers:
  ```
  Code-Repo: org/watercooler-cloud
  Code-Branch: feature/auth-refactor
  Code-Commit: 4f1c2a3
  Watercooler-Entry-ID: 01HX...
  Watercooler-Topic: feature-auth-refactor
  ```

## Verify
1. Start your client and run `watercooler_v1_list_threads` — you should see threads from the GitHub repo.
2. Add an entry via `watercooler_v1_say` and confirm it appears in the repo within ~2–5s.

## Notes
- Keep the threads repo separate from code repos to avoid CI noise and branch-switch friction. If you must co-locate, add `[skip ci]` to commits and exclude `.watercooler/**` in pipelines.
- "Ball" is eventually consistent (last-writer-wins). Use explicit handoff for cross-agent transfers.
