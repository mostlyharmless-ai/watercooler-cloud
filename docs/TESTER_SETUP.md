# Watercooler – Tester Setup (Universal Dev Mode)

This guide shows how a tester can install and run the local MCP server with zero per‑project configuration. The MCP discovers the correct threads repository and branch from the code context you pass on each call.

## Prerequisites
- Python 3.10+
- Git + SSH access to GitHub (or PAT if using HTTPS)
- Access to the paired threads repository named `{org}/{repo}-threads`

## Install (local repo build)
```bash
# In the watercooler-cloud repo
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[mcp]
```

## Register MCP in Claude (user-scope)
One-line command (context-aware, no per‑project config):
```bash
claude mcp add --transport stdio watercooler-dev --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_BASE="$HOME/.watercooler-threads" \
  -e WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python3 -m watercooler_mcp
```

Alternate (guarantee latest code from this repo file):
```bash
claude mcp add --transport stdio watercooler-dev --scope user \
  -e WATERCOOLER_AGENT="Claude@Code" \
  -e WATERCOOLER_THREADS_BASE="$HOME/.watercooler-threads" \
  -e WATERCOOLER_THREADS_PATTERN="git@github.com:{org}/{repo}-threads.git" \
  -e WATERCOOLER_AUTO_BRANCH=1 \
  -- python3 /path/to/watercooler-cloud/src/watercooler_mcp/server.py
```

## Required Call Parameters
To avoid ambiguity across repos/branches, every call must provide:
- `code_path`: the code repo root (e.g., `"."` when Claude runs in the repo, or an absolute path)
- `agent_func` (writes only): identity as `"<AgentBase>:<spec>"` (e.g., `"Claude:pm"`)

Examples:
```text
# Identity
watercooler_v1_whoami

# Health (shows threads dir)
watercooler_v1_health(code_path=".")

# List / Read
watercooler_v1_list_threads(code_path=".")
watercooler_v1_read_thread(topic="trial-run", code_path=".")

# Write (explicit identity)
watercooler_v1_say(topic="trial-run", title="Dev server OK", body="Spec: pm — universal mode", role="pm", code_path=".", agent_func="Claude:pm")
watercooler_v1_ack(topic="trial-run", title="Ack", code_path=".", agent_func="Claude:pm")
watercooler_v1_handoff(topic="trial-run", note="Your turn", target_agent="Codex", code_path=".", agent_func="Claude:pm")
watercooler_v1_set_status(topic="trial-run", status="IN_REVIEW", code_path=".", agent_func="Claude:pm")
```

## Expected Behavior
- Threads repo clone: `~/.watercooler-threads/{org}/{repo}-threads`
- Branch mirroring: same branch name as your code repo; created on demand
- Commit footers on writes: `Code-Repo`, `Code-Branch`, `Code-Commit`, `Watercooler-Entry-ID`, `Watercooler-Topic`, and `Spec`
- say() also adds `<!-- Entry-ID: ... -->` in the body for idempotency

## Troubleshooting
- Seeing a repo‑local `./.\watercooler` path? You’re running an older server or missing `code_path`:
  - Reinstall to ensure latest server: `pip install -e .[mcp]`
  - Or point Claude to the repo file: `-- python3 /path/to/src/watercooler_mcp/server.py`
  - Always pass `code_path` (or set `WATERCOOLER_GIT_REPO` to force a specific threads repo)
- Do not set `WATERCOOLER_DIR` on this server; it forces legacy behavior

## One‑Minute Validation
1) `watercooler_v1_whoami`
2) `watercooler_v1_health(code_path=".")` → Threads Dir under `~/.watercooler-threads/{org}/{repo}-threads`
3) `watercooler_v1_list_threads(code_path=".")`
4) `watercooler_v1_say(..., code_path=".", agent_func="Claude:pm")`
5) Terminal: `cd ~/.watercooler-threads/{org}/{repo}-threads && git log -1 --pretty=raw` → footers present

