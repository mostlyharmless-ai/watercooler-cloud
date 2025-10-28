# [ARCHIVED] Cloudflare Remote MCP Playbook (Authorization‑First, Proxy‑First)

> Archived with the remote stack. Preferred path: local stdio MCP universal
> dev mode. See docs/TESTER_SETUP.md and docs/LOCAL_QUICKSTART.md.

Intent: Make authorization the primary objective while exposing the existing watercooler‑collab MCP server as a Remote MCP behind Cloudflare Workers—without changing tool logic. Use a Cloudflare Worker to provide the Remote MCP transport (SSE/Streamable HTTP) and enforce identity via OAuth first (best compatibility with `mcp-remote`), with Cloudflare Access as an optional, defense‑in‑depth layer. Proxy tool calls to the current Python backend.

TL;DR (Auth‑First)
- Keep all Python tool logic as‑is. Do not port code to TS.
- Stand up a Cloudflare Worker that implements Remote MCP endpoints and forwards to a Python backend (HTTP facade).
- Use the GitHub OAuth Remote MCP template as the default path (best support for desktop clients via `mcp-remote`).
- Optionally layer Cloudflare Access after OAuth works (org SSO, defense in depth). Be aware of header/cookie constraints for CLI clients.
- Point Claude/Cursor at the Worker via mcp‑remote.

---

## 0) Why Authorization‑First

- Compatibility: `mcp-remote` cleanly supports the OAuth flow (first connection opens browser). Cloudflare Access alone may require service tokens or custom headers that typical clients do not inject.
- Identity: OAuth provides a per‑user identity you can map directly to entry authorship and policy.
- Defense‑in‑depth: Add Cloudflare Access after OAuth if you want org‑scoped SSO in front of the Worker domain. Validate that your clients can satisfy Access (cookies/service tokens) without breaking `mcp-remote`.

---

## 1) Preconditions

- Repo: mostlyharmless-ai/watercooler-collab (Python FastMCP server and tools live here).
- Node 18+, npm, and wrangler installed locally.
- Cloudflare account with Workers + Access enabled.
- A reachable Python backend (private service) that exposes a thin HTTP facade for the MCP tools (details below). This reuses the same Python functions; no logic changes.

---

## 2) Architecture

```
Claude / Cursor
  └─ mcp-remote (local proxy)
      └─ https://<worker>.<account>.workers.dev/sse  (Cloudflare Worker: Remote MCP)
            └─ forwards tool calls over HTTPS → Python MCP backend (HTTP facade)
                   └─ invokes existing watercooler tools + file/git operations
```

Why proxy‑first?
- Cloudflare Workers cannot run CPython, subprocess, or a writable local FS. The repo’s tools use Python, the local filesystem (`.watercooler/`) and `git` (via subprocess).
- Proxying avoids any tool rewrite: the Worker only handles Remote MCP transport + auth, while Python keeps doing the work.

Multi‑tenancy (Per‑User / Per‑Project)
- Identity comes from OAuth (user id/handle/email).
- Project selection is provided by the client via query param `?project=<id>` while keeping the path `/sse` (maintains template compatibility), or by separate `mcpServers` entries per project.
- Worker enforces authorization: user → allowed projects (lookup via KV/D1) and forwards headers `X-User-Id`, `X-Agent-Name`, `X-Project-Id` to the backend.
- Backend selects per‑project storage (threads dir or git repo) based on `X-Project-Id` and invokes existing Python functions.

---

## 3) Python backend (HTTP facade)

Goal: Provide a minimal HTTP surface that maps 1:1 to existing MCP tools. Internally, call the same functions already used by the FastMCP server.

Required endpoints (suggested):
- `POST /mcp/watercooler_v1_health`
- `POST /mcp/watercooler_v1_whoami`
- `POST /mcp/watercooler_v1_list_threads`
- `POST /mcp/watercooler_v1_read_thread`  (body: `{ topic }`)
- `POST /mcp/watercooler_v1_say`          (body: `{ topic, title, body, role?, entry_type? }`)
- `POST /mcp/watercooler_v1_ack`          (body: `{ topic, title, body }`)
- `POST /mcp/watercooler_v1_handoff`      (body: `{ topic, note, target_agent? }`)
- `POST /mcp/watercooler_v1_set_status`   (body: `{ topic, status }`)
- `POST /mcp/watercooler_v1_reindex`

Implementation notes
- Reuse `watercooler` library and `src/watercooler_mcp/*` code; call the same functions used in `src/watercooler_mcp/server.py`.
- Respect existing env vars (`WATERCOOLER_DIR`, `WATERCOOLER_GIT_*`). See docs/ENVIRONMENT_VARS.md.
- Set agent identity per request from an HTTP header (e.g., `X-Agent-Name`) by temporarily overriding `WATERCOOLER_AGENT` or passing through to `get_agent_name(...)` if you adapt it.
- Recommended: lightweight FastAPI/Flask app with JSON in/out and 200/4xx/5xx semantics.

Per‑project selection (backend)
- Accept `X-Project-Id` and compute:
  - Local FS mode: `threads_dir = Path(BASE_THREADS_ROOT) / user_id / project_id`
  - Git mode: map `project_id` → `WATERCOOLER_GIT_REPO` (e.g., `git@github.com:org/<project_id>-threads.git`)
- Call watercooler commands with explicit `threads_dir` (preferred) to avoid global env mutation.

Example (pseudo‑Python):
```python
def derive_threads_dir(user_id: str, project_id: str) -> Path:
    return Path(os.environ.get("BASE_THREADS_ROOT", "/srv/watercooler")) / user_id / project_id

@app.post("/mcp/watercooler_v1_say")
def say_ep(req: SayPayload, x_agent_name: str = Header(None), x_project_id: str = Header(...), x_user_id: str = Header(...)):
    threads_dir = derive_threads_dir(x_user_id, x_project_id)
    threads_dir.mkdir(parents=True, exist_ok=True)
    return commands.say(
        topic=req.topic,
        title=req.title,
        body=req.body,
        threads_dir=threads_dir,
        role=req.role,
        entry_type=req.entry_type,
    )
```

Security
- Bind the backend on private network/VPC or behind a gateway. The Worker should be the only public entry point.
- Require an internal shared secret or mTLS between Worker and backend.

---

## 4) Cloudflare Worker (Remote MCP gateway)

Scaffold (OAuth‑first recommended)
```bash
npm create cloudflare@latest mharmless-remote-mcp -- --template=cloudflare/ai/demos/remote-mcp-github-oauth
cd mharmless-remote-mcp
npm install
npm start   # local dev on http://localhost:8788/sse
```

Configure wrangler (TOML preferred)
```toml
# wrangler.toml
name = "mharmless-remote-mcp"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[vars]
BACKEND_URL = "https://backend.internal.example" # Python HTTP facade

# Optional: forward a static fallback for agent identity if Access/OAuth missing
DEFAULT_AGENT = "Agent"

# Bindings for multi-tenant project authorization
[[kv_namespaces]]
binding = "KV_PROJECTS"
id = "<your_kv_id>"
```

OAuth secrets
```bash
# GitHub OAuth app for the Worker
npx wrangler secret put GITHUB_CLIENT_ID
npx wrangler secret put GITHUB_CLIENT_SECRET
# Ensure the OAuth app redirect matches the Worker URL (…/sse auth flow in template docs)
```

Project selection and authZ (Worker)
- Accept `?project=<id>` on the `/sse` URL and preserve the `/sse` path.
- Resolve user from OAuth session; look up allowed projects in `KV_PROJECTS` under key `user_id`.
- If project not provided, fall back to a per‑user default stored in KV (or reject).
- Enforce membership; on success, forward `X-Project-Id`, `X-User-Id`, and `X-Agent-Name` to the backend.

KV shape (example):
```json
{
  "user_id": "gh:octocat",
  "default": "proj-alpha",
  "projects": ["proj-alpha", "proj-beta"]
}
```

Forwarding logic (conceptual)
- On each MCP tool request, extract identity from Access/OAuth (see §4) and call the Python backend endpoint with:
  - JSON body that mirrors the tool parameters
  - Headers: `X-Agent-Name` (derived identity), plus any internal auth header
  - Timeouts tuned for streamable responses (use Streamable HTTP for long operations)

Auth gating (authorization‑first)
- Use the OAuth template as default so clients can authenticate interactively via browser.
- Layer Cloudflare Access afterwards if you need org‑wide SSO on the Worker domain. Validate `mcp-remote` compatibility (may need Access service tokens and a Worker shim to add headers).

---

## 5) Identity and authorization

OAuth (primary)
- Use `remote-mcp-github-oauth`. First connection opens browser; `mcp-remote` manages tokens client‑side.
- Derive `agent_name` from the OAuth identity (e.g., `github_login`, `name`, or `email`).
- Worker → backend: set `X-Agent-Name: <derived>` and include opaque session id for audit.

Cloudflare Access (optional, defense‑in‑depth)
- Put the Worker behind Access to require SSO for the domain. Note: CLI/desktop clients may not automatically include Access cookies.
- If using Access for programmatic clients, set up Access Service Tokens and a Worker adapter that injects `CF-Access-Client-Id`/`CF-Access-Client-Secret` or validates them server‑side.

Server behavior
- The existing server resolves agent identity as:
  1) `WATERCOOLER_AGENT` env var
  2) `client_id` from MCP Context
  3) fallback "Agent"
  To honor SSO/OAuth identity per request, prefer passing identity via header to the backend and mapping to the effective agent name for that request.

---

## 6) Environment & secrets (align with repo)

Use the repo’s variables from docs/ENVIRONMENT_VARS.md.

Core
- `WATERCOOLER_DIR` – threads directory root (server auto‑creates if missing)
- `WATERCOOLER_GIT_REPO` – enables git cloud sync (optional)
- `WATERCOOLER_GIT_SSH_KEY`, `WATERCOOLER_GIT_AUTHOR`, `WATERCOOLER_GIT_EMAIL`

Worker
- `BACKEND_URL` – private HTTPS URL for the Python facade
- `DEFAULT_AGENT` – optional fallback agent label
- `KV_PROJECTS` – KV binding used to store per‑user project ACLs and defaults

Cloudflare commands
```bash
npx wrangler secret put BACKEND_URL
```

Note: Prefer `wrangler.toml` over JSON. Avoid inventing new names like `WATERCOOLER_ROOT`/`REPO_PATH`; stick to `WATERCOOLER_DIR` and `WATERCOOLER_GIT_*` to match the server.

---

## 7) Client setup (`mcp-remote`)

Claude Desktop `settings.json`
```json
{
  "mcpServers": {
    "watercooler": {
      "command": "npx",
      "args": ["mcp-remote", "https://<worker>.<account>.workers.dev/sse?project=proj-alpha"]
    }
  }
}
```

Cursor: same command/args in MCP server config.

Alternative: define one `mcpServers` entry per project (distinct names) if you prefer not to pass `?project=`.

---

## 8) Validation & observability

Validation
1) `watercooler_v1_health` via MCP
2) `watercooler_v1_list_threads` → expect threads or an empty set
3) `watercooler_v1_say` on a test topic → confirm new entry appears
4) Switch projects (`?project=`) and repeat; ensure isolation (no cross‑project reads/writes)

Observability
- Use Worker logs to verify connect/disconnect and tool calls.
- Prefer Streamable HTTP for long‑running operations.
- For app‑level audit, continue emitting Watercooler cards in Python.

---

## 9) Migration checklist (authorization‑first)

1. Scaffold Worker from the GitHub OAuth Remote MCP template.
2. Configure OAuth app + secrets; verify browser sign‑in from client connect.
3. Stand up Python HTTP facade (private) mapping endpoints to existing tools (no logic changes).
4. Add per‑user/project KV: create `KV_PROJECTS`; write initial ACLs/defaults for tonight’s users/projects.
5. Configure Worker `BACKEND_URL` and KV bindings; deploy via `wrangler deploy`.
6. Connect with `mcp-remote` using `?project=<id>`; validate identity propagation (`X-Agent-Name`, `X-User-Id`, `X-Project-Id`) and core tools.
7. Flip projects and repeat; verify isolation and authorization errors for disallowed projects.
8. Optional: Add Cloudflare Access as a front gate; verify client compatibility (cookies/service tokens).
9. Optional: Enable `WATERCOOLER_GIT_REPO` for git sync in backend.
10. Document Worker URL, client config, auth and project selection expectations in docs.

---

## 10) Troubleshooting

- 401 at Worker: OAuth secrets or redirect mismatch; verify `GITHUB_CLIENT_ID/SECRET` and callback URL. If using Access, check policy and token/header handling.
- No tools in client: Ensure endpoint ends with `/sse` and that you’re using `mcp-remote`.
- Timeouts/long calls: Use Streamable HTTP variant in Worker; increase backend timeouts.
- Env not applied: Set/redeploy wrangler secrets/vars; confirm backend sees `WATERCOOLER_*`.
- Identity mismatch in entries: Ensure Worker sets `X-Agent-Name` and backend maps this to the effective agent.
- Project denied: Check `?project=` param, user’s ACL in KV, and Worker logic that enforces allowed project list.

---

## 11) Optional Phase 2 — Worker‑native execution (rewrite)

Only if you want to eliminate the Python backend:
- Re‑implement tool logic in TypeScript.
- Replace git subprocess with GitHub API or CF storage (R2/D1).
- Replace local `.watercooler/` with KV/R2/D1.
- This is a code rewrite; not needed for the Cloudflare auth cutover.

---

## Appendix A — Tool map (HTTP facade ↔ MCP)

| MCP tool | HTTP method | Path |
|----------|-------------|------|
| watercooler_v1_health | POST | /mcp/watercooler_v1_health |
| watercooler_v1_whoami | POST | /mcp/watercooler_v1_whoami |
| watercooler_v1_list_threads | POST | /mcp/watercooler_v1_list_threads |
| watercooler_v1_read_thread | POST | /mcp/watercooler_v1_read_thread |
| watercooler_v1_say | POST | /mcp/watercooler_v1_say |
| watercooler_v1_ack | POST | /mcp/watercooler_v1_ack |
| watercooler_v1_handoff | POST | /mcp/watercooler_v1_handoff |
| watercooler_v1_set_status | POST | /mcp/watercooler_v1_set_status |
| watercooler_v1_reindex | POST | /mcp/watercooler_v1_reindex |

---

## Appendix B — wrangler.toml (skeleton)

```toml
name = "mharmless-remote-mcp"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[vars]
BACKEND_URL = "https://backend.internal.example"
DEFAULT_AGENT = "Agent"

# Optional
# [placement]
# mode = "smart"
```

---

## Appendix C — Safety defaults

- Rate‑limit tool calls at the Worker (per IP/session).
- Redact sensitive env keys from error messages.
- If using OAuth/Access, log user identity (email/GitHub handle) with session ID.

---

## Appendix D — Tonight’s Implementation Plan (tight)

- 0:00–0:20 — OAuth Worker scaffold and secrets
  - Create from `remote-mcp-github-oauth`; set `GITHUB_CLIENT_ID/SECRET`.
  - `npm start`; validate local `/sse` OAuth handshake via `mcp-remote`.

- 0:20–0:50 — Python HTTP facade (thin)
  - Implement `/mcp/*` endpoints calling existing `watercooler` functions.
  - Support headers: `X-Agent-Name`, `X-User-Id`, `X-Project-Id`.

- 0:50–1:20 — Worker forwarder with project authZ
  - Bind `KV_PROJECTS` and write initial ACLs/defaults for target users/projects.
  - Accept `?project=`; enforce membership; forward headers to backend.

- 1:20–1:40 — Deploy + connect
  - Set `BACKEND_URL`; `wrangler deploy`.
  - Configure client `mcp-remote` with `?project=<id>`.

- 1:40–2:00 — Validate and harden
  - Run health/list/say across two projects; confirm isolation.
  - Add basic rate limiting and error redaction.
