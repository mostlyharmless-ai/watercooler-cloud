# [ARCHIVED] Cloudflare Remote MCP Playbook (Authorization‑First, Proxy‑First)

> Archived with the remote stack. Preferred path: local stdio MCP universal
> dev mode. See docs/TESTER_SETUP.md and docs/LOCAL_QUICKSTART.md.

**Intent:** Make **authorization and per‑request identity** the primary objective while exposing the existing **watercooler‑collab** MCP server as a **Remote MCP** behind **Cloudflare Workers** — **without changing tool logic**. The Worker provides the Remote MCP transport (SSE/Streamable HTTP) and enforces **user identity via OAuth** (best compatibility with `mcp-remote`). **Cloudflare Access** can be added later for org‑wide SSO (defense‑in‑depth). The Worker **proxies** tool calls to a thin **Python HTTP facade** that invokes the current Watercooler functions.

> Why this shape? Claude/Codex **do not pass a reliable client identity** (`client_id`, headers, or env). Remote MCP with **OAuth at the edge** is the simplest way to attach identity and project context to every call — *without* rewriting your Python tools.

---

## TL;DR (Auth‑First)

- Keep all **Python tool logic** as‑is. **Do not port** code to TypeScript.
- Stand up a **Cloudflare Worker** that implements **Remote MCP** endpoints and **forwards** to a **Python backend** (HTTP facade).
- Use the **GitHub OAuth** Remote MCP template by default (best support with `mcp-remote` for desktop clients).
- Optionally layer **Cloudflare Access** after OAuth works (org SSO). Be mindful of cookie/header requirements for CLI clients.
- Point Claude/Cursor at the Worker via **`mcp‑remote`**.
- Storage is **centralized** (shared FS and/or Git repo) in the Python backend — supports **many balls in play** (parallel threads).

---

## 0) Why Authorization‑First

- **Compatibility:** `mcp-remote` cleanly supports OAuth (first connection opens a browser). Cloudflare Access alone may require service tokens or cookies that typical clients do not inject.
- **Identity:** OAuth yields a **per‑user identity** you can map directly to authorship and policy (user → allowed projects).
- **Defense‑in‑depth:** Add Cloudflare **Access** in front of the Worker once stable. Confirm your clients can meet Access requirements without breaking `mcp-remote`.
- **Reality of clients:** Claude/Codex generally **do not provide** `client_id`/headers → the server cannot infer caller identity by itself; put identity at the edge.

---

## 1) Preconditions

- Repo: `mostlyharmless-ai/watercooler-cloud` (Python FastMCP server + tools).
- Node 18+, `npm`, and `wrangler` installed locally.
- Cloudflare account with **Workers** (+ **Access** optional).
- A reachable **Python backend** (private service) that exposes a thin **HTTP facade** for MCP tools (details below). This facade **reuses the same Python functions**; no logic changes.

---

## 2) Architecture

```
Claude / Cursor
  └─ mcp-remote (local proxy)
      └─ https://<worker>.<account>.workers.dev/sse  (Cloudflare Worker: Remote MCP)
            └─ forwards tool calls over HTTPS → Python MCP backend (HTTP facade)
                   └─ invokes existing Watercooler tools + file/git operations
```

**Why proxy‑first?**
- Cloudflare Workers cannot run CPython, subprocess, or a writable local FS. Watercooler tools use Python, the local filesystem (`.watercooler/`) and `git` (via subprocess).
- Proxying avoids any rewrite: the Worker only handles **Remote MCP transport + OAuth/Access**, while Python keeps doing the work.

**Multi‑tenancy (Per‑User / Per‑Project)**
- Identity comes from **OAuth** (user id/handle/email).
- **Project selection** provided by the client via query param `?project=<id>` while keeping the path `/sse` (matches template expectations), or by separate `mcpServers` entries per project.
- Worker enforces **authorization**: user → allowed projects (lookup via **KV/D1**) and forwards headers `X-User-Id`, `X-Agent-Name`, `X-Project-Id` to the backend.
- Backend selects per‑project storage (threads dir or a mapped Git repo) based on `X-Project-Id` and invokes existing Python functions.

---

## 3) Python backend (HTTP facade)

**Goal:** Provide a minimal **HTTP surface** that maps 1:1 to existing MCP tools. Internally, call the same functions already used by the FastMCP server.

**Required endpoints (suggested):**
- `POST /mcp/watercooler_v1_health`
- `POST /mcp/watercooler_v1_whoami`
- `POST /mcp/watercooler_v1_list_threads`
- `POST /mcp/watercooler_v1_read_thread`  (body: `{ topic }`)
- `POST /mcp/watercooler_v1_say`          (body: `{ topic, title, body, role?, entry_type? }`)
- `POST /mcp/watercooler_v1_ack`          (body: `{ topic, title, body }`)
- `POST /mcp/watercooler_v1_handoff`      (body: `{ topic, note, target_agent? }`)
- `POST /mcp/watercooler_v1_set_status`   (body: `{ topic, status }`)
- `POST /mcp/watercooler_v1_reindex`

**Implementation notes**
- Reuse `watercooler` library and `src/watercooler_mcp/*` code; call the same functions used in `src/watercooler_mcp/server.py`.
- Respect existing env vars (`WATERCOOLER_DIR`, `WATERCOOLER_GIT_*`). See `docs/ENVIRONMENT_VARS.md`.
- Set **agent identity** per request from an HTTP header (e.g., `X-Agent-Name`) by temporarily overriding `WATERCOOLER_AGENT` or passing through to `get_agent_name(...)` if you adapt it.
- Recommended: lightweight **FastAPI/Flask** app with JSON in/out and 200/4xx/5xx semantics.

**Per‑project selection (backend)**
- Accept `X-Project-Id` and compute:
  - Local FS mode: `threads_dir = Path(BASE_THREADS_ROOT) / user_id / project_id`
  - Git mode: map `project_id` → `WATERCOOLER_GIT_REPO` (e.g., `git@github.com:org/<project_id>-threads.git`)
- Call watercooler commands with explicit `threads_dir` (preferred) to avoid global env mutation.

**Example (pseudo‑Python):**
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

**Security**
- Bind the backend on **private network/VPC** or behind a gateway. The Worker should be the only public entry point.
- Require an **internal shared secret** or **mTLS** between Worker and backend.

---

## 4) Cloudflare Worker (Remote MCP gateway)

**Scaffold (OAuth‑first recommended)**
```bash
npm create cloudflare@latest mharmless-remote-mcp -- --template=cloudflare/ai/demos/remote-mcp-github-oauth
cd mharmless-remote-mcp
npm install
npm start   # local dev on http://localhost:8788/sse
```

**Configure wrangler (TOML preferred)**
```toml
# wrangler.toml
name = "mharmless-remote-mcp"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[vars]
BACKEND_URL = "https://backend.internal.example" # Python HTTP facade

# Optional: fallback for agent identity if Access/OAuth missing
DEFAULT_AGENT = "Agent"

# Bindings for multi-tenant project authorization
[[kv_namespaces]]
binding = "KV_PROJECTS"
id = "<your_kv_id>"
```

**OAuth secrets**
```bash
# GitHub OAuth app for the Worker
npx wrangler secret put GITHUB_CLIENT_ID
npx wrangler secret put GITHUB_CLIENT_SECRET
# Ensure the OAuth app redirect matches the Worker URL (…/sse auth flow in template docs)
```

**Project selection & authZ (Worker)**
- Accept `?project=<id>` on the `/sse` URL; preserve the `/sse` path.
- Resolve user from OAuth session; look up allowed projects in `KV_PROJECTS` under key `user_id`.
- If project not provided, fall back to a per‑user default stored in KV (or reject).
- On success, forward `X-Project-Id`, `X-User-Id`, and `X-Agent-Name` to the backend.

**KV shape (example):**
```json
{
  "user_id": "gh:octocat",
  "default": "proj-alpha",
  "projects": ["proj-alpha", "proj-beta"]
}
```

**Forwarding logic (conceptual)**
- For each MCP tool request, extract identity from OAuth (and Access if used) and call the Python backend endpoint with:
  - JSON body mirroring tool parameters
  - Headers: `X-Agent-Name`, `X-User-Id`, `X-Project-Id`, and your internal auth header
  - Timeouts tuned for **streamable responses** (use Streamable HTTP for long ops)

**Auth gating (authorization‑first)**
- Use the OAuth template by default so clients can authenticate via browser.
- Layer **Cloudflare Access** afterwards if you need org‑wide SSO. Validate `mcp-remote` compatibility (cookies/service tokens).

---

## 5) Identity and authorization

**OAuth (primary)**
- Use `remote-mcp-github-oauth`. First connection opens a browser; `mcp-remote` manages tokens.
- Derive `agent_name` from the OAuth identity (e.g., GitHub login).
- Worker → backend: set `X-Agent-Name: <derived>` and include an opaque **session id** for audit.

**Token mode (CLI/headless)**
- For non‑interactive clients (Codex, CI), issue personal tokens at `/console` (requires an OAuth session in the browser).
- Pass tokens via HTTP header: `Authorization: Bearer <token>` when connecting to `/sse`.
- Tokens are rate‑limited and time‑limited; prefer short TTLs and revoke when not needed.
- Example (`mcp-remote`):
  ```bash
  npx -y mcp-remote \
    "https://<worker>.<account>.workers.dev/sse?project=proj-alpha" \
    --header "Authorization: Bearer <YOUR_TOKEN>"
  ```

**Cloudflare Access (optional)**
- Put the Worker behind Access to require SSO for the domain.
- If using Access for programmatic clients, consider **Access Service Tokens** and a Worker adapter that injects or validates them.

**Server behavior**
- Existing server resolves agent identity as:
  1) `WATERCOOLER_AGENT` env var
  2) `client_id` from MCP Context (usually absent)
  3) fallback `"Agent"`
- Prefer **per‑request headers** to set identity on each call.

---

## 6) Environment & secrets (align with repo)

Use the repo’s variables from `docs/ENVIRONMENT_VARS.md`.

**Core**
- `WATERCOOLER_DIR` — threads directory root (server auto‑creates if missing)
- `WATERCOOLER_GIT_REPO` — enables git cloud sync (optional)
- `WATERCOOLER_GIT_SSH_KEY`, `WATERCOOLER_GIT_AUTHOR`, `WATERCOOLER_GIT_EMAIL`

**Worker**
- `BACKEND_URL` — private HTTPS URL for the Python facade
- `DEFAULT_AGENT` — optional fallback agent label
- `KV_PROJECTS` — KV binding used to store per‑user project ACLs and defaults
 - `ALLOW_DEV_SESSION` — optional (staging only). Default disabled. If `"true"`, allows temporary `?session=dev` testing in staging; never enable in production.
 - `AUTO_ENROLL_PROJECTS` — optional. Default `"false"`. When enabled, `set_project`/`create_project` may auto‑add the requested project to the caller's ACL after backend validation; prefer explicit `create_project` + ACL seeding.

> Staging posture: auth‑only by default (dev session disabled). Use OAuth or `/console` tokens. Enable dev session only temporarily for debugging.

**Cloudflare commands**
```bash
npx wrangler secret put BACKEND_URL
```

> Prefer `wrangler.toml` over JSON. Avoid inventing new names like `WATERCOOLER_ROOT`/`REPO_PATH`; stick to `WATERCOOLER_DIR` and `WATERCOOLER_GIT_*` to match the server.

---

## 6a) Hosting & Persistence (Render + Disk + Git Backup)

Backend hosting (Render)
- Service: Render Web Service (Python)
- Build: `pip install -U pip setuptools wheel && pip install '.[http]'`
- Start: `uvicorn src/watercooler_mcp/http_facade:app --host 0.0.0.0 --port $PORT`
- Env:
  - `BASE_THREADS_ROOT=/data/wc-cloud`
  - `INTERNAL_AUTH_SECRET=<strong-random>` (Worker must use same secret)
  - Optional (Git sync ON): `WATERCOOLER_GIT_REPO`, `WATERCOOLER_GIT_AUTHOR`, `WATERCOOLER_GIT_EMAIL`, `WATERCOOLER_GIT_SSH_KEY`
- Disk: attach persistent disk (e.g., wc-cloud) mounted at `/data` (≥ 1 GB). Without a Disk, storage is ephemeral.

Worker pointing to Render
- `BACKEND_URL` in `wrangler.toml` → Render URL (e.g., `https://app.onrender.com`)
- `INTERNAL_AUTH_SECRET` in Worker secrets → must equal Render secret
- Deploy: `npx wrangler deploy`

Hybrid mode (best of both)
- Primary store: Render Disk under `/data/wc-cloud` (fast, shared, durable)
- Periodic Git backup: Enable `WATERCOOLER_GIT_REPO` and use a scheduled sync from the Worker to the backend
  - Backend: `POST /admin/sync` (requires `X-Internal-Auth`) pulls and commit+pushes pending changes
  - Worker cron: call `/admin/sync` every 15 minutes (`[triggers] crons = ["*/15 * * * *"]`)

---
## 7) Client setup (`mcp-remote`)

**Claude Desktop `settings.json`**
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

**Cursor:** same command/args in MCP server config.

**Alternative:** define one `mcpServers` entry per project (distinct names) if you prefer not to pass `?project=`.

---

## 8) Validation & observability

**Validation**
1) `watercooler_v1_health` via MCP
2) `watercooler_v1_list_threads` → expect threads or an empty set
3) `watercooler_v1_say` on a test topic → confirm new entry appears
4) Switch projects (`?project=`) and repeat; ensure isolation (no cross‑project reads/writes)

**Observability**
- Use **Worker logs** to verify connect/disconnect and tool calls.
- Prefer **Streamable HTTP** for long‑running operations.
- For app‑level audit, continue emitting **Watercooler cards** in Python.

---

## 9) Migration checklist (authorization‑first)

1. Scaffold Worker from the **GitHub OAuth Remote MCP** template.
2. Configure OAuth app + secrets; verify browser sign‑in from client connect.
3. Stand up **Python HTTP facade** (private) mapping endpoints to existing tools (**no logic changes**).
4. Add per‑user/project **KV**: create `KV_PROJECTS`; write initial ACLs/defaults for target users/projects.
5. Configure Worker `BACKEND_URL` and KV bindings; `wrangler deploy`.
6. Connect with `mcp-remote` using `?project=<id>`; validate identity propagation (`X-User-Id`, `X-Agent-Name`, `X-Project-Id`) and core tools.
7. Flip projects and repeat; verify **isolation** and **authorization** errors for disallowed projects.
8. Optional: Add **Cloudflare Access** as a front gate; verify client compatibility (cookies/service tokens).
9. Optional: Enable `WATERCOOLER_GIT_REPO` for git sync in backend.
10. Document Worker URL, client config, auth and project selection expectations in `docs/`.

---

## 10) Troubleshooting

- **401 at Worker:** OAuth secrets or redirect mismatch; verify `GITHUB_CLIENT_ID/SECRET` and callback URL. If using Access, check policy/token handling.
- **No tools in client:** Ensure endpoint ends with `/sse` and that you’re using `mcp-remote`.
- **Timeouts/long calls:** Use **Streamable HTTP** variant in Worker; increase backend timeouts.
- **Env not applied:** Set/redeploy wrangler secrets/vars; confirm backend sees `WATERCOOLER_*`.
- **Identity mismatch in entries:** Ensure Worker sets `X-Agent-Name` and backend maps this to the effective agent.
- **Project denied:** Check `?project=` param, the user’s ACL in KV, and Worker enforcement.

---

## 11) Optional Phase 2 — Worker‑native execution (rewrite)

Only if you want to eliminate the Python backend:
- Re‑implement tool logic in TypeScript.
- Replace git subprocess with GitHub API or CF storage (R2/D1).
- Replace local `.watercooler/` with KV/R2/D1.
- This is a **rewrite**, not required for the Cloudflare cutover.

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

## Appendix B — `wrangler.toml` (skeleton)

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

## Appendix D — Hosting on free tiers (practical notes)

- **Cloudflare Workers (Free):** plenty for a small team; keep Worker logic **proxy‑light** (OAuth + ACL + forwarding). Prefer **Streamable HTTP/SSE** to support long-lived sessions while staying within the Free CPU budget.
- **Cloudflare KV (Free):** adequate for per‑user project ACLs and lightweight session/state.
- **Render Free backend:** one always‑on service (~750h/mo) is enough for the Python facade; expect **cold starts** after idle.
- Upgrade targets if needed: **Workers Standard** (more CPU/subrequests) and **Render Starter** (no cold starts).

---

## Appendix E — Tonight’s Implementation Plan (tight)

- **0:00–0:20 — OAuth Worker scaffold and secrets**
  - Create from `remote-mcp-github-oauth`; set `GITHUB_CLIENT_ID/SECRET`.
  - `npm start`; verify local `/sse` OAuth handshake via `mcp-remote`.

- **0:20–0:50 — Python HTTP facade (thin)**
  - Implement `/mcp/*` endpoints calling existing `watercooler` functions.
  - Support headers: `X-User-Id`, `X-Agent-Name`, `X-Project-Id`.

- **0:50–1:20 — Worker forwarder with project authZ**
  - Bind `KV_PROJECTS` and write initial ACLs/defaults for target users/projects.
  - Accept `?project=`; enforce membership; forward headers to backend.

- **1:20–1:40 — Deploy + connect**
  - Set `BACKEND_URL`; `wrangler deploy`.
  - Configure client `mcp-remote` with `?project=<id>`.

- **1:40–2:00 — Validate and harden**
  - Run health/list/say across two projects; confirm isolation.
  - Add basic rate limiting and error redaction.

---

## Appendix F — One‑PR Commit Breakdown (land tonight)

Goal: Ship everything in a single PR with 4–5 small, reviewable commits.

1) docs: authorization‑first Remote MCP plan and setup
- Update playbook(s), README pointers, and TROUBLESHOOTING with OAuth + `?project=` usage.
- Add example `wrangler.toml` and KV shape inline in docs.

2) feat(backend): Python HTTP facade for MCP tools (thin)
- New module: `src/watercooler_mcp/http_facade.py` (FastAPI/Flask), exposing `/mcp/*` endpoints:
  - health, whoami, list_threads, read_thread, say, ack, handoff, set_status, reindex
- Read headers: `X-User-Id`, `X-Agent-Name`, `X-Project-Id`.
- Derive per‑user/per‑project `threads_dir` or map to `WATERCOOLER_GIT_REPO`.
- Return JSON; ensure idempotency surfaces any errors cleanly.
- pyproject: add optional extra `http` with minimal deps (e.g., `fastapi`, `uvicorn` or `flask`).

3) feat(worker): Cloudflare Worker scaffold (OAuth + forwarding)
- New folder: `cloudflare-worker/` with `wrangler.toml` and `src/index.ts` skeleton.
- Template: `remote-mcp-github-oauth` shape; bind `KV_PROJECTS`.
- On `/sse?project=<id>`, enforce ACL from KV; forward headers (`X-User-Id`, `X-Agent-Name`, `X-Project-Id`) to backend.
- Streamable HTTP/SSE support; timeouts tuned for long ops.

4) chore(config): KV bootstrap and examples
- Add `scripts/kv_seed_projects.json` example and a short script/notes to populate KV for tonight’s users/projects.
- Document command(s) to write KV entries with Wrangler.

5) docs: client config + acceptance checklist
- Add a short `docs/REMOTE_MCP_QUICKSTART.md` with Claude/Cursor `mcp-remote` config, OAuth sign‑in expectations, and `?project=` usage.
- Add acceptance criteria: OAuth login succeeds; identity forwarded; per‑project isolation; core tools work (health/list/say/read); rate limiting; redaction.

Acceptance criteria (PR ready to merge)
- OAuth sign‑in works via `mcp-remote`; Worker returns tool list.
- Identity headers arrive at backend; entries show correct `agent_name`.
- Project ACL enforced; `?project=` switch isolates reads/writes.
- Health/list/say/read work end‑to‑end; long calls stream safely.
- Docs and examples sufficient for another dev to reproduce.
