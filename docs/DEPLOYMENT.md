# Remote MCP Deployment Guide

**A complete guide to deploying, securing, and operating Remote MCP with OAuth authentication and default-deny ACLs.**

This guide teaches you the architecture as you deploy it, helping you build a mental model of how OAuth, ACL enforcement, and MCP transport work together at the edge.

## Table of Contents

- [Understanding Remote MCP](#understanding-remote-mcp)
  - [What is Remote MCP?](#what-is-remote-mcp)
  - [System Architecture](#system-architecture)
  - [Request Flow](#request-flow)
  - [Security Model Overview](#security-model-overview)
- [Prerequisites](#prerequisites)
- [Deployment Journey](#deployment-journey)
  - [Quick Path: Using Helper Scripts](#quick-path-using-helper-scripts)
  - [Advanced Path: Manual Setup](#advanced-path-manual-setup)
- [Operation & Management](#operation--management)
  - [User & Access Management](#user--access-management)
  - [Monitoring & Observability](#monitoring--observability)
  - [Testing & Validation](#testing--validation)
- [Understanding Through Troubleshooting](#understanding-through-troubleshooting)
- [Security Deep Dive](#security-deep-dive)
- [Reference](#reference)

---

## Executive Summaries (At‑a‑Glance)

### Operator: 5‑Minute Rollout (Staging → Prod)
1. Secrets: `wrangler login` → `wrangler secret put GITHUB_CLIENT_ID|GITHUB_CLIENT_SECRET|INTERNAL_AUTH_SECRET`
2. Backend env: set `INTERNAL_AUTH_SECRET`, `BASE_THREADS_ROOT=/data/wc-cloud`, `WATERCOOLER_DIR=/data/wc-cloud`
3. Backend start: copy the one‑liner from [Deployment Journey → Backend Start Command](#configure-start-command-copypaste-one%E2%80%91liner)
4. Worker deploy (staging): `npx wrangler deploy --env staging` (auth-only; dev session disabled by default — use tokens via `/console` if needed)
5. Seed ACL: KV `user:gh:<login>` → `["proj-alpha"]`
6. Test OAuth + SSE + say/read; then deploy prod (`--env production`). Staging and prod are both behind auth; dev session is optional in staging and should be used only temporarily.

### Developer: Quick Test
1. Visit `/auth/login` (OAuth) → returns with session cookie
2. SSE: `/sse?project=proj-alpha` (Accept: `text/event-stream`)
3. Send JSON‑RPC to `/messages` → `initialize`, `tools/list`, `watercooler_v1_say`
4. Verify repo commit (if Git backup enabled)

### Security: Fast Checks
- 401 unauthenticated, 403 not in ACL, 406 missing SSE Accept header, 429 rate‑limited
- Default‑deny ACL enforced at Worker, backend validates `X‑Internal‑Auth`
- CSRF state checked on `/auth/callback`; cookie‑only sessions in production

### CLI Token Mode (Available)
- Use `Authorization: Bearer` tokens for headless/CLI clients (Codex, CI/CD)
- Self-service token issue/revoke at `/console` (requires OAuth session)
- Rate limits: 3 tokens/hour per user (issue); 10/hour (revoke)
- See [CLI Token Authentication](#cli-token-authentication) for setup details

### Pre‑Deploy Checklist (Per Environment)
- Cloudflare account: `npx wrangler whoami` shows the expected account
- KV binding: `[[kv_namespaces]]` contains `KV_PROJECTS` with a valid `id`
- Secrets set: `./cloudflare-worker/scripts/set-secrets.sh --env staging|production`
  - `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `INTERNAL_AUTH_SECRET`
  - INTERNAL_AUTH_SECRET matches the backend value exactly
- wrangler.toml per env:
  - Staging defaults: `ALLOW_DEV_SESSION="false"`, `AUTO_ENROLL_PROJECTS="false"`
  - Production: do not set `ALLOW_DEV_SESSION`; keep `AUTO_ENROLL_PROJECTS` off
  - `BACKEND_URL` points to the correct backend for the environment
- OAuth App: callback URL matches the Worker domain (`…/auth/callback`), no trailing slash
- ACL: seed at least one project for your user in KV (`user:gh:<login>`) 
- Token for testing: issue at `/console`; copy token safely
- Acceptance smoke:
  - Open SSE with `Authorization: Bearer <token>` on an allowed project → receive `event: endpoint`
  - POST `initialize` → then `tools/list` → `watercooler_v1_health` → `watercooler_v1_say`
  - Deny tests: forbidden project → 403; revoke token → subsequent 401
- Observability: `npx wrangler tail --env <env> --format json` shows `session_validated` and `token_auth_success`

## TODO: Token Lifecycle & UX Improvements

The following items capture best practices and planned refinements for day‑to‑day token use so users don’t need to edit configs frequently.

- Longer‑lived CLI tokens
  - Allow choosing TTL at issue time in `/console` (e.g., 7 or 30 days in addition to 24h default).
  - Document acceptable TTL ranges and recommend 7d as a solid default.
- “Token file + wrapper” pattern (no daily config edits)
  - Document keeping a token in `~/.watercooler-cloud/token` and using a tiny wrapper that injects `Authorization: Bearer $(cat ~/.watercooler-cloud/token)`.
  - When rotating, overwrite the file only; no changes to `~/.codex/config.toml` or `~/.claude.json`.
- Environment variable injection
  - Document using `WATERCOOLER_TOKEN` and a wrapper to add the header from the environment.
- Desktop session quality of life
  - Consider bumping cookie TTL modestly (e.g., 7d) for Desktop OAuth sessions, while preserving security constraints.
- Optional future enhancements
  - Device‑code flow for fully headless issuance from CLI.
  - “Alias tokens” (stable token ID with revocable inner secret) to avoid changing configs when rotating.
  - Read‑only tokens / per‑project scopes.
- Security guidance (document clearly)
  - Keep TTL as short as practical; use one token per user/machine; revoke immediately on suspicion.
  - Rate limits and default‑deny ACLs remain enforced regardless of TTL.


## How‑To Index (Jump Links)
- Set secrets (Worker): [Prerequisites → Cloudflare](#prerequisites)
- Configure Backend env + start command: [Configure Start Command](#configure-start-command-copypaste-one%E2%80%91liner)
- Deploy Worker: [Deployment Journey → Quick Path](#quick-path-using-helper-scripts)
- OAuth login flow: [Understanding Remote MCP → Request Flow](#request-flow)
- Seed ACL (default‑deny): [Operation & Management → User & Access](#user--access-management)
- Tail logs: [Monitoring & Observability](#monitoring--observability)
- Troubleshoot 401/403/406/429/5xx: [Troubleshooting](#understanding-through-troubleshooting)
- Enable Git backup: [Deployment Journey → Backend Start Command](#configure-start-command-copypaste-one%E2%80%91liner)

### Quick Glossary

- `KV` (Cloudflare Workers KV): Cloudflare’s globally distributed key–value store used by the Worker for small, fast data at the edge. We use it for:
  - Sessions: `session:{uuid}` → `{ userId, login, … }` (TTL ~24h)
  - OAuth CSRF state: `oauth:state:{state}` → "1" (TTL 10m)
  - Rate limits: `ratelimit:oauth:cb:{ip}` → counters (TTL 5m)
  - Access Control Lists (see below): `user:gh:{login}` → JSON array of allowed projects
  - (CLI tokens, planned): `token:{uuid}` → `{ userId, createdAt, expiresAt }`

- `ACL` (Access Control List): Per‑user allowlist of projects that enforces a default‑deny authorization model at the Worker. If there is no entry for the user or the project isn’t listed, the request is rejected with 403.
  - Key: `user:gh:{login}`
  - Value: JSON array of project names, e.g. `["proj-alpha", "proj-agent"]`
  - Example: `gh:octocat` may access `/sse?project=proj-alpha` but not `/sse?project=proj-forbidden`.

## Understanding Remote MCP

### What is Remote MCP?

Remote MCP enables MCP clients (like Claude Desktop) to connect to Watercooler collaboration tools through a secure, cloud-hosted proxy. Instead of running MCP servers locally, users authenticate via GitHub OAuth and access project-specific collaboration spaces through a Cloudflare Worker at the edge.

**Key Benefits**:
- **Zero local setup** - No local servers, no process management
- **Secure by default** - OAuth authentication + default-deny authorization
- **Multi-project isolation** - Each user's projects are strictly separated
- **Edge performance** - Cloudflare Workers provide global, low-latency access
- **Persistent storage** - Threads survive across sessions, optionally backed by Git

### System Architecture

The system has two main layers: an **authentication/authorization layer** at the edge (Cloudflare Worker), and a **tools/storage layer** in the cloud (FastAPI backend on Render).

```
┌─────────────┐
│ MCP Client  │ (Claude Desktop, etc.)
└──────┬──────┘
       │ SSE connection (Server-Sent Events)
       │ Cookie: session=<uuid>
       ▼
┌─────────────────────────────────────────────────┐
│          Cloudflare Worker (Edge)               │  🔒 Security Perimeter
│  ┌──────────────────────────────────────────┐  │
│  │ GET  /auth/login    → OAuth start        │  │
│  │ GET  /auth/callback → Session creation   │  │
│  │ GET  /sse           → MCP stream (SSE)   │  │
│  │ POST /messages      → JSON-RPC handler   │  │
│  │ GET  /health        → Health check       │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  Security Checkpoints:                          │
│  1️⃣  GitHub OAuth authentication                │
│  2️⃣  CSRF protection (state param + cookie)     │
│  3️⃣  Session validation (HttpOnly cookies)      │
│  4️⃣  Rate limiting (10 attempts / 5 min)        │
│  5️⃣  ACL enforcement (default-deny)             │
│                                                 │
│  Storage (Cloudflare KV):                       │
│  • session:{uuid} → SessionData                 │
│  • user:gh:{login} → ACL allowlist              │
│  • oauth:state:{state} → CSRF token (10min)     │
│  • ratelimit:* → Token bucket counters          │
└─────────────┬───────────────────────────────────┘
              │ Authenticated requests with identity headers:
              │ X-User-Id: gh:<login>
              │ X-Project-Id: <project-name>
              │ X-Agent-Name: <agent>
              │ X-Internal-Auth: <shared-secret>
              ▼
┌─────────────────────────────────────────────────┐
│         FastAPI Backend (Render)                │
│  ┌──────────────────────────────────────────┐  │
│  │ POST /mcp/*       → Watercooler tools    │  │
│  │ GET  /health      → Health check         │  │
│  │ POST /admin/sync  → Git sync trigger     │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  Security:                                      │
│  • Validates X-Internal-Auth (shared secret)   │
│  • Trusts Worker-provided identity headers     │
│  • Fail-fast on missing secret (production)    │
│                                                 │
│  Storage (Persistent Disk):                     │
│  • /data/wc-cloud/gh:<user>/<project>/         │
│  • Thread files (Markdown)                     │
│  • Optional Git sync to remote repo            │
└─────────────────────────────────────────────────┘
```

**Why this architecture?**

- **Worker at edge**: OAuth, session management, and ACL checks happen close to users, minimizing latency for security operations
- **Backend for tools**: Watercooler tools are complex Python code that benefits from traditional server infrastructure
- **Separation of concerns**: Authentication/authorization logic is isolated from business logic, making both easier to audit
- **Defense in depth**: Even if Worker were compromised, Backend validates shared secret; if Backend were compromised, it has no user credentials

### Request Flow

Let's trace what happens when a user connects to a project:

**First Time (Authentication)**:

```
1. User visits Worker URL in browser
   ↓
2. User navigates to /auth/login
   ↓
3. Worker generates cryptographic state parameter
   • Stores in KV: oauth:state:{state} → "1" (10min TTL)
   • Sets cookie: oauth_state={state} (HttpOnly, Secure)
   • Redirects to GitHub OAuth
   ↓
4. GitHub shows authorization screen
   ↓
5. User approves, GitHub redirects to /auth/callback?code=...&state=...
   ↓
6. Worker validates CSRF protection:
   • State from URL must exist in KV ✓
   • State from URL must match oauth_state cookie ✓
   • Delete state from KV (one-time use)
   ↓
7. Worker exchanges code for GitHub access token
   ↓
8. Worker fetches user info from GitHub API
   ↓
9. Worker creates session:
   • Store in KV: session:{uuid} → {userId: "gh:<login>", login, avatar}
   • Set cookie: session={uuid} (HttpOnly, Secure, 24h TTL)
   ↓
10. User now has authenticated session
```

**Every Subsequent Request** (once authenticated):

```
1. MCP Client connects to /sse?project=proj-alpha
   • Includes Cookie: session={uuid}
   ↓
2. Worker reads session cookie
   • Look up session:{uuid} in KV
   • Extract userId (e.g., "gh:octocat")
   ↓
3. Worker checks ACL (default-deny):
   • Look up user:gh:octocat in KV
   • Check if "proj-alpha" is in projects array
   • If NOT found → 403 Access Denied ❌
   • If found → Proceed ✓
   ↓
4. Worker proxies to Backend with identity headers:
   • X-User-Id: gh:octocat
   • X-Project-Id: proj-alpha
   • X-Agent-Name: Claude
   • X-Internal-Auth: <shared-secret>
   ↓
5. Backend validates:
   • X-Internal-Auth matches expected secret ✓
   • Trusts Worker-provided identity headers
   ↓
6. Backend executes Watercooler tool
   • Reads/writes threads in /data/wc-cloud/gh:octocat/proj-alpha/
   • Returns JSON-RPC response
   ↓
7. Worker streams response to client via SSE
```

**What happens on failure?**

- **No session cookie** → 401 Unauthorized
- **Session not in KV** (expired/invalid) → 401 Unauthorized
- **No ACL entry for user** → 403 Access Denied (default-deny)
- **Project not in ACL** → 403 Access Denied
- **Invalid internal auth** → 403 from Backend
- **Rate limit exceeded** → 429 Too Many Requests

### Security Model Overview

**Authentication vs Authorization** - Two distinct security layers:

1. **Authentication (OAuth)** - *Who are you?*
   - GitHub OAuth 2.0 proves user identity
   - Session cookies maintain authenticated state (24h)
   - CSRF protection prevents session injection attacks
   - Rate limiting prevents brute force attempts

2. **Authorization (ACL)** - *What can you access?*
   - Default-deny: No access unless explicitly granted
   - Per-user project allowlists stored in KV
   - Enforced at Worker before proxying to Backend
   - Independent of authentication (being logged in ≠ having access)

**Service-to-Service Authentication**:
- Worker and Backend share a secret (`INTERNAL_AUTH_SECRET`)
- Worker includes secret in `X-Internal-Auth` header on every backend request
- Backend validates secret, then trusts identity headers (`X-User-Id`, `X-Project-Id`)
- This prevents direct Backend access without going through Worker's security checks

**Why default-deny ACLs?**

Default-deny means users start with **zero** access. You must explicitly grant project access to each user. This is more secure than default-allow (where users start with access and you revoke as needed) because:

- **Fail-safe**: Misconfiguration results in denied access, not exposed data
- **Explicit intent**: Every permission is a conscious decision
- **Audit-friendly**: ACL list shows exactly who has access to what
- **Principle of least privilege**: Users only get what they need

---

## Prerequisites

Before deploying, you'll need accounts and credentials from three services. Here's what each provides and why it's necessary:

### 1. GitHub OAuth App (Organization-level)

**What it provides**: User authentication via GitHub's OAuth 2.0 flow

**Why organization-level**: Organization OAuth apps can access org membership, enabling future team-based permissions

**How to create**:
1. Navigate to: `https://github.com/organizations/<your-org>/settings/applications`
2. Click "New OAuth App"
3. Configure:
   - **Application name**: "Watercooler Remote MCP" (or your preferred name)
   - **Homepage URL**: `https://<your-worker-subdomain>.workers.dev`
   - **Authorization callback URL**: `https://<your-worker-subdomain>.workers.dev/auth/callback`
     - ⚠️ **Critical**: Must match exactly (no trailing slash)
   - **Application description**: "Remote MCP server with OAuth authentication"
4. Click "Register application"
5. **Copy these values** (you'll need them for deployment):
   - Client ID (public, shown on app page)
   - Client Secret (click "Generate a new client secret" if needed)

**OAuth scope**: Only `read:user` is requested (minimal permissions)

### 2. Cloudflare Account with Workers

**What it provides**: Edge compute platform for the Worker, KV storage for sessions and ACLs

**Why Cloudflare**: Global edge network provides low-latency security checks close to users

**Setup steps**:
1. Sign up at https://dash.cloudflare.com (free tier works)
2. Install Wrangler CLI: `npm install -g wrangler`
3. Authenticate: `wrangler login` (opens browser for OAuth)
4. Create KV namespace for data storage:
   ```bash
   wrangler kv:namespace create "KV_PROJECTS"
   wrangler kv:namespace create "KV_PROJECTS" --preview  # For local dev
   ```
5. **Copy the namespace IDs** from output (you'll add these to `wrangler.toml`)

**What is KV?** Cloudflare's globally replicated key-value store. We use it to store:
- Session data (session cookies → user identity)
- ACL allowlists (user → allowed projects)
- OAuth CSRF tokens (temporary state validation)
- Rate limiting counters (IP → attempt count)

### 3. Render Account (or any FastAPI-compatible host)

**What it provides**: Hosting for the FastAPI backend with persistent disk storage

**Why persistent disk**: Thread files need to survive container restarts

**Setup steps**:
1. Sign up at https://render.com (free tier available)
2. Create a new "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Build Command**: `pip install -e .`
   - **Start Command**: See [Backend Configuration](#backend-configuration) section below
   - **Add Disk**: Mount persistent disk at `/data` (for thread storage)

**Alternative hosting**: Any platform that supports FastAPI and persistent volumes works (Fly.io, Railway, cloud VMs, etc.)

### 4. Optional: Git Repository for Thread Backup

**What it provides**: Persistent backup of thread data outside Render's disk

**Why optional**: Render's persistent disk is reliable, but Git provides version history and off-platform backup

**Setup steps** (if desired):
1. Create empty repository: `git@github.com:<org>/watercooler-threads.git`
2. Generate SSH deploy key (no passphrase):
   ```bash
   ssh-keygen -t ed25519 -C "watercooler-deploy" -f watercooler_deploy_key
   ```
3. Add public key to repository as Deploy Key (with write access)
4. Copy private key contents for Render environment variable

---

## Deployment Journey

You have two paths: **Quick Path** using helper scripts (recommended for most users), or **Advanced Path** with manual configuration (for those who want full control or need to customize).

### Quick Path: Using Helper Scripts

This path uses automated scripts that handle secrets, validation, and deployment. Recommended for first-time deployment and production use.

**Time estimate**: ~15-20 minutes (plus manual GitHub OAuth app creation)

#### Step 1: Configure Secrets

The `set-secrets.sh` script guides you through configuring the three secrets the Worker needs.

```bash
cd cloudflare-worker
./scripts/set-secrets.sh
```

**What's happening?** The script will:
1. Verify you're logged into Cloudflare (via `wrangler whoami`)
2. Prompt for your **GitHub Client ID** (from OAuth app created in Prerequisites)
3. Prompt for your **GitHub Client Secret** (from OAuth app)
4. Either auto-generate a secure **Internal Auth Secret** or let you provide one
5. Use `wrangler secret put` to store these encrypted in Cloudflare
6. Display the `INTERNAL_AUTH_SECRET` value that you'll need for the Backend

**Security note**: Secrets are stored encrypted by Cloudflare and never written to local files (except optionally to `.internal-auth-secret`, which is git-ignored).

**Expected output**:
```
=== Cloudflare Worker Secrets Configuration ===

✓ Logged in to Cloudflare

Current secrets:
(none)

=== GitHub OAuth App Configuration ===

Get these from: https://github.com/organizations/<org>/settings/applications

Enter GITHUB_CLIENT_ID: Iv1.abc123...
Enter GITHUB_CLIENT_SECRET: ****

=== Internal Authentication Secret ===

Options:
  1. Auto-generate secure random secret (recommended)
  2. Enter custom secret (must be 32+ characters)

Choice (1 or 2): 1

Generated secure random secret

=== Confirm Configuration ===

GITHUB_CLIENT_ID: Iv1.abc123...
GITHUB_CLIENT_SECRET: abc1...xyz9
INTERNAL_AUTH_SECRET: f4e7d2c1...a9b8c7d6

Set these secrets? (yes/no): yes

Setting secrets...
✓ GITHUB_CLIENT_ID set
✓ GITHUB_CLIENT_SECRET set
✓ INTERNAL_AUTH_SECRET set

=== Secrets configured successfully! ===

IMPORTANT: Copy INTERNAL_AUTH_SECRET to Backend

INTERNAL_AUTH_SECRET=f4e7d2c1...a9b8c7d6

Steps for Render:
  1. Go to: https://dashboard.render.com
  2. Select your watercooler backend service
  3. Go to: Environment
  4. Add environment variable:
       Name: INTERNAL_AUTH_SECRET
       Value: (paste the value above)
  5. Save (this will redeploy the backend)
```

**Copy the `INTERNAL_AUTH_SECRET` value** - you'll configure this on the Backend in Step 3.

#### Step 2: Configure Backend

Before deploying the Worker, set up the Backend so it's ready to receive proxied requests.

**On Render** (or your hosting platform):

1. Set **required** environment variables:
   ```
   INTERNAL_AUTH_SECRET=<value from Step 1>
   BASE_THREADS_ROOT=/data/wc-cloud
   ```

2. Set **optional** Git sync variables (if using Git backup):
   ```
   WATERCOOLER_GIT_REPO=git@github.com:<org>/watercooler-threads.git
   WATERCOOLER_DIR=/data/wc-cloud
   WATERCOOLER_GIT_AUTHOR=Watercooler Bot
   WATERCOOLER_GIT_EMAIL=bot@yourdomain.com
   GIT_SSH_PRIVATE_KEY=<contents of deploy key PEM file>
   ```

3. Configure **Start Command** (copy/paste one‑liner):

   Preserve + migrate + initializer (recommended)
   ```bash
   mkdir -p /data/secrets && printf '%s' "$GIT_SSH_PRIVATE_KEY" > /data/secrets/wc_git_key && chmod 600 /data/secrets/wc_git_key && export GIT_SSH_COMMAND="ssh -i /data/secrets/wc_git_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes" && export WATERCOOLER_DIR=/data/wc-cloud BASE_THREADS_ROOT=/data/wc-cloud && if [ -n "$WATERCOOLER_GIT_REPO" ] && [ ! -d /data/wc-cloud/.git ]; then ts=$(date +%s); [ -d /data/wc-cloud ] && mv /data/wc-cloud /data/wc-cloud.bak.$ts || true; git clone "$WATERCOOLER_GIT_REPO" /data/wc-cloud && cd /data/wc-cloud && git config user.name "${WATERCOOLER_GIT_AUTHOR:-Watercooler Bot}" && git config user.email "${WATERCOOLER_GIT_EMAIL:-bot@mostlyharmless.ai}" && if ! git rev-parse --quiet --verify HEAD >/dev/null; then git commit --allow-empty -m "Initialize threads repo" && git push -u origin HEAD || true; fi; if [ -d /data/wc-cloud.bak.$ts ]; then cp -a /data/wc-cloud.bak.$ts/* /data/wc-cloud/ 2>/dev/null || true; git add -A && git commit -m "Initial import from disk" || true; git push || true; fi; fi && uvicorn src.watercooler_mcp.http_facade:app --host 0.0.0.0 --port "$PORT"
   ```

   Destructive first‑clone (faster; wipes any preexisting `/data/wc-cloud` on first run)
   ```bash
   mkdir -p /data/secrets && printf '%s' "$GIT_SSH_PRIVATE_KEY" > /data/secrets/wc_git_key && chmod 600 /data/secrets/wc_git_key && export GIT_SSH_COMMAND="ssh -i /data/secrets/wc_git_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes" && export WATERCOOLER_DIR=/data/wc-cloud BASE_THREADS_ROOT=/data/wc-cloud && if [ -n "$WATERCOOLER_GIT_REPO" ] && [ ! -d /data/wc-cloud/.git ]; then rm -rf /data/wc-cloud; git clone "$WATERCOOLER_GIT_REPO" /data/wc-cloud && cd /data/wc-cloud && git config user.name "${WATERCOOLER_GIT_AUTHOR:-Watercooler Bot}" && git config user.email "${WATERCOOLER_GIT_EMAIL:-bot@mostlyharmless.ai}" && if ! git rev-parse --quiet --verify HEAD >/dev/null; then git commit --allow-empty -m "Initialize threads repo" && git push -u origin HEAD || true; fi; fi && uvicorn src.watercooler_mcp.http_facade:app --host 0.0.0.0 --port "$PORT"
   ```

   **What this command does**:
   - Creates `/data/secrets/` directory for SSH key
   - Writes `GIT_SSH_PRIVATE_KEY` env var to a file (no trailing newline) and locks permissions
   - Exports `GIT_SSH_COMMAND` so git uses the key, disables host key prompts
   - Aligns both `WATERCOOLER_DIR` and `BASE_THREADS_ROOT` to `/data/wc-cloud`
   - Clones the threads repo to `/data/wc-cloud` if missing
   - If the repo is empty: creates an initial commit and runs `git push -u origin HEAD` to establish upstream
   - (Preserve variant) migrates any existing `/data/wc-cloud` content into the repo, commits and pushes
   - Starts FastAPI via `uvicorn`

4. Attach **persistent disk** at `/data` (ensures threads survive restarts)

5. Deploy the Backend (it will fail if `INTERNAL_AUTH_SECRET` is missing - this is expected fail-fast behavior)

**Why set up Backend first?** The Worker needs to proxy to a running Backend. By configuring the Backend first, you can immediately test end-to-end connectivity after deploying the Worker.

#### Step 3: Update Worker Configuration

Edit `cloudflare-worker/wrangler.toml` to configure environment variables:

```toml
# Global config (applies to all environments)
name = "watercooler-remote-mcp"
main = "src/index.ts"
compatibility_date = "2024-01-01"
node_compat = true

# KV namespace binding (from Prerequisites step)
[[kv_namespaces]]
binding = "KV_PROJECTS"
id = "your_production_namespace_id"     # From wrangler kv:namespace create
preview_id = "your_preview_namespace_id"  # From wrangler kv:namespace create --preview

# Staging environment
[env.staging]
name = "watercooler-remote-mcp-staging"
vars = { BACKEND_URL = "https://your-backend-staging.onrender.com", DEFAULT_AGENT = "Claude", ALLOW_DEV_SESSION = "false", AUTO_ENROLL_PROJECTS = "false" }

# Production environment (default when no --env specified)
vars = { BACKEND_URL = "https://your-backend-prod.onrender.com", DEFAULT_AGENT = "Claude" }
# Note: ALLOW_DEV_SESSION is NOT set (production default-denies dev sessions)
```

**Configuration decisions**:

- `BACKEND_URL`: Your Render backend URL (from Backend deployment)
- `DEFAULT_AGENT`: Default agent name for MCP requests (e.g., "Claude")
- `ALLOW_DEV_SESSION`: Optional in staging, disabled by default. If set to `"true"`, allows `?session=dev` for temporary testing. ⚠️ Never enable in production; prefer OAuth or issued tokens.
- `AUTO_ENROLL_PROJECTS`: Default `"false"`. When enabled, `set_project`/`create_project` can auto‑add the requested project to the caller’s ACL after backend validation. Prefer explicit `create_project` + `seed-acl.sh`.

Note: By default, staging and production can point to the same `BACKEND_URL` and share the same `KV_PROJECTS` namespace. Sessions (Durable Objects) are per‑environment, but threads/ACL/tokens are shared. To fully separate environments, bind a different KV namespace for staging and/or point `BACKEND_URL` to a staging backend.

**Why separate staging and production?** Staging lets you test changes (including risky features like dev sessions) before impacting production users.

#### Step 4: Deploy to Staging

Deploy to staging first to validate configuration before production deployment.

```bash
cd cloudflare-worker
./scripts/deploy.sh staging
```

**What's happening?** The `deploy.sh` script:
1. Validates all required secrets are set (`wrangler secret list`)
2. Checks KV namespace is bound (parses `wrangler.toml`)
3. Verifies `ALLOW_DEV_SESSION` is NOT enabled if deploying to production
4. Deploys with `wrangler deploy --env staging` (Wrangler compiles TypeScript)
5. Provides next-step instructions

**Expected output**:
```
=== Cloudflare Worker Deployment ===
Environment: staging

Running pre-flight checks...
✓ wrangler installed
✓ wrangler.toml found

Checking required secrets...
✓ GITHUB_CLIENT_ID is set
✓ GITHUB_CLIENT_SECRET is set
✓ INTERNAL_AUTH_SECRET is set

Checking KV namespace binding...
✓ KV_PROJECTS bound (ID: abc123...)

Checking environment configuration...
✓ Dev session DISABLED (staging) — recommended

=== All pre-flight checks passed ===

Building...
✓ Build successful

Deploying to staging...
[wrangler output...]

=== Deployment successful! ===

Next steps:
  1. Test OAuth flow:
     Visit: https://watercooler-remote-mcp-staging.your-org.workers.dev/auth/login

  2. Monitor logs:
     ./scripts/tail-logs.sh auth

  3. Seed ACL data (if not already done):
     ./scripts/seed-acl.sh <github-login> <project-name>

  4. Run security tests:
     ./scripts/test-security.sh https://watercooler-remote-mcp-staging.your-org.workers.dev
```

**Common deployment failures**:
- "Secret X is missing" → Run `./scripts/set-secrets.sh` first
- "KV_PROJECTS binding missing" → Create KV namespace and add to `wrangler.toml`
- "BACKEND_URL not found" → Add to `wrangler.toml` in `[env.staging]` section

#### Step 5: Grant User Access

With the Worker deployed, grant yourself (and other users) access to projects using the ACL system.

```bash
cd cloudflare-worker
./scripts/seed-acl.sh <github-login> <project1> <project2> ...
```

**Example**:
```bash
# Grant user "octocat" access to two projects
./scripts/seed-acl.sh octocat proj-alpha proj-beta
```

**What's happening?** The script:
1. Fetches current ACL from KV for user (if exists)
2. Adds specified projects to the allowlist (deduplicates)
3. Writes updated ACL back to KV at key `user:gh:<login>`
4. Displays resulting permissions

**Expected output**:
```
Seeding ACL for user: gh:octocat
Projects: proj-alpha proj-beta

Current ACL: (none)

Writing ACL to KV...
✓ ACL set for user gh:octocat

Final ACL:
{
  "projects": ["proj-alpha", "proj-beta"]
}
```

**View existing permissions**:
```bash
./scripts/seed-acl.sh octocat --show
```

**Revoke all access** (remove user from ACL):
```bash
./scripts/seed-acl.sh octocat --remove
```

**Understanding the ACL data structure**:
```json
// KV Key: user:gh:octocat
{
  "projects": ["proj-alpha", "proj-beta"]  // Array of allowed project names
}
```

When a user connects with `?project=proj-gamma` but their ACL only contains `["proj-alpha", "proj-beta"]`, they receive **403 Access Denied**. This is default-deny security in action.

#### Step 6: Test End-to-End

Now validate the complete authentication and authorization flow.

**Test 1: OAuth Flow** (manual browser test)

1. Visit Worker login URL:
   ```
   https://watercooler-remote-mcp-staging.your-org.workers.dev/auth/login
   ```

2. You'll be redirected to GitHub OAuth authorization screen

3. Authorize the application

4. GitHub redirects back to `/auth/callback`

5. Worker sets session cookie and shows success message

6. Your browser now has an authenticated session (check cookies: `session=<uuid>`)

**Test 2: ACL Enforcement** (automated security tests)

```bash
cd cloudflare-worker
./scripts/test-security.sh https://watercooler-remote-mcp-staging.your-org.workers.dev
```

**What's happening?** The test script validates:
- **CSRF Protection (C1)**: Reused state parameters are rejected
- **Session Fixation Prevention (C2)**: Session must come from cookie, not query param
- **Rate Limiting (C3)**: 11th OAuth attempt within 5 minutes is rate-limited
- **ACL Enforcement (H2)**: Access to non-allowlisted projects is denied

**Expected output**:
```
=== Remote MCP Security Tests ===
Worker URL: https://watercooler-remote-mcp-staging.your-org.workers.dev

Testing CSRF Protection (C1)...
✓ CSRF state validation prevents reuse attacks

Testing Session Fixation Prevention (C2)...
✓ Query param sessions rejected in production

Testing Rate Limiting (C3)...
✓ Rate limiting active after 10 attempts

Testing ACL Enforcement (H2)...
⚠ Skipped (requires authenticated session)

=== Summary ===
Passed: 3
Failed: 0
Skipped: 1
```

**Test 3: MCP Client Connection**

Configure your MCP client (Claude Desktop, etc.) with:
```json
{
  "mcpServers": {
    "watercooler-remote": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/client-sse", "https://watercooler-remote-mcp-staging.your-org.workers.dev/sse"],
      "env": {
        "MCP_PROJECT": "proj-alpha"
      }
    }
  }
}
```

**What happens on first connection**:
1. Client sends SSE connection request to Worker
2. Worker checks for `session` cookie
3. No cookie → Worker returns 401 with OAuth login URL
4. User visits OAuth login URL in browser (see Test 1)
5. After OAuth, user has session cookie
6. Client reconnects → Worker validates session → checks ACL → proxies to Backend
7. Backend executes Watercooler tools with identity headers

**Test 4: Monitor Logs**

Watch real-time logs to see authentication and ACL events:

```bash
cd cloudflare-worker
./scripts/tail-logs.sh auth    # Authentication events
./scripts/tail-logs.sh acl     # ACL decisions
./scripts/tail-logs.sh error   # Errors only
./scripts/tail-logs.sh all     # Everything
```

**Sample log output**:
```json
// Authentication success
{
  "event": "auth_success",
  "user": "gh:octocat",
  "timestamp": "2024-01-15T10:30:00Z"
}

// ACL allowed
{
  "event": "acl_allowed",
  "user": "gh:octocat",
  "project": "proj-alpha",
  "timestamp": "2024-01-15T10:30:05Z"
}

// ACL denied (project not in allowlist)
{
  "event": "acl_denied",
  "user": "gh:octocat",
  "project": "proj-gamma",
  "reason": "project_not_in_allowlist",
  "timestamp": "2024-01-15T10:31:00Z"
}
```

#### Step 7: Deploy to Production

Once staging is validated, deploy to production with the same process.

```bash
cd cloudflare-worker
./scripts/deploy.sh production
```

**What's different?** The script:
- Checks that `ALLOW_DEV_SESSION` is **NOT** enabled (security validation)
- Prompts for confirmation (production is live traffic)
- Deploys without `--env` flag (uses default `wrangler.toml` config)

**Production checklist before deploying**:
- ✅ Staging deployment tested and working
- ✅ OAuth flow validated in staging
- ✅ ACL enforcement tested in staging
- ✅ Backend health check passing
- ✅ Secrets rotated (if reusing staging secrets, rotate first)
- ✅ `ALLOW_DEV_SESSION` NOT set in production config
- ✅ Users seeded in production ACLs
- ✅ Monitoring/alerting configured

**Post-deployment validation**:
```bash
# Test production OAuth
open https://watercooler-remote-mcp.your-org.workers.dev/auth/login

# Run security tests
./scripts/test-security.sh https://watercooler-remote-mcp.your-org.workers.dev

# Monitor logs
./scripts/tail-logs.sh security
```

---

### Advanced Path: Manual Setup

This path gives you full control over every configuration step. Use this if you need to customize deployment, understand internals deeply, or deploy to non-standard environments.

**When to use manual setup**:
- Custom Cloudflare account structure (multiple accounts, legacy KV)
- Non-Render backend hosting (requires different deployment commands)
- CI/CD pipeline integration (script commands can be extracted)
- Learning/educational purposes (seeing every step explicitly)

#### Manual Step 1: Create and Bind KV Namespace

Create Cloudflare KV namespace for session and ACL storage:

```bash
cd cloudflare-worker

# Production namespace
wrangler kv:namespace create "KV_PROJECTS"
# Output: Created namespace with ID: abc123def456...

# Preview namespace (for local development)
wrangler kv:namespace create "KV_PROJECTS" --preview
# Output: Created namespace with ID: xyz789uvw123...
```

Edit `wrangler.toml` to bind the namespace:

```toml
[[kv_namespaces]]
binding = "KV_PROJECTS"
id = "abc123def456..."        # Production ID from above
preview_id = "xyz789uvw123..." # Preview ID from above
```

**What is this binding?** The TypeScript code accesses KV via `env.KV_PROJECTS` (the binding name). Cloudflare maps this to the actual namespace IDs you created.

#### Manual Step 2: Set Worker Secrets

Set the three required secrets using Wrangler:

```bash
# GitHub OAuth App Client ID
wrangler secret put GITHUB_CLIENT_ID
# Prompt: Enter value for GITHUB_CLIENT_ID:
# (paste Client ID from GitHub OAuth app)

# GitHub OAuth App Client Secret
wrangler secret put GITHUB_CLIENT_SECRET
# Prompt: Enter value for GITHUB_CLIENT_SECRET:
# (paste Client Secret from GitHub OAuth app)

# Internal authentication secret (shared with Backend)
# Generate 32+ character random string:
openssl rand -hex 32  # Outputs: f4e7d2c1b0a9...
wrangler secret put INTERNAL_AUTH_SECRET
# Prompt: Enter value for INTERNAL_AUTH_SECRET:
# (paste generated secret)
```

**Save the `INTERNAL_AUTH_SECRET` value** - you'll configure it on Backend in next step.

**Verify secrets are set**:
```bash
wrangler secret list
# Output:
# GITHUB_CLIENT_ID
# GITHUB_CLIENT_SECRET
# INTERNAL_AUTH_SECRET
```

#### Manual Step 3: Configure Backend Environment

Set environment variables on your Backend hosting platform (Render example shown):

**Required Variables**:
```bash
INTERNAL_AUTH_SECRET=<exact value from Worker secret>
BASE_THREADS_ROOT=/data/wc-cloud
```

**Optional Git Sync Variables**:
```bash
WATERCOOLER_GIT_REPO=git@github.com:your-org/watercooler-threads.git
WATERCOOLER_DIR=/data/wc-cloud
WATERCOOLER_GIT_AUTHOR=Watercooler Bot
WATERCOOLER_GIT_EMAIL=bot@yourdomain.com
GIT_SSH_PRIVATE_KEY=<SSH private key PEM contents>
```

**Why `WATERCOOLER_DIR` must equal `BASE_THREADS_ROOT`**: Both point to the same directory. `BASE_THREADS_ROOT` is where the app writes threads; `WATERCOOLER_DIR` is the Git working tree. Mismatch causes "clone into non-empty directory" errors.

**Start Command** (configure in Render dashboard or equivalent):
```bash
bash -c 'mkdir -p /data/secrets && echo "$GIT_SSH_PRIVATE_KEY" > /data/secrets/wc_git_key && chmod 600 /data/secrets/wc_git_key && export GIT_SSH_COMMAND="ssh -i /data/secrets/wc_git_key -o StrictHostKeyChecking=no" && if [ -n "$WATERCOOLER_GIT_REPO" ] && [ ! -d "$WATERCOOLER_DIR/.git" ]; then git clone "$WATERCOOLER_GIT_REPO" "$WATERCOOLER_DIR" || echo "Clone failed, continuing..."; fi && uvicorn src.watercooler_mcp.http_facade:app --host 0.0.0.0 --port $PORT'
```

**Persistent Disk**: Mount at `/data` (Render: Dashboard → Disks → Add Disk)

#### Manual Step 4: Configure Worker Environment Variables

Edit `cloudflare-worker/wrangler.toml`:

```toml
name = "watercooler-remote-mcp"
main = "src/index.ts"
compatibility_date = "2024-01-01"
node_compat = true  # Required for Node.js built-ins

[[kv_namespaces]]
binding = "KV_PROJECTS"
id = "your_production_namespace_id"
preview_id = "your_preview_namespace_id"

# Staging environment
[env.staging]
name = "watercooler-remote-mcp-staging"
vars = {
  BACKEND_URL = "https://your-backend-staging.onrender.com",
  DEFAULT_AGENT = "Claude",
  ALLOW_DEV_SESSION = "false",  # Default; set to "true" temporarily for testing only
  AUTO_ENROLL_PROJECTS = "false"  # Recommended default; prefer explicit create_project + ACL
}

# Production environment (default)
vars = {
  BACKEND_URL = "https://your-backend-prod.onrender.com",
  DEFAULT_AGENT = "Claude"
  # ALLOW_DEV_SESSION is NOT set (production default)
}
```

**Environment Variable Descriptions**:
- `BACKEND_URL`: FastAPI backend URL (from Render deployment)
- `DEFAULT_AGENT`: Default agent name sent to Backend (typically "Claude")
- `ALLOW_DEV_SESSION`: Optional (staging). Default disabled; if `"true"`, allows `?session=dev` for temporary testing. Prefer OAuth/tokens.
- `AUTO_ENROLL_PROJECTS`: Default `"false"`. When enabled, auto‑enrolls requested project into caller’s ACL after backend validation; prefer explicit ACL seeding.

#### Manual Step 5: Deploy

```bash
cd cloudflare-worker

# Install dependencies
npm install

# Deploy to staging
wrangler deploy --env staging

# Deploy to production (after staging validation)
wrangler deploy
```

**Post-deployment verification**:
```bash
# Check deployment
wrangler deployments list

# Test health endpoint
curl https://watercooler-remote-mcp-staging.your-org.workers.dev/health
# Expected: {"status": "ok", "timestamp": "..."}
```

#### Manual Step 6: Seed ACL Data

Use Wrangler to directly write ACL entries to KV:

```bash
# Grant user "octocat" access to "proj-alpha" and "proj-beta"
wrangler kv:key put "user:gh:octocat" '{"projects":["proj-alpha","proj-beta"]}' --binding=KV_PROJECTS

# Verify
wrangler kv:key get "user:gh:octocat" --binding=KV_PROJECTS
# Expected: {"projects":["proj-alpha","proj-beta"]}
```

**Alternative: Use seed-acl.sh script** (even in manual path):
```bash
./scripts/seed-acl.sh octocat proj-alpha proj-beta
```

#### Manual Step 7: Test Deployment

**Test OAuth Flow**:
```bash
# Initiate OAuth (will redirect to GitHub)
curl -i https://watercooler-remote-mcp-staging.your-org.workers.dev/auth/login
# Expected: HTTP 302 redirect to github.com/login/oauth/authorize?...
```

**Test Backend Connectivity** (requires valid `INTERNAL_AUTH_SECRET`):
```bash
curl -X POST https://your-backend.onrender.com/mcp/watercooler_v1_health \
  -H "X-Internal-Auth: $INTERNAL_AUTH_SECRET" \
  -H "X-User-Id: gh:testuser" \
  -H "X-Project-Id: test-proj" \
  -H "X-Agent-Name: Claude"
# Expected: {"status": "healthy", ...}
```

**Test ACL Enforcement**:
```bash
# Requires authenticated session (cookie)
# Use browser DevTools to copy session cookie after OAuth

curl -H "Cookie: session=<uuid>" \
  -H "Accept: text/event-stream" \
  "https://watercooler-remote-mcp-staging.your-org.workers.dev/sse?project=proj-alpha"
# Expected: SSE stream (if user has proj-alpha in ACL)
# Or: 403 Access Denied (if user lacks ACL entry)
```

---

## Operation & Management

### User & Access Management

#### Granting Access

Use the `seed-acl.sh` script to grant users access to projects:

```bash
cd cloudflare-worker/scripts

# Grant single user access to multiple projects
./seed-acl.sh octocat proj-alpha proj-beta proj-gamma

# Grant multiple users access (run separately for each)
./seed-acl.sh alice proj-alpha
./seed-acl.sh bob proj-alpha proj-beta
```

**What happens**:
1. Script fetches existing ACL for user from KV (if exists)
2. Adds new projects to existing allowlist (deduplicates)
3. Writes updated JSON to KV at `user:gh:<login>`

**Example: Progressive Access**
```bash
# Week 1: Grant Alice access to one project
./seed-acl.sh alice proj-alpha

# Week 2: Add another project (preserves existing)
./seed-acl.sh alice proj-beta

# Result: Alice has ["proj-alpha", "proj-beta"]
```

#### Viewing Permissions

Check what projects a user can access:

```bash
./seed-acl.sh octocat --show
```

**Expected output**:
```
ACL for user gh:octocat:
{
  "projects": ["proj-alpha", "proj-beta"]
}
```

**Alternative: Direct KV query**:
```bash
wrangler kv:key get "user:gh:octocat" --binding=KV_PROJECTS
```

#### Revoking Access

**Revoke all access** (remove user from ACL entirely):
```bash
./seed-acl.sh octocat --remove
```

**Revoke specific project** (manual KV update required):
```bash
# Fetch current ACL
CURRENT=$(wrangler kv:key get "user:gh:octocat" --binding=KV_PROJECTS)

# Edit JSON to remove project (example: remove proj-beta)
# Before: {"projects":["proj-alpha","proj-beta"]}
# After:  {"projects":["proj-alpha"]}

# Write updated ACL
wrangler kv:key put "user:gh:octocat" '{"projects":["proj-alpha"]}' --binding=KV_PROJECTS
```

**Best practice**: Prefer `--remove` and re-grant with specific projects to avoid manual JSON editing errors.

#### Understanding Default-Deny

**No ACL entry = zero access**. When a user first authenticates via OAuth, they can log in successfully but cannot access ANY project until you grant permission:

```
User "alice" authenticates via OAuth ✓
  ↓
Alice tries to connect to proj-alpha
  ↓
Worker checks KV for user:gh:alice
  ↓
Key not found → 403 Access Denied ❌
  ↓
Admin runs: ./seed-acl.sh alice proj-alpha
  ↓
Alice tries again → Worker finds proj-alpha in allowlist ✓
  ↓
Connection succeeds ✓
```

This fail-safe behavior means forgetting to seed ACLs results in denied access (safe), not exposed data (dangerous).

#### CLI Token Authentication

For CLI clients (Codex, CI/CD pipelines) that cannot use browser-based OAuth, users can create Personal MCP Tokens.

**Token Workflow**:
1. User authenticates via browser OAuth at `/auth/login`
2. User visits `/console` to create a CLI token
3. Token is shown once (copy immediately!)
4. User configures CLI client with `Authorization: Bearer <token>`
5. Token authenticates requests with same ACL permissions as user's OAuth session

**Security Model**:
- Tokens are scoped to the user who created them
- Tokens inherit the user's project ACLs (same default-deny enforcement)
- Rate limits: 3 tokens/hour per user (creation), 10/hour (revocation)
- Default TTL: 24 hours (configurable at creation)
- Tokens are stored in KV as `token:{uuid}` with expiration

**Creating Tokens via Console**:

Users create their own tokens at `/console`:
```bash
# 1. User opens console in browser (requires OAuth session)
open https://watercooler-remote-mcp.your-org.workers.dev/console

# 2. Fill out form:
#    - Note: "My dev laptop" (optional)
#    - TTL: 86400 seconds (24 hours)
# 3. Click "Create Token"
# 4. Copy token immediately (won't be shown again)
```

**Configuring CLI Clients**:

```toml
# Codex CLI (~/.codex/config.toml)
[mcp_servers.watercooler_cloud]
command = "npx"
args = [
  "-y",
  "mcp-remote",
  "https://watercooler-remote-mcp.your-org.workers.dev/sse?project=proj-alpha",
  "--header",
  "Authorization: Bearer a1b2c3d4-5678-90ab-cdef-1234567890ab"
]
```

```bash
# Direct usage
npx -y mcp-remote \
  "https://watercooler-remote-mcp.your-org.workers.dev/sse?project=proj-alpha" \
  --header "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Token Revocation**:

Users can revoke their own tokens at `/console` or via the revocation API:

```bash
# Via console (browser)
# 1. Visit /console
# 2. Enter token ID in "Revoke Token" section
# 3. Click "Revoke Token"

# Via API (requires OAuth session cookie)
curl -X POST https://watercooler-remote-mcp.your-org.workers.dev/tokens/revoke \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your-session-cookie>" \
  -d '{"tokenId": "a1b2c3d4-5678-90ab-cdef-1234567890ab"}'
```

**Admin Token Revocation**:

Admins can manually revoke any token via KV:

```bash
# Revoke specific token
npx wrangler kv:key delete "token:a1b2c3d4-5678-90ab-cdef-1234567890ab" \
  --binding=KV_PROJECTS --env production

# List all tokens (note: this is inefficient, use sparingly)
npx wrangler kv:key list --binding=KV_PROJECTS --prefix="token:" --env production
```

**Security Best Practices for Tokens**:
- Store tokens in environment variables or secure vaults (not in code)
- Use short TTLs for development (1-24 hours)
- Create separate tokens for each machine/environment
- Revoke tokens immediately if compromised or when no longer needed
- Monitor `token_auth_failure` events for suspicious activity
- Educate users to never commit tokens to version control

**Token Limitations**:
- Tokens cannot be listed (by design - no enumeration attack surface)
- Users must track their own tokens or revoke and recreate
- No per-project token scoping yet (future enhancement)
- No long-lived service tokens (all tokens have TTL)

---

### Monitoring & Observability

#### Viewing Logs

The `tail-logs.sh` script provides filtered log streams from the Worker:

```bash
cd cloudflare-worker/scripts

# Authentication events (OAuth flow, session creation)
./tail-logs.sh auth

# ACL decisions (allowed/denied project access)
./tail-logs.sh acl

# All errors (500s, exceptions, validation failures)
./tail-logs.sh error

# Security events (auth + acl + rate limiting)
./tail-logs.sh security

# Everything (unfiltered)
./tail-logs.sh all
```

**How filtering works**: The script uses `wrangler tail` with grep filters on structured JSON logs. Each event type has an `"event"` field (e.g., `"auth_success"`, `"acl_denied"`).

#### Log Event Types

**Authentication Events**:
```json
// Successful OAuth completion
{
  "event": "auth_success",
  "user": "gh:octocat",
  "timestamp": "2024-01-15T10:30:00Z"
}

// OAuth callback failure (invalid code, etc.)
{
  "event": "auth_error",
  "error": "Invalid authorization code",
  "timestamp": "2024-01-15T10:30:00Z"
}

// CSRF state validation failure
{
  "event": "csrf_error",
  "reason": "state_mismatch",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**ACL Events**:
```json
// User allowed (project in allowlist)
{
  "event": "acl_allowed",
  "user": "gh:octocat",
  "project": "proj-alpha",
  "timestamp": "2024-01-15T10:30:05Z"
}

// User denied (no ACL entry)
{
  "event": "acl_denied",
  "user": "gh:alice",
  "project": "proj-alpha",
  "reason": "no_acl_entry",
  "timestamp": "2024-01-15T10:31:00Z"
}

// User denied (project not in allowlist)
{
  "event": "acl_denied",
  "user": "gh:octocat",
  "project": "proj-gamma",
  "reason": "project_not_in_allowlist",
  "allowlist": ["proj-alpha", "proj-beta"],
  "timestamp": "2024-01-15T10:32:00Z"
}
```

**Rate Limiting Events**:
```json
// Rate limit triggered
{
  "event": "rate_limit_exceeded",
  "ip": "203.0.113.42",
  "endpoint": "/auth/callback",
  "timestamp": "2024-01-15T10:33:00Z"
}
```

**CLI Token Events**:
```json
// Token issued successfully
{
  "event": "token_issue",
  "user": "gh:octocat",
  "token_id": "a1b2c3d4-...",  // Truncated for logs
  "ttl": 86400,
  "note": "My dev laptop",
  "timestamp": "2024-01-15T10:35:00Z"
}

// Token authentication success
{
  "event": "token_auth_success",
  "user": "gh:octocat",
  "token_id": "a1b2c3d4-...",
  "timestamp": "2024-01-15T10:36:00Z"
}

// Token authentication failure
{
  "event": "token_auth_failure",
  "reason": "token_expired",  // or "token_not_found", "parse_error"
  "token_id": "a1b2c3d4-...",
  "user": "gh:octocat",  // Only present if token was found but expired
  "timestamp": "2024-01-15T11:36:00Z"
}

// Token revoked
{
  "event": "token_revoke",
  "user": "gh:octocat",
  "token_id": "a1b2c3d4-...",
  "timestamp": "2024-01-15T11:00:00Z"
}

// Console page accessed
{
  "event": "console_view",
  "user": "gh:octocat",
  "timestamp": "2024-01-15T10:34:00Z"
}
```

**Monitoring CLI Tokens**:
```bash
# View all token-related events
npx wrangler tail --env production --format json | grep -E 'token_'

# Monitor token authentication (successes and failures)
npx wrangler tail --env production --format json | grep -E 'token_auth_'

# Watch for token issuance (check for suspicious patterns)
npx wrangler tail --env production --format json | grep 'token_issue'
```

#### Health Checks

**Worker Health**:
```bash
curl https://watercooler-remote-mcp.your-org.workers.dev/health
```

Expected response:
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Backend Health**:
```bash
curl https://your-backend.onrender.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "threads_root": "/data/wc-cloud",
  "git_enabled": true
}
```

#### Metrics and Alerting

**Cloudflare Analytics** (via Cloudflare Dashboard):
- Request rate (requests/second)
- Error rate (4xx/5xx status codes)
- Latency (p50/p95/p99)
- CPU time and KV operations

**Key Metrics to Monitor**:
- **401 errors** - Session expiration or missing auth (expected occasionally)
- **403 errors** - ACL denials (investigate if spike occurs)
- **429 errors** - Rate limiting (investigate if sustained)
- **500 errors** - Worker/Backend errors (should be near zero)
- **503 errors** - Backend unavailable (investigate immediately)

**Recommended Alerts**:
- 5xx error rate > 1% for 5 minutes → Page on-call
- 429 rate limit errors > 100/min for 5 minutes → Possible attack
- 403 ACL denials > 50/min → Possible misconfiguration or attack
- Backend health check failing → Backend down

---

### Testing & Validation

#### End-to-End OAuth Flow

Manually test the complete authentication flow in a browser:

1. **Clear cookies** (start fresh):
   - Browser DevTools → Application → Cookies → Clear all for worker domain

2. **Visit login endpoint**:
   ```
   https://watercooler-remote-mcp.your-org.workers.dev/auth/login
   ```

3. **Observe redirect to GitHub**:
   - URL changes to `github.com/login/oauth/authorize?...`
   - Query params include `client_id` (your OAuth app) and `state` (CSRF token)
   - Check browser cookies: `oauth_state` cookie set (HttpOnly, Secure)

4. **Authorize application**:
   - GitHub shows "Authorize [Your OAuth App]" screen
   - Click "Authorize"

5. **Observe callback**:
   - GitHub redirects to `https://worker.dev/auth/callback?code=...&state=...`
   - Worker validates CSRF (state param matches cookie)
   - Worker exchanges code for access token
   - Worker creates session in KV
   - Browser receives `session` cookie (HttpOnly, Secure, 24h TTL)

6. **Verify session cookie**:
   - DevTools → Application → Cookies → `session=<uuid>`
   - Note UUID value (this is your session ID)

7. **Verify session in KV** (optional):
   ```bash
   wrangler kv:key get "session:<uuid>" --binding=KV_PROJECTS
   # Expected: {"userId":"gh:<login>","login":"<login>","avatar":"<url>"}
   ```

**What to look for**:
- ✅ Each redirect preserves state parameter
- ✅ Cookies are HttpOnly and Secure
- ✅ Session lasts 24 hours (check cookie expiry)
- ✅ Repeated logins create new sessions (different UUIDs)

#### Security Validation Tests

Run automated security tests to validate protection mechanisms:

```bash
cd cloudflare-worker/scripts
./test-security.sh https://watercooler-remote-mcp.your-org.workers.dev
```

**What gets tested**:

**Test C1: CSRF Protection**
- Attempts to reuse OAuth state parameter
- Expected: 403 Forbidden (state already consumed)
- **Why this matters**: Prevents attackers from replaying OAuth callbacks

**Test C2: Session Fixation Prevention**
- Attempts to connect with `?session=<uuid>` query parameter
- Expected: 401 Unauthorized in production (only cookies accepted)
- **Why this matters**: Prevents attackers from injecting session IDs via URL

**Test C3: Rate Limiting**
- Sends 11 OAuth callback requests within 5 minutes
- Expected: First 10 succeed, 11th returns 429 Too Many Requests
- **Why this matters**: Prevents brute force attacks on OAuth flow

**Test H2: ACL Enforcement**
- Requires authenticated session (skipped if no session cookie)
- Attempts to access project not in ACL
- Expected: 403 Access Denied
- **Why this matters**: Validates default-deny authorization

**Sample output**:
```
=== Remote MCP Security Tests ===
Worker URL: https://watercooler-remote-mcp.your-org.workers.dev

Testing CSRF Protection (C1)...
Initiating OAuth flow to get state parameter...
Attempting to reuse state parameter...
✓ CSRF state validation prevents reuse attacks

Testing Session Fixation Prevention (C2)...
Attempting connection with query param session...
✓ Query param sessions rejected in production

Testing Rate Limiting (C3)...
Sending 11 OAuth callback attempts...
Attempt 1/11... 200
Attempt 2/11... 200
...
Attempt 10/11... 200
Attempt 11/11... 429 (Rate limited)
✓ Rate limiting active after 10 attempts

Testing ACL Enforcement (H2)...
⚠ Skipped (requires authenticated session cookie)

=== Summary ===
Passed: 3
Failed: 0
Skipped: 1
```

#### Backend Direct Testing

Test Backend independently (bypassing Worker) to isolate issues:

**Health Check**:
```bash
curl https://your-backend.onrender.com/health
```

**Call Watercooler Tool**:
```bash
# Replace $INTERNAL_AUTH_SECRET with your secret
curl -X POST https://your-backend.onrender.com/mcp/watercooler_v1_health \
  -H "X-Internal-Auth: $INTERNAL_AUTH_SECRET" \
  -H "X-User-Id: gh:testuser" \
  -H "X-Project-Id: test-proj" \
  -H "X-Agent-Name: Claude" \
  -H "Content-Type: application/json"
```

Expected response:
```json
{
  "status": "healthy",
  "threads_dir": "/data/wc-cloud/gh:testuser/test-proj"
}
```

**Write Thread Entry**:
```bash
curl -X POST https://your-backend.onrender.com/mcp/watercooler_v1_say \
  -H "X-Internal-Auth: $INTERNAL_AUTH_SECRET" \
  -H "X-User-Id: gh:testuser" \
  -H "X-Project-Id: test-proj" \
  -H "X-Agent-Name: Claude" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "test-thread",
    "title": "Test Entry",
    "body": "This is a test message",
    "role": "implementer",
    "entry_type": "Note"
  }'
```

**Verify File Created**:
```bash
# On Render, use Web Shell or SSH
ls -la /data/wc-cloud/gh:testuser/test-proj/
# Expected: test-thread.md file exists
```

**What this tells you**:
- ✅ Backend is reachable and processing requests
- ✅ `INTERNAL_AUTH_SECRET` is correctly configured
- ✅ Thread storage is working
- ✅ Per-user/per-project directories are created correctly

If Backend direct tests work but Worker→Backend fails, the issue is in Worker proxy logic or network connectivity.

#### Project Isolation Verification

Verify that different projects create separate directories:

1. **Connect to project A** (with authenticated session):
   ```
   https://worker.dev/sse?project=proj-alpha
   ```

2. **Write thread entry** (via MCP client or direct API):
   ```bash
   # (Use Backend direct test from above with X-Project-Id: proj-alpha)
   ```

3. **Connect to project B**:
   ```
   https://worker.dev/sse?project=proj-beta
   ```

4. **Write thread entry**:
   ```bash
   # (Use Backend direct test with X-Project-Id: proj-beta)
   ```

5. **Verify separate directories**:
   ```bash
   # On Backend (Render Web Shell)
   ls /data/wc-cloud/gh:<login>/
   # Expected:
   # proj-alpha/
   # proj-beta/

   ls /data/wc-cloud/gh:<login>/proj-alpha/
   # Expected: thread files for proj-alpha

   ls /data/wc-cloud/gh:<login>/proj-beta/
   # Expected: thread files for proj-beta (separate from proj-alpha)
   ```

**What this validates**:
- ✅ Projects are isolated (no data leakage between projects)
- ✅ Directory structure follows `/data/wc-cloud/gh:<user>/<project>/` pattern
- ✅ Worker correctly passes `X-Project-Id` header
- ✅ Backend correctly uses project ID in file paths

#### Thread Disambiguation & Cross-Project Behavior

The Worker implements thread existence checking and cross-project access controls to prevent confusion and ensure intentional thread creation.

**Key Behaviors**:

1. **Session Project Persistence**
   - `watercooler_v1_set_project` stores project ID in Durable Object storage
   - Project selection persists across all subsequent tool calls
   - Check current project with `watercooler_v1_whoami`

2. **Thread Existence Checking**
   - Thread operations require explicit thread creation via `create_if_missing=true`
   - Operations on non-existent threads return helpful error messages
   - Error includes list of projects where thread exists (if any)

3. **Cross-Project Access**
   - All thread tools accept optional `project` parameter
   - Explicit project parameter bypasses session project
   - Cross-project operations logged and annotated in metadata
   - ACL validation enforced for target project

**Testing Thread Disambiguation**:

```bash
# Set project context
watercooler_v1_set_project(project="proj-alpha")

# Attempt to write to non-existent thread (fails)
watercooler_v1_say(topic="new-topic", title="Test", body="Content")
# Error: Thread 'new-topic' not found in project 'proj-alpha'.
#        Use create_if_missing=true to create it.

# Explicitly create new thread
watercooler_v1_say(
  topic="new-topic",
  title="Test",
  body="Content",
  create_if_missing=true
)
# Success: Thread created in proj-alpha

# Cross-project read (requires ACL access)
watercooler_v1_read_thread(topic="existing-thread", project="proj-beta")
# Success if user has access to proj-beta
# Response includes _metadata: { project_id: "proj-beta", cross_project: true, session_project: "proj-alpha" }
```

**Testing Cross-Project Discovery**:

```bash
# Create thread in proj-alpha
watercooler_v1_set_project(project="proj-alpha")
watercooler_v1_say(topic="shared-topic", title="Alpha Entry", body="Content", create_if_missing=true)

# Switch to proj-beta
watercooler_v1_set_project(project="proj-beta")

# Attempt to access thread (thread exists in different project)
watercooler_v1_read_thread(topic="shared-topic")
# Error: Thread 'shared-topic' not found in project 'proj-beta'.
#        Thread exists in: [proj-alpha].
#        Use set_project or specify project explicitly.

# Access via explicit project parameter
watercooler_v1_read_thread(topic="shared-topic", project="proj-alpha")
# Success: Returns thread content
```

**What this validates**:
- ✅ No accidental thread creation (default `create_if_missing=false`)
- ✅ Clear error messages when thread not found
- ✅ Cross-project thread discovery helps locate threads
- ✅ Explicit project parameter works for all thread tools
- ✅ Metadata includes project context for all operations
- ✅ ACL validation enforced for cross-project access

**Error Codes**:
- `-32001`: Project not set (call `set_project` first)
- `-32002`: Thread not found (with hints about where it exists)
- `-32000`: Access denied for project (user not in ACL)

---

## Understanding Through Troubleshooting

Troubleshooting isn't just about fixing errors—it's an opportunity to deepen your understanding of the architecture. This section organizes common issues by architectural layer, helping you learn *why* failures occur and *what* they teach about the system.

### Authentication Layer (OAuth & Sessions)

#### "OAuth error: Unexpected token 'R'"

**What happened**: GitHub returned an HTML error page instead of JSON token response

**Why this matters**: OAuth callback URL misconfiguration is the most common deployment issue

**Root cause**:
- OAuth app's callback URL doesn't match Worker's actual callback URL
- Most common: Trailing slash mismatch
  - OAuth app: `https://worker.dev/auth/callback/` ❌
  - Worker expects: `https://worker.dev/auth/callback` ✅

**How to fix**:
1. Check OAuth app settings:
   ```
   https://github.com/organizations/<org>/settings/applications
   ```
2. Verify callback URL exactly matches (no trailing slash):
   ```
   https://<your-subdomain>.workers.dev/auth/callback
   ```
3. Check secrets are set:
   ```bash
   wrangler secret list
   # Expected: GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET
   ```
4. Verify client ID/secret are current (regenerate if doubt exists)

**Debug with logs**:
```bash
./scripts/tail-logs.sh auth
# Look for: "oauth_error" event with detailed error message
```

**What this teaches**: OAuth relies on exact URL matching for security. GitHub validates callback URLs to prevent redirect attacks where attackers steal authorization codes.

---

#### "client_id=undefined on login redirect"

**What happened**: The GitHub authorization URL was constructed with `client_id=undefined`, leading to a GitHub 404 or an immediate failure to render the OAuth page.

**Root cause**:
- Cloudflare Worker secrets were not configured for the active environment (staging/production). Wrangler secrets are environment‑scoped, so setting only the default scope leaves `env.GITHUB_CLIENT_ID` and `env.GITHUB_CLIENT_SECRET` undefined in non‑default environments.

**How to fix (per environment)**:
```bash
cd cloudflare-worker

# Recommended: interactive helper (sets all three secrets)
./scripts/set-secrets.sh --env staging     # or --env production

# Alternatively: set explicitly with wrangler
echo "<GITHUB_CLIENT_ID>"        | npx wrangler secret put GITHUB_CLIENT_ID --env staging
echo "<GITHUB_CLIENT_SECRET>"    | npx wrangler secret put GITHUB_CLIENT_SECRET --env staging
echo "<INTERNAL_AUTH_SECRET>"    | npx wrangler secret put INTERNAL_AUTH_SECRET --env staging
```

**Verify**:
- List secrets for the target environment:
  ```bash
  npx wrangler secret list --env staging   # expect: GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, INTERNAL_AUTH_SECRET
  ```
- Probe the Worker’s debug endpoint (reports presence/lengths only):
  ```bash
  curl -sS https://<your-worker-domain>/debug/secrets | jq
  # { has_github_client_id: true, github_client_id_length: 20, ... }
  ```

**What this teaches**:
- Secrets are environment‑scoped in Wrangler; always pass `--env <env>` when setting and listing.
- OAuth failures can originate from missing env bindings rather than code; add a preflight secrets check to every deploy.

#### "CSRF state invalid" or "State mismatch"

**What happened**: CSRF protection working correctly (this is good!)

**Why this matters**: Shows anti-CSRF defenses are active

**Root cause**:
- User tried to reuse an OAuth callback URL (e.g., from browser history)
- OAuth state parameter is single-use (deleted from KV after first callback)
- Or: Cookies were cleared/expired between login and callback

**How to "fix"**:
- Not actually an error—this is correct behavior
- Start fresh from `/auth/login` (don't bookmark or reuse callback URLs)

**What this teaches**:
- OAuth state parameter prevents CSRF attacks
- State is stored in two places: KV (server-side) and cookie (client-side)
- Both must match and state must exist in KV
- After validation, state is deleted (one-time use prevents replay attacks)

**CSRF attack scenario prevented**:
```
1. Attacker initiates OAuth flow, gets state=ATTACKER_STATE
2. Attacker tricks victim into clicking:
   /auth/callback?code=VICTIM_CODE&state=ATTACKER_STATE
3. Worker checks:
   - state from URL (ATTACKER_STATE)
   - state from victim's cookie (VICTIM_STATE)
   - States don't match → 403 Forbidden ✓

Without this protection, attacker would hijack victim's OAuth code and gain access to victim's account.
```

---

#### "Access denied - No project permissions"

**What happened**: User authenticated successfully but has no ACL entry

**Why this matters**: Shows default-deny security working correctly

**Root cause**:
- User completed OAuth flow (authentication ✓)
- But user has no ACL entry in KV (authorization ❌)
- Default-deny means: no ACL = no access

**How to fix**:
```bash
# Grant user access to projects
cd cloudflare-worker
./scripts/seed-acl.sh <github-login> <project-name>

# Verify ACL was set
./scripts/seed-acl.sh <github-login> --show
```

**Debug steps**:
1. Confirm user is authenticated:
   ```bash
   # Check session exists in KV
   wrangler kv:key list --binding=KV_PROJECTS --prefix="session:"
   # Should see session:<uuid> entries
   ```

2. Check user's ACL:
   ```bash
   wrangler kv:key get "user:gh:<login>" --binding=KV_PROJECTS
   # If "404 key not found" → No ACL entry (expected)
   ```

3. View logs to confirm ACL denial reason:
   ```bash
   ./scripts/tail-logs.sh acl
   # Look for: {"event":"acl_denied","reason":"no_acl_entry",...}
   ```

**What this teaches**:
- **Authentication ≠ Authorization**: Being logged in doesn't grant access
- **Default-deny is fail-safe**: Misconfiguration results in denied access (safe) not exposed data (dangerous)
- **Explicit permissions**: Every user-project pair must be explicitly allowed

---

#### "Unauthorized - Dev session not allowed"

**What happened**: Tried to use `?session=dev` but `ALLOW_DEV_SESSION` not enabled

**Why this matters**: Production security working correctly

**Root cause**:
- User tried to connect with `?session=dev` (dev bypass)
- `ALLOW_DEV_SESSION` is not set to `"true"` in `wrangler.toml`
- Production default: dev sessions are disabled

**How to fix** (choose based on environment):

**If this is staging** (and you explicitly want dev session for temporary testing):
```toml
# In wrangler.toml under [env.staging]
[env.staging]
vars = {
  ALLOW_DEV_SESSION = "true",  # TEMPORARY: enable dev session for testing only
  ...
}
```

**If this is production** (dev sessions should stay disabled):
- Do not enable `ALLOW_DEV_SESSION` in production
- Prefer OAuth (`/auth/login`) or issue a token at `/console` and use `Authorization: Bearer <token>`
- Dev sessions are a security bypass for testing only

**What this teaches**:
- **Environment-specific security**: Staging can have looser security for testing, production must be strict
- **Defense in depth**: Even if attacker knows about `?session=dev`, it only works in staging
- **Never enable dev shortcuts in production**: Convenience features create security holes

---

#### "Rate limit exceeded"

**What happened**: Too many OAuth callback attempts from same IP

**Why this matters**: Anti-DoS protection working correctly

**Root cause**:
- More than 10 OAuth callback attempts from same IP within 5 minutes
- Rate limiting uses KV token bucket: `ratelimit:oauth:cb:{ip}` → counter

**How to fix**:

**Wait it out** (automatic reset):
- Rate limit resets after 5 minutes
- Counter expires via KV TTL

**Manual reset** (for legitimate testing):
```bash
# Find your IP
curl ifconfig.me

# Clear rate limit counter
wrangler kv:key delete "ratelimit:oauth:cb:<your-ip>" --binding=KV_PROJECTS
```

**What this teaches**:
- **Rate limiting prevents brute force**: 10 attempts / 5 min is enough for legitimate use, too slow for attacks
- **IP-based limiting**: Per-IP prevents distributed attacks from requiring per-user tracking
- **KV TTL for automatic cleanup**: Rate limit counters auto-expire, no manual cleanup needed
- **HTTP 429 + Retry-After header**: Client knows to wait (5 min = 300 seconds)

**Attack scenario prevented**:
```
Attacker tries to brute force OAuth:
- Attempt 1-10: Worker processes normally
- Attempt 11+: 429 Too Many Requests
- Attacker must wait 5 minutes before trying again
- At 10 attempts / 5 min, testing 100 tokens takes 50 minutes
- Makes brute force impractical
```

---

### Authorization Layer (ACL)

#### "Access denied: Project not in allowlist"

**What happened**: User has ACL entry but specific project not allowed

**Why this matters**: Granular project-level authorization working

**Root cause**:
- User authenticated ✓
- User has ACL entry ✓
- But user's allowlist doesn't include requested project ❌

**Example**:
```json
// User's ACL
{
  "projects": ["proj-alpha", "proj-beta"]
}

// User requests ?project=proj-gamma
// Result: 403 Access Denied (proj-gamma not in allowlist)
```

**How to fix**:
```bash
# Add project to user's allowlist
./scripts/seed-acl.sh <github-login> proj-gamma

# This merges with existing projects:
# Before: ["proj-alpha", "proj-beta"]
# After:  ["proj-alpha", "proj-beta", "proj-gamma"]
```

**Debug steps**:
```bash
# View current allowlist
./scripts/seed-acl.sh <github-login> --show

# Check logs for exact denial reason
./scripts/tail-logs.sh acl
# Look for: {"event":"acl_denied","reason":"project_not_in_allowlist","allowlist":[...]}
```

**What this teaches**:
- **Granular permissions**: Users can have access to some projects but not others
- **Project isolation**: Even authenticated users can't access projects they shouldn't see
- **Allowlist is additive**: Adding projects doesn't remove existing access

---

### Worker ↔ Backend Layer

#### "403 Invalid internal authentication"

**What happened**: Backend rejected request due to `X-Internal-Auth` header mismatch

**Why this matters**: Service-to-service authentication prevents Backend bypass

**Root cause**:
- Worker's `INTERNAL_AUTH_SECRET` doesn't match Backend's `INTERNAL_AUTH_SECRET`
- Common causes:
  - Typo when setting secret
  - Trailing newline in secret (from copy-paste)
  - Secret rotated on one side but not other

**How to fix**:

1. **Regenerate secret on Worker**:
   ```bash
   cd cloudflare-worker
   openssl rand -hex 32  # Generate new secret
   echo -n "<new-secret>" | wrangler secret put INTERNAL_AUTH_SECRET
   # Note: -n flag prevents newline
   ```

2. **Set exact same secret on Backend** (Render example):
   - Dashboard → Environment → `INTERNAL_AUTH_SECRET`
   - Copy-paste same value (no extra whitespace)
   - Save (triggers redeploy)

3. **Verify match**:
   ```bash
   # Test Backend directly with secret
   curl -X POST https://backend.onrender.com/mcp/watercooler_v1_health \
     -H "X-Internal-Auth: <secret>" \
     -H "X-User-Id: gh:test" \
     -H "X-Project-Id: test" \
     -H "X-Agent-Name: Claude"
   # Expected: 200 OK (if secret correct)
   # Expected: 403 (if secret wrong)
   ```

**What this teaches**:
- **Shared secrets must be exactly identical**: Single character difference breaks auth
- **Whitespace matters**: Trailing newlines, spaces, tabs count as part of secret
- **Secret rotation requires coordination**: Both sides must update simultaneously
- **Defense in depth**: Even if Worker security were bypassed, Backend validates its own secret

**Attack scenario prevented**:
```
Attacker tries to access Backend directly (bypass Worker's OAuth/ACL):
1. Attacker sends request to Backend /mcp/ endpoint
2. Backend checks X-Internal-Auth header
3. Header missing or wrong → 403 Forbidden ✓
4. Attacker can't bypass Worker's security layer

Without this protection, attacker could access Backend directly and bypass:
- OAuth authentication
- CSRF protection
- Session validation
- ACL enforcement
```

---

#### "Backend refuses to start: 'INTERNAL_AUTH_SECRET is required'"

**What happened**: Backend fail-fast validation working correctly

**Why this matters**: Prevents accidentally running unsecured Backend in production

**Root cause**:
- Backend checks for `INTERNAL_AUTH_SECRET` on startup
- If missing in production (when `ALLOW_DEV_MODE != "true"`), Backend refuses to start
- This is **intentional fail-fast behavior**

**How to fix**:

**For production/staging** (set the secret):
```bash
# Render: Dashboard → Environment → Add Variable
# Name: INTERNAL_AUTH_SECRET
# Value: <32+ character random string, same as Worker>
```

**For local development** (allow dev mode):
```bash
# In local .env or environment
export ALLOW_DEV_MODE=true
export INTERNAL_AUTH_SECRET=dev-secret-not-for-production
```

**What this teaches**:
- **Fail-fast > fail-open**: Better to refuse to start than run insecurely
- **Environment-aware validation**: Strict in production, lenient in dev
- **Configuration errors caught at startup**: Not at first request (when damage could occur)

---

#### "500: clone into non-empty directory"

**What happened**: Git tried to clone into directory that already has files

**Why this matters**: Shows Git sync initialization order matters

**Root cause**:
- `WATERCOOLER_DIR` (Git working tree) and `BASE_THREADS_ROOT` (app data) point to same location
- Directory already has thread files from previous runs
- Git `clone` refuses to overwrite non-empty directory

**How to fix**:

**Option 1: Align paths and use proper Start command**:
```bash
# Ensure both point to same directory
WATERCOOLER_DIR=/data/wc-cloud
BASE_THREADS_ROOT=/data/wc-cloud

# Use Start command that clones BEFORE writing files
# (See Manual Setup → Backend Configuration for full command)
```

**Option 2: Clear and re-clone** (destructive):
```bash
# On Backend (Render Web Shell)
rm -rf /data/wc-cloud/*
# Restart service (triggers clone)
```

**Option 3: Initialize Git in existing directory**:
```bash
cd /data/wc-cloud
git init
git remote add origin git@github.com:org/watercooler-threads.git
git fetch
git checkout -b main origin/main
```

**What this teaches**:
- **Initialization order matters**: Git clone must happen before app writes files
- **Path alignment is critical**: Working tree and data root must be same directory
- **Start commands control initialization**: Proper startup script handles clone-then-run order

---

### Client Connection Issues

#### "Use Accept: text/event-stream"

**What happened**: Client didn't request SSE format

**Why this matters**: SSE endpoint requires specific Accept header

**Root cause**:
- Client sent request to `/sse` without `Accept: text/event-stream` header
- Worker validates Accept header to ensure client can handle SSE format

**How to fix**:

**If using curl**:
```bash
curl -H "Accept: text/event-stream" \
  -H "Cookie: session=<uuid>" \
  "https://worker.dev/sse?project=proj-alpha"
```

**If using MCP client**:
- MCP clients automatically set correct Accept header
- If seeing this error, check MCP client configuration
- Ensure URL points to `/sse` endpoint (not `/messages`)

**What this teaches**:
- **SSE requires specific headers**: Server-Sent Events is an HTTP standard with required Accept header
- **Content negotiation**: Worker validates client can handle response format before processing request

---

## Security Deep Dive

This section provides in-depth explanations of security mechanisms for those who want to fully understand the system's defenses.

### OAuth 2.0 Flow (Step-by-Step with State)

**Phase 1: Initiation** (`GET /auth/login`)

```
1. User visits /auth/login
   ↓
2. Worker generates cryptographic state parameter:
   const state = crypto.randomUUID()  // e.g., "a1b2c3d4-..."
   ↓
3. Worker stores state in KV (server-side):
   KV.put("oauth:state:a1b2c3d4-...", "1", { expirationTtl: 600 })  // 10 min
   ↓
4. Worker sets state cookie (client-side):
   Set-Cookie: oauth_state=a1b2c3d4-...; HttpOnly; Secure; SameSite=Lax; Max-Age=600
   ↓
5. Worker redirects to GitHub OAuth:
   Location: https://github.com/login/oauth/authorize?
     client_id=<CLIENT_ID>&
     redirect_uri=https://worker.dev/auth/callback&
     state=a1b2c3d4-...&
     scope=read:user
```

**Why store state in both KV and cookie?**
- **KV (server-side)**: Proves Worker initiated this OAuth flow (not an attacker)
- **Cookie (client-side)**: Proves same browser that started flow is completing it
- **Both must match**: Prevents CSRF even if attacker learns state value

---

**Phase 2: GitHub Authorization**

```
1. GitHub shows authorization screen to user
   "Authorize Watercooler Remote MCP to access your account?"
   ↓
2. User clicks "Authorize"
   ↓
3. GitHub validates:
   - client_id matches registered OAuth app ✓
   - redirect_uri matches OAuth app's allowed callback URLs ✓
   - User is logged into GitHub ✓
   ↓
4. GitHub generates authorization code (one-time use)
   ↓
5. GitHub redirects user to callback:
   Location: https://worker.dev/auth/callback?
     code=<AUTHORIZATION_CODE>&
     state=a1b2c3d4-...
```

---

**Phase 3: Callback Validation** (`GET /auth/callback`)

```
1. Worker receives callback request with:
   - URL params: code=<CODE>, state=<STATE_FROM_URL>
   - Cookie: oauth_state=<STATE_FROM_COOKIE>
   ↓
2. Worker validates CSRF protection:

   a) Extract state from cookie:
      const cookieState = request.cookies.get("oauth_state")

   b) Extract state from URL:
      const urlState = new URL(request.url).searchParams.get("state")

   c) Check states match:
      if (urlState !== cookieState) {
        return 403 "CSRF state mismatch"  // Cookie/URL state differ
      }

   d) Check state exists in KV (server-side validation):
      const kvState = await KV.get(`oauth:state:${urlState}`)
      if (!kvState) {
        return 403 "Invalid or expired state"  // State not in KV
      }

   e) Delete state from KV (one-time use):
      await KV.delete(`oauth:state:${urlState}`)
      // Prevents reuse of same state
   ↓
3. All CSRF checks passed ✓
```

**Why three checks (URL + cookie + KV)?**

| Check | Prevents |
|-------|----------|
| URL state = Cookie state | Attacker using victim's browser to complete attacker's OAuth flow |
| State exists in KV | Attacker fabricating state values (KV proves Worker created it) |
| Delete after use | Attacker replaying captured callback URLs |

---

**Phase 4: Token Exchange**

```
1. Worker exchanges authorization code for access token:

   POST https://github.com/login/oauth/access_token
   Headers:
     Accept: application/json
   Body:
     client_id=<CLIENT_ID>
     client_secret=<CLIENT_SECRET>
     code=<AUTHORIZATION_CODE>
   ↓
2. GitHub validates:
   - client_id + client_secret authenticate Worker ✓
   - code is valid and not expired ✓
   - code hasn't been used before ✓
   ↓
3. GitHub returns access token:
   { "access_token": "gho_...", "scope": "read:user", "token_type": "bearer" }
   ↓
4. Worker fetches user info:

   GET https://api.github.com/user
   Headers:
     Authorization: Bearer gho_...
   ↓
5. GitHub returns user profile:
   {
     "login": "octocat",
     "id": 583231,
     "avatar_url": "https://avatars.github.com/u/583231?v=4",
     ...
   }
```

---

**Phase 5: Session Creation**

```
1. Worker generates session ID:
   const sessionId = crypto.randomUUID()  // e.g., "s1s2s3s4-..."
   ↓
2. Worker stores session in KV:
   await KV.put(
     `session:${sessionId}`,
     JSON.stringify({
       userId: `gh:${user.login}`,  // e.g., "gh:octocat"
       login: user.login,            // e.g., "octocat"
       avatar: user.avatar_url
     }),
     { expirationTtl: 86400 }  // 24 hours
   )
   ↓
3. Worker sets session cookie:
   Set-Cookie: session=s1s2s3s4-...;
     HttpOnly;        // JavaScript can't access (prevents XSS theft)
     Secure;          // Only sent over HTTPS (prevents interception)
     SameSite=Lax;    // Only sent to same site (prevents CSRF)
     Max-Age=86400;   // 24 hours
     Path=/           // Valid for all paths
   ↓
4. User now has authenticated session
   Browser will include Cookie: session=s1s2s3s4-... on future requests
```

---

### CSRF Attack Vector & Protection Mechanism

**What is CSRF in OAuth context?**

Cross-Site Request Forgery (CSRF) in OAuth allows an attacker to link their OAuth account to victim's session.

**Attack Scenario (without protection)**:

```
1. Attacker initiates OAuth flow for their own GitHub account:
   /auth/login → state=ATTACKER_STATE
   GitHub redirects to:
   /auth/callback?code=ATTACKER_CODE&state=ATTACKER_STATE
   ↓
2. Attacker captures this callback URL
   ↓
3. Attacker tricks victim into clicking callback URL:
   <img src="/auth/callback?code=ATTACKER_CODE&state=ATTACKER_STATE">
   ↓
4. WITHOUT CSRF PROTECTION:
   - Worker would process callback in victim's browser context
   - Worker would create session linking ATTACKER's GitHub to VICTIM's cookies
   - Victim now logged in as attacker
   - Attacker sees victim's activity (data leakage)

WITH CSRF PROTECTION:
   - Worker checks state parameter
   - state=ATTACKER_STATE doesn't match victim's oauth_state cookie
   - 403 Forbidden ✓
   - Attack fails
```

**How our protection works**:

```
Victim flow:
1. Victim clicks /auth/login
   Worker sets: Cookie: oauth_state=VICTIM_STATE
   KV stores: oauth:state:VICTIM_STATE → "1"
   ↓
2. Attacker tries to inject their callback:
   /auth/callback?code=ATTACKER_CODE&state=ATTACKER_STATE
   ↓
3. Worker validates:
   - URL state = ATTACKER_STATE
   - Cookie state = VICTIM_STATE
   - ATTACKER_STATE ≠ VICTIM_STATE → 403 Forbidden ✓

Even if attacker learns VICTIM_STATE:
1. Attacker uses victim's state:
   /auth/callback?code=ATTACKER_CODE&state=VICTIM_STATE
   ↓
2. Worker validates:
   - URL state = VICTIM_STATE ✓
   - Cookie state = VICTIM_STATE ✓
   - KV check: oauth:state:VICTIM_STATE exists ✓
   - But: code=ATTACKER_CODE is for attacker's account
   ↓
3. GitHub token exchange:
   - Worker sends ATTACKER_CODE to GitHub
   - GitHub returns attacker's access token (not victim's)
   - Worker fetches user info → attacker's profile
   - Session created for attacker (no privilege escalation)
```

**Why this defense works**:
- State parameter ties OAuth flow to specific browser session
- Server-side KV storage prevents state fabrication
- Client-side cookie prevents state substitution
- One-time use prevents replay attacks

---

### Session Fixation & Prevention

**What is session fixation?**

Session fixation is when an attacker sets a victim's session ID to a value the attacker knows, then uses that knowledge to hijack the session.

**Attack Scenario (vulnerable implementation)**:

```
VULNERABLE CODE (don't use):
// Accept session ID from query parameter
const sessionId = url.searchParams.get("session") || crypto.randomUUID()

Attack:
1. Attacker creates URL: /sse?session=ATTACKER_CHOSEN_ID&project=proj-alpha
2. Attacker tricks victim into clicking link
3. Worker accepts session=ATTACKER_CHOSEN_ID from URL
4. Victim authenticates with this session ID
5. Attacker uses same session ID: /sse?session=ATTACKER_CHOSEN_ID
6. Attacker now has victim's authenticated session ✗
```

**Our Prevention**:

```typescript
// Worker code (simplified)
async function validateSession(request: Request): Promise<Session | null> {
  // ONLY accept session from cookie (not query params)
  const sessionId = getCookie(request, "session")

  // Reject query param sessions (unless dev mode enabled)
  const querySession = new URL(request.url).searchParams.get("session")
  if (querySession) {
    if (env.ALLOW_DEV_SESSION === "true" && querySession === "dev") {
      // Dev session allowed only in staging
      return { userId: "gh:dev", login: "dev", avatar: "" }
    }
    // Query param sessions rejected in production
    return null  // → 401 Unauthorized
  }

  // Look up session in KV
  if (!sessionId) return null

  const sessionData = await env.KV_PROJECTS.get(`session:${sessionId}`)
  if (!sessionData) return null  // Expired or invalid

  return JSON.parse(sessionData)
}
```

**Why this works**:
- **Cookies are set by server**, not controllable via URL by attacker
- **HttpOnly flag** prevents JavaScript from reading/setting cookies (XSS protection)
- **Secure flag** ensures cookies only sent over HTTPS (prevents interception)
- **SameSite=Lax** prevents cookies from being sent on cross-site requests (CSRF protection)

**Dev session exception** (staging only):
- `?session=dev` allowed when `ALLOW_DEV_SESSION=true`
- Used for testing without OAuth
- Logs warning on every use
- **Never enabled in production** (deploy.sh validates this)

---

### Rate Limiting Algorithm

**Goal**: Prevent brute force attacks on OAuth callback endpoint

**Implementation**: Token bucket algorithm using KV storage

**Configuration**:
- **Limit**: 10 attempts per 5 minutes
- **Scope**: Per IP address
- **Endpoint**: `/auth/callback` (most vulnerable to abuse)

**Algorithm**:

```typescript
async function checkRateLimit(ip: string): Promise<boolean> {
  const key = `ratelimit:oauth:cb:${ip}`

  // Get current count
  const current = await KV.get(key)
  const count = current ? parseInt(current) : 0

  // Check if limit exceeded
  if (count >= 10) {
    return false  // Rate limited
  }

  // Increment counter
  await KV.put(
    key,
    (count + 1).toString(),
    { expirationTtl: 300 }  // 5 minutes = 300 seconds
  )

  return true  // Allowed
}

// Usage in OAuth callback handler
if (!await checkRateLimit(clientIP)) {
  return new Response("Rate limit exceeded", {
    status: 429,
    headers: { "Retry-After": "300" }  // Client should wait 5 minutes
  })
}
```

**How it works**:

```
Time 0:00 - First attempt from IP 1.2.3.4
  KV: ratelimit:oauth:cb:1.2.3.4 → "1" (TTL: 300s)
  Response: 200 OK

Time 0:01 - Second attempt
  KV: ratelimit:oauth:cb:1.2.3.4 → "2" (TTL: 299s)
  Response: 200 OK

... (8 more attempts) ...

Time 0:09 - Tenth attempt
  KV: ratelimit:oauth:cb:1.2.3.4 → "10" (TTL: 291s)
  Response: 200 OK

Time 0:10 - Eleventh attempt
  KV: ratelimit:oauth:cb:1.2.3.4 → "10" (still < 300s since first)
  count >= 10 → 429 Too Many Requests
  Response: Rate limit exceeded, Retry-After: 300

Time 5:00 - First attempt after 5 minutes
  KV: ratelimit:oauth:cb:1.2.3.4 → (expired, deleted)
  count = 0 → Allowed again
```

**Why this approach**:
- **KV TTL handles cleanup**: No manual counter reset needed
- **Per-IP isolation**: One attacker can't exhaust limit for all users
- **Sliding window via TTL**: Counter expires 5 minutes from first attempt
- **Retry-After header**: Well-behaved clients know when to retry

**Attack scenario prevented**:

```
Attacker tries to brute force OAuth codes:
1. Attacker has stolen state parameter (somehow)
2. Attacker tries to guess authorization codes:
   /auth/callback?code=guess1&state=<STATE>
   /auth/callback?code=guess2&state=<STATE>
   ...
   /auth/callback?code=guess10&state=<STATE>
   → All fail (GitHub rejects invalid codes)

3. Attempt 11:
   → 429 Rate Limited
   → Must wait 5 minutes

At 10 guesses / 5 minutes:
- Testing 100 codes takes 50 minutes
- Testing 1000 codes takes 8.3 hours
- Testing 10000 codes takes 3.5 days
- Brute force becomes impractical
```

---

### ACL Enforcement Timing

**When ACL checks happen**: After authentication, before proxying to Backend

**Request pipeline**:

```
1. Client request arrives
   ↓
2. Extract session from cookie
   ↓
3. Validate session (look up in KV)
   ← If no session: 401 Unauthorized ❌
   ↓
4. Extract project from query params
   ↓
5. Fetch user's ACL from KV
   key: user:gh:<login>
   ← If no ACL entry: 403 Access Denied ❌
   ↓
6. Check if project in allowlist
   ← If project not in list: 403 Access Denied ❌
   ↓
7. All checks passed ✓
   ↓
8. Proxy to Backend with identity headers:
   X-User-Id: gh:<login>
   X-Project-Id: <project>
   X-Agent-Name: <agent>
   X-Internal-Auth: <secret>
```

**Code flow** (TypeScript, simplified):

```typescript
async function handleSSERequest(request: Request, env: Env): Promise<Response> {
  // 1. Authenticate (session validation)
  const session = await validateSession(request, env)
  if (!session) {
    return new Response("Unauthorized", { status: 401 })
  }

  // 2. Extract project
  const url = new URL(request.url)
  const project = url.searchParams.get("project")
  if (!project) {
    return new Response("Project parameter required", { status: 400 })
  }

  // 3. Authorize (ACL check)
  const userId = session.userId  // e.g., "gh:octocat"
  const login = userId.replace("gh:", "")  // e.g., "octocat"

  // Fetch ACL from KV
  const aclData = await env.KV_PROJECTS.get(`user:${userId}`)
  if (!aclData) {
    // No ACL entry → default deny
    await logEvent({
      event: "acl_denied",
      user: userId,
      project,
      reason: "no_acl_entry"
    })
    return new Response("Access denied - No project permissions", {
      status: 403
    })
  }

  // Parse ACL
  const acl = JSON.parse(aclData)
  const allowedProjects = acl.projects || []

  // Check project in allowlist
  if (!allowedProjects.includes(project)) {
    await logEvent({
      event: "acl_denied",
      user: userId,
      project,
      reason: "project_not_in_allowlist",
      allowlist: allowedProjects
    })
    return new Response(
      `Access denied - Project ${project} not in allowlist`,
      { status: 403 }
    )
  }

  // 4. ACL check passed
  await logEvent({
    event: "acl_allowed",
    user: userId,
    project
  })

  // 5. Proxy to backend
  return proxyToBackend(request, {
    userId,
    projectId: project,
    agentName: env.DEFAULT_AGENT,
    internalSecret: env.INTERNAL_AUTH_SECRET
  })
}
```

**Why check ACL at Worker (not Backend)**:

| Approach | Pros | Cons |
|----------|------|------|
| **Worker checks ACL** (our approach) | • Denies at edge (low latency)<br>• Backend doesn't need ACL logic<br>• Reduces Backend load (invalid requests rejected early) | • ACL data in KV (edge storage)<br>• Worker code slightly more complex |
| Backend checks ACL | • Centralized authorization logic<br>• ACL data in Backend database | • Every request hits Backend (higher latency)<br>• Backend does work for denied requests<br>• Backend needs ACL database |

**Security benefit of edge enforcement**:
- Unauthorized requests never reach Backend
- Attack surface reduced (Backend only sees pre-authorized traffic)
- DDoS mitigation (edge rejects malicious requests, Backend stays healthy)

---

### Service-to-Service Authentication

**Problem**: Backend must distinguish between:
- Legitimate requests from Worker (trusted, should process)
- Direct requests from internet (untrusted, should reject)

**Solution**: Shared secret authentication via `X-Internal-Auth` header

**Flow**:

```
Worker → Backend Request:
POST /mcp/watercooler_v1_health
Headers:
  X-Internal-Auth: f4e7d2c1b0a9...  ← Shared secret
  X-User-Id: gh:octocat             ← User identity
  X-Project-Id: proj-alpha          ← Project context
  X-Agent-Name: Claude              ← Agent name

Backend validation:
1. Extract X-Internal-Auth header
2. Compare to INTERNAL_AUTH_SECRET env var
3. If match: Process request ✓
4. If no match: 403 Forbidden ❌
```

**Backend implementation** (Python FastAPI, simplified):

```python
from fastapi import Request, HTTPException
import os

INTERNAL_AUTH_SECRET = os.getenv("INTERNAL_AUTH_SECRET")

# Fail-fast on startup
if not INTERNAL_AUTH_SECRET and os.getenv("ALLOW_DEV_MODE") != "true":
    raise RuntimeError("INTERNAL_AUTH_SECRET is required in production")

async def validate_internal_auth(request: Request):
    """Middleware to validate Worker authentication"""

    # Extract header
    auth_header = request.headers.get("X-Internal-Auth")

    # Check header exists
    if not auth_header:
        raise HTTPException(status_code=403, detail="Missing internal authentication")

    # Constant-time comparison (prevents timing attacks)
    import secrets
    if not secrets.compare_digest(auth_header, INTERNAL_AUTH_SECRET):
        raise HTTPException(status_code=403, detail="Invalid internal authentication")

    # Authentication passed
    return True

@app.post("/mcp/watercooler_v1_health")
async def health_check(request: Request):
    # Validate Worker auth
    await validate_internal_auth(request)

    # Trust Worker-provided identity headers
    user_id = request.headers.get("X-User-Id")
    project_id = request.headers.get("X-Project-Id")
    agent_name = request.headers.get("X-Agent-Name")

    # Process request with trusted identity
    return {"status": "healthy", "user": user_id, "project": project_id}
```

**Why trust identity headers after secret validation?**

1. Worker authenticated via shared secret ✓
2. If Worker is compromised, attacker has secret (game over anyway)
3. Simpler than separate user authentication to Backend
4. Worker is trust boundary (handles OAuth, sessions, ACL)

**Security model**:

```
Trust Zones:

┌─────────────────────────┐
│   Untrusted Internet    │ ← No secrets, no access
└────────────┬────────────┘
             │ OAuth flow (user auth)
             ▼
┌─────────────────────────┐
│   Cloudflare Worker     │ ← Has secrets, enforces OAuth + ACL
│   (Trust Boundary)      │
└────────────┬────────────┘
             │ X-Internal-Auth (service auth)
             │ + Identity headers (trusted claims)
             ▼
┌─────────────────────────┐
│   FastAPI Backend       │ ← Trusts Worker (after secret validation)
│   (Trusted Zone)        │
└─────────────────────────┘
```

**Attack scenarios**:

**Scenario 1: Direct Backend access**
```
Attacker → Backend /mcp/watercooler_v1_say
Request:
  X-User-Id: gh:victim
  X-Project-Id: secret-project
  (no X-Internal-Auth header)

Backend validation:
  X-Internal-Auth missing → 403 Forbidden ✓
  Attack fails
```

**Scenario 2: Wrong secret**
```
Attacker → Backend /mcp/watercooler_v1_say
Request:
  X-Internal-Auth: attacker-guess-123
  X-User-Id: gh:victim
  X-Project-Id: secret-project

Backend validation:
  attacker-guess-123 ≠ INTERNAL_AUTH_SECRET
  → 403 Forbidden ✓
  Attack fails
```

**Scenario 3: Correct secret (Worker compromised)**
```
Attacker has stolen INTERNAL_AUTH_SECRET (Worker compromised)

Attacker → Backend /mcp/watercooler_v1_say
Request:
  X-Internal-Auth: <CORRECT_SECRET>
  X-User-Id: gh:victim
  X-Project-Id: secret-project

Backend validation:
  Secret matches → Request processed ❌

Note: If attacker has secret, they've compromised Worker.
At this point, they could also:
- Read all sessions from KV
- Modify ACLs
- Impersonate any user via Worker

Defense: Secret rotation + incident response
```

---

## Reference

---

## FAQ (Quick Answers)

- “What is KV?”  
  Cloudflare Workers KV: a global key–value store the Worker uses for sessions (`session:{uuid}`), OAuth CSRF state (`oauth:state:{state}`), ACLs (`user:gh:{login}`), and rate‑limit buckets (`ratelimit:*`).

- “What is an ACL?”  
  Access Control List: a per‑user allowlist of projects. We enforce default‑deny at the Worker; if a project isn’t listed for your login, the request is rejected with 403.

- “Why do I get 401 on /sse?”  
  No authenticated session. Visit `/auth/login` (OAuth). In production we don’t accept `?session=dev`.

- “Why do I get 406 on /sse?”  
  Missing `Accept: text/event-stream`. SSE endpoints require this header.

- “Why do I get 403 on /sse?project=…?”  
  You are not allowed for that project. Ask an operator to add it to your KV ACL allowlist.

- “Why do I get 429 on /auth/callback?”  
  Rate limit exceeded (e.g., >10 requests in 5 min per IP). Wait or try staging.

- “How do I enable Git backup?”  
  Set `WATERCOOLER_GIT_REPO`, `WATERCOOLER_DIR=/data/wc-cloud`, `GIT_SSH_PRIVATE_KEY` (PEM). Use the copy/paste one‑liner start command to clone/init and push `HEAD`.

- “How do I rotate INTERNAL_AUTH_SECRET?”  
  Update Worker secret and Backend env to the same new value; redeploy both.


### Environment Variables

#### Worker (Cloudflare)

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `GITHUB_CLIENT_ID` | Secret | ✅ Yes | GitHub OAuth app client ID (from OAuth app settings) |
| `GITHUB_CLIENT_SECRET` | Secret | ✅ Yes | GitHub OAuth app client secret (generate new if needed) |
| `INTERNAL_AUTH_SECRET` | Secret | ✅ Yes | Shared secret for Worker↔Backend auth (32+ random chars) |
| `BACKEND_URL` | Var | ✅ Yes | FastAPI backend URL (e.g., `https://watercooler.onrender.com`) |
| `DEFAULT_AGENT` | Var | ✅ Yes | Default agent name (e.g., `"Claude"`) |
| `ALLOW_DEV_SESSION` | Var | ⚠️ Staging | Optional; default disabled. If set to `"true"`, allows `?session=dev` for temporary testing in staging (NEVER in prod). Prefer OAuth or issued tokens. |
| `AUTO_ENROLL_PROJECTS` | Var | Optional | Default `"false"`. When enabled, `set_project`/`create_project` may auto‑add the requested project to the caller's ACL after backend validation. Prefer explicit `create_project` + `seed-acl.sh`. |
| `KV_PROJECTS` | Binding | ✅ Yes | KV namespace binding (configured in `wrangler.toml`) |

**How to set**:
- **Secrets**: `wrangler secret put <NAME>` or `./scripts/set-secrets.sh`
- **Vars**: Edit `wrangler.toml` in `vars` or `[env.<name>].vars` section
- **Bindings**: Edit `wrangler.toml` in `[[kv_namespaces]]` section

---

#### Backend (Render or equivalent)

| Variable | Required | Description |
|----------|----------|-------------|
| `INTERNAL_AUTH_SECRET` | ✅ Yes | Must match Worker secret exactly (no trailing whitespace!) |
| `BASE_THREADS_ROOT` | ✅ Yes | Root directory for thread storage (e.g., `/data/wc-cloud`) |
| `WATERCOOLER_GIT_REPO` | ⚠️ Optional | Git repository URL for sync (e.g., `git@github.com:org/watercooler-threads.git`) |
| `WATERCOOLER_DIR` | ⚠️ Optional | Git working tree root (must equal `BASE_THREADS_ROOT` if using Git) |
| `WATERCOOLER_GIT_AUTHOR` | ⚠️ Optional | Git commit author name (e.g., `"Watercooler Bot"`) |
| `WATERCOOLER_GIT_EMAIL` | ⚠️ Optional | Git commit email (e.g., `"bot@yourdomain.com"`) |
| `GIT_SSH_PRIVATE_KEY` | ⚠️ Optional | SSH private key PEM contents (for Git authentication) |
| `ALLOW_DEV_MODE` | ⚠️ Local Dev | Set to `"true"` for local development only (skips `INTERNAL_AUTH_SECRET` validation) |

**How to set**:
- **Render**: Dashboard → Environment → Add Environment Variable
- **Local**: `.env` file or `export VAR=value`

---

### KV Schema

#### Session Data

**Key**: `session:{uuid}`
**Value** (JSON):
```json
{
  "userId": "gh:<github-login>",
  "login": "<github-login>",
  "avatar": "<github-avatar-url>"
}
```
**TTL**: 24 hours (86400 seconds)
**Purpose**: Maps session cookies to user identity

**Example**:
```
Key: session:a1b2c3d4-e5f6-7890-abcd-ef1234567890
Value: {"userId":"gh:octocat","login":"octocat","avatar":"https://avatars.github.com/u/583231?v=4"}
Expiration: 2024-01-16T10:30:00Z
```

---

#### User ACL

**Key**: `user:gh:{github-login}`
**Value** (JSON):
```json
{
  "projects": ["project1", "project2", "project3"]
}
```
**TTL**: None (permanent until manually deleted)
**Purpose**: Default-deny authorization allowlist

**Example**:
```
Key: user:gh:octocat
Value: {"projects":["proj-alpha","proj-beta"]}
```

---

#### OAuth State

**Key**: `oauth:state:{state-uuid}`
**Value**: `"1"` (placeholder, only existence matters)
**TTL**: 10 minutes (600 seconds)
**Purpose**: CSRF protection for OAuth flow

**Example**:
```
Key: oauth:state:a1b2c3d4-e5f6-7890-abcd-ef1234567890
Value: "1"
Expiration: 2024-01-15T10:40:00Z
```

---

#### Rate Limit Counter

**Key**: `ratelimit:oauth:cb:{ip-address}`
**Value**: `"<count>"` (string integer)
**TTL**: 5 minutes (300 seconds)
**Purpose**: Token bucket rate limiting

**Example**:
```
Key: ratelimit:oauth:cb:203.0.113.42
Value: "7"
Expiration: 2024-01-15T10:35:00Z
```

---

### API Endpoints

#### Worker Endpoints

| Method | Endpoint | Purpose | Auth Required |
|--------|----------|---------|---------------|
| `GET` | `/auth/login` | Initiates GitHub OAuth flow | No |
| `GET` | `/auth/callback` | Handles OAuth redirect, creates session | No (validates OAuth state) |
| `GET` | `/sse` | Server-Sent Events transport for MCP | Yes (session cookie) |
| `POST` | `/messages` | JSON-RPC handler for MCP requests | Yes (session cookie) |
| `GET` | `/health` | Worker health check | No |

**SSE Endpoint Parameters**:
- `project` (required): Project name (must be in user's ACL)
- `session` (optional, staging only): `dev` for dev session bypass

**Example**:
```
GET /sse?project=proj-alpha HTTP/1.1
Host: watercooler-remote-mcp.your-org.workers.dev
Cookie: session=a1b2c3d4-...
Accept: text/event-stream
```

---

#### Backend Endpoints

| Method | Endpoint | Purpose | Auth Required |
|--------|----------|---------|---------------|
| `POST` | `/mcp/*` | Watercooler tool endpoints (proxied from Worker) | Yes (`X-Internal-Auth`) |
| `GET` | `/health` | Backend health check | No |
| `POST` | `/admin/sync` | Trigger Git sync | Yes (`X-Internal-Auth`) |

**Required Headers** (for `/mcp/*` endpoints):
- `X-Internal-Auth`: Shared secret (validates Worker)
- `X-User-Id`: User identity (e.g., `gh:octocat`)
- `X-Project-Id`: Project name (e.g., `proj-alpha`)
- `X-Agent-Name`: Agent name (e.g., `Claude`)

**Example**:
```bash
curl -X POST https://backend.onrender.com/mcp/watercooler_v1_health \
  -H "X-Internal-Auth: f4e7d2c1..." \
  -H "X-User-Id: gh:octocat" \
  -H "X-Project-Id: proj-alpha" \
  -H "X-Agent-Name: Claude"
```

---

### File Locations

#### Core Implementation

| Path | Description |
|------|-------------|
| `cloudflare-worker/src/index.ts` | Worker implementation (OAuth, ACL, MCP transport) |
| `src/watercooler_mcp/http_facade.py` | Backend HTTP facade (tool endpoints, auth middleware) |
| `src/watercooler_mcp/git_sync.py` | Git sync implementation (optional backup) |
| `src/watercooler_mcp/config.py` | Backend configuration and validation |

#### Helper Scripts

| Path | Description |
|------|-------------|
| `cloudflare-worker/scripts/deploy.sh` | Deploy Worker with pre-flight checks |
| `cloudflare-worker/scripts/set-secrets.sh` | Interactive secret configuration |
| `cloudflare-worker/scripts/seed-acl.sh` | Manage user ACL permissions |
| `cloudflare-worker/scripts/tail-logs.sh` | Stream logs with filters |
| `cloudflare-worker/scripts/test-security.sh` | Run security validation tests |
| `cloudflare-worker/scripts/README.md` | Comprehensive helper scripts documentation |

#### Configuration

| Path | Description |
|------|-------------|
| `cloudflare-worker/wrangler.toml` | Worker configuration (env vars, KV binding, secrets) |
| `cloudflare-worker/.dev.vars` | Local development secrets (git-ignored) |
| `.gitignore` | Excludes secrets and build artifacts |

#### Documentation

| Path | Description |
|------|-------------|
| `docs/DEPLOYMENT.md` | This deployment guide |
| `cloudflare-worker/scripts/README.md` | Helper scripts reference |
| `.watercooler/oauth-and-acl.md` | OAuth + ACL implementation thread |
| `.watercooler/cloudflare-remote-mcp-auth-proxy.md` | Previous implementation thread |

---

### External Resources

**GitHub OAuth App**:
- **Organization Settings**: `https://github.com/organizations/<your-org>/settings/applications`
- **OAuth Documentation**: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps

**Cloudflare**:
- **Workers Documentation**: https://developers.cloudflare.com/workers/
- **KV Documentation**: https://developers.cloudflare.com/kv/
- **Wrangler CLI**: https://developers.cloudflare.com/workers/wrangler/

**Render**:
- **Dashboard**: https://dashboard.render.com
- **Docs**: https://render.com/docs
- **Persistent Disks**: https://render.com/docs/disks

**OAuth 2.0 Standard**:
- **RFC 6749**: https://datatracker.ietf.org/doc/html/rfc6749
- **CSRF in OAuth**: https://datatracker.ietf.org/doc/html/rfc6749#section-10.12

**Server-Sent Events**:
- **MDN Documentation**: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- **Specification**: https://html.spec.whatwg.org/multipage/server-sent-events.html

---

## Appendix: Data Organization

### Per-User/Per-Project Directory Structure

Threads are organized in a hierarchical structure that provides clean isolation:

```
/data/wc-cloud/                           ← BASE_THREADS_ROOT (Backend env var)
├── gh:alice/                             ← User directory (GitHub user: alice)
│   ├── proj-alpha/                       ← Project directory
│   │   ├── feature-auth.md               ← Thread file (topic: feature-auth)
│   │   ├── bug-login-timeout.md          ← Thread file
│   │   └── .watercooler/                 ← Metadata directory
│   │       └── index.md                  ← Auto-generated index
│   └── proj-beta/                        ← Different project
│       ├── deployment-plan.md
│       └── .watercooler/
│           └── index.md
├── gh:bob/                               ← Different user
│   └── proj-alpha/                       ← Same project name, different user
│       ├── refactor-database.md          ← Bob's threads (isolated from Alice)
│       └── .watercooler/
│           └── index.md
└── .git/                                 ← Git repository (optional)
    └── ...                               ← Git sync backup
```

**Directory creation**:
- Directories created automatically on first thread write
- Pattern: `{BASE_THREADS_ROOT}/{user-id}/{project-id}/`
- User ID format: `gh:<github-login>` (e.g., `gh:octocat`)

**File naming**:
- Thread topic becomes filename: `{topic}.md`
- Example: Topic "feature-auth" → `feature-auth.md`
- Special characters sanitized (spaces → hyphens, etc.)

**Isolation guarantees**:
- Alice's `proj-alpha` and Bob's `proj-alpha` are separate directories
- ACL enforces: Alice can only access her own `gh:alice/*` paths
- Backend trusts Worker's `X-User-Id` header (validated via `X-Internal-Auth`)

---

### Git Sync (Optional)

When `WATERCOOLER_GIT_REPO` is configured:

**What gets synced**:
- All thread files (`*.md`)
- Watercooler metadata (`.watercooler/` directories)
- Directory structure (`gh:<user>/<project>/`)

**Sync trigger**:
- Automatic: After each thread write operation
- Manual: `POST /admin/sync` with `X-Internal-Auth` header

**Git operations**:
```bash
# On thread write:
1. git add <thread-file>
2. git commit -m "Update thread: <topic> by <user>"
3. git push origin main

# On startup (if repo configured):
1. Check if /data/wc-cloud/.git exists
2. If not: git clone $WATERCOOLER_GIT_REPO /data/wc-cloud
3. If yes: git pull origin main
```

**Benefits**:
- **Version history**: Git log shows all thread changes
- **Off-platform backup**: Thread data survives Render disk loss
- **Multi-instance sync**: Multiple backends can share thread storage (future)

**Trade-offs**:
- **Latency**: Git operations add ~100-500ms to write operations
- **Conflicts**: Concurrent writes from multiple backends could conflict (future concern)
- **Complexity**: Requires SSH key management, Git repo setup

---

## Conclusion

You now have a comprehensive understanding of Remote MCP deployment, from architecture to operations to security internals.

**Quick deployment recap**:
1. Prerequisites: GitHub OAuth app, Cloudflare KV, Render account
2. Configure secrets: `./scripts/set-secrets.sh`
3. Set Backend env vars (include `INTERNAL_AUTH_SECRET`)
4. Update `wrangler.toml` with Backend URL and KV IDs
5. Deploy to staging: `./scripts/deploy.sh staging`
6. Grant user access: `./scripts/seed-acl.sh <user> <project>`
7. Test OAuth flow and security: `./scripts/test-security.sh <url>`
8. Deploy to production: `./scripts/deploy.sh production`

**For ongoing operations**:
- Grant access: `./scripts/seed-acl.sh <user> <projects...>`
- Monitor logs: `./scripts/tail-logs.sh [auth|acl|error|security]`
- Health checks: `curl <worker-url>/health` and `curl <backend-url>/health`

**For troubleshooting**:
- Start with architectural layer (OAuth vs ACL vs Worker↔Backend)
- Use logs to identify specific failure point
- Consult "Understanding Through Troubleshooting" section

**Security best practices**:
- Never enable `ALLOW_DEV_SESSION` in production
- Rotate `INTERNAL_AUTH_SECRET` every 90 days
- Use different secrets for staging and production
- Monitor for repeated ACL denials (possible attack)
- Review ACLs regularly (grant minimum necessary access)

This system demonstrates defense-in-depth security: OAuth authentication, CSRF protection, session validation, rate limiting, default-deny ACLs, and service-to-service authentication all work together to create multiple independent security layers.

Happy deploying!
