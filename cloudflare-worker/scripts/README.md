# Cloudflare Worker Operations Scripts

Helper scripts for deploying and managing the Remote MCP Worker with OAuth + ACL security.

## Architecture Overview

```
┌─────────────────┐
│   MCP Client    │ (Claude Desktop, etc.)
└────────┬────────┘
         │ SSE connection
         ▼
┌─────────────────────────────────────────────────┐
│          Cloudflare Worker (Edge)               │
│  ┌──────────────────────────────────────────┐  │
│  │  /auth/login    → OAuth initiation       │  │
│  │  /auth/callback → GitHub OAuth, session  │  │
│  │  /sse           → MCP transport (SSE)    │  │
│  │  /messages      → JSON-RPC handler       │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  Security:                                      │
│  • CSRF protection (state parameter)           │
│  • Session cookies (HttpOnly, Secure)          │
│  • Rate limiting (KV token bucket)             │
│  • ACL enforcement (default-deny)              │
│                                                 │
│  Storage (KV):                                  │
│  • session:{uuid} → {userId, login, avatar}    │
│  • user:gh:{login} → {projects: [...]}         │
│  • oauth:state:{state} → "1" (10min TTL)       │
│  • ratelimit:oauth:cb:{ip} → count (5min TTL)  │
└─────────────────┬───────────────────────────────┘
                  │ X-User-Id, X-Project-Id,
                  │ X-Agent-Name, X-Internal-Auth
                  ▼
┌─────────────────────────────────────────────────┐
│       FastAPI Backend (Render)                  │
│  ┌──────────────────────────────────────────┐  │
│  │  /mcp/* → Watercooler tool endpoints     │  │
│  │  /health → Health check                  │  │
│  │  /admin/sync → Git sync trigger          │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  Security:                                      │
│  • Validates X-Internal-Auth header            │
│  • Trusts Worker identity headers              │
│  • Fail-fast if secret missing in production   │
│                                                 │
│  Storage:                                       │
│  • Per-user/project thread directories         │
│  • Optional Git sync to watercooler-threads    │
└─────────────────────────────────────────────────┘
```

## Environment Variables

### Worker (Cloudflare)

| Variable | Required | Description | How to Set |
|----------|----------|-------------|------------|
| `GITHUB_CLIENT_ID` | ✅ Yes | GitHub OAuth app client ID | `wrangler secret put GITHUB_CLIENT_ID` |
| `GITHUB_CLIENT_SECRET` | ✅ Yes | GitHub OAuth app secret | `wrangler secret put GITHUB_CLIENT_SECRET` |
| `INTERNAL_AUTH_SECRET` | ✅ Yes | Shared secret for Worker↔Backend auth (32+ random chars) | `wrangler secret put INTERNAL_AUTH_SECRET` |
| `BACKEND_URL` | ✅ Yes | FastAPI backend URL (e.g. `https://watercooler.onrender.com`) | Set in `wrangler.toml` |
| `DEFAULT_AGENT` | ✅ Yes | Default agent name (e.g. "Claude") | Set in `wrangler.toml` |
| `ALLOW_DEV_SESSION` | ⚠️ Staging | Set to `"true"` to allow `?session=dev` (NEVER in production) | Set in `wrangler.toml` per environment |
| `KV_PROJECTS` | ✅ Yes | KV namespace binding | Bind in `wrangler.toml` |

### Backend (Render)

| Variable | Required | Description |
|----------|----------|-------------|
| `INTERNAL_AUTH_SECRET` | ✅ Yes | Must match Worker secret exactly |
| `BASE_THREADS_ROOT` | ✅ Yes | Root directory for thread storage (e.g. `/data/threads`) |
| `WATERCOOLER_GIT_REPO` | ⚠️ Optional | Git repository URL for sync (e.g. `https://github.com/org/watercooler-threads`) |
| `ALLOW_DEV_MODE` | ⚠️ Dev | Set to `"true"` for local development (omit on Render) |

## Security Model

### Authentication Flow

1. **User visits `/auth/login`**
   - Worker generates cryptographic `state` parameter
   - Stores state in KV with 10-minute TTL
   - Sets `oauth_state` cookie (HttpOnly, Secure)
   - Redirects to GitHub OAuth

2. **GitHub redirects to `/auth/callback?code=...&state=...`**
   - Worker validates state (must exist in KV AND match cookie)
   - Deletes state from KV (one-time use)
   - Exchanges code for GitHub access token
   - Fetches user info from GitHub API
   - Creates session: `session:{uuid}` → `{userId: "gh:login", login, avatar}`
   - Sets `session` cookie (HttpOnly, Secure, 24h)

3. **Client connects to `/sse?project=proj-name`**
   - Worker reads session from cookie (NOT query params)
   - Looks up ACL: `user:gh:{login}`
   - Validates project is in user's allowed list (default-deny)
   - Proxies to backend with identity headers

### ACL (Access Control Lists)

**Default-Deny Security Model**: Users must have an explicit ACL entry to access ANY project.

**KV Schema**:
```json
// Key: user:gh:octocat
{
  "projects": ["proj-alpha", "proj-beta"]
}
```

**Enforcement**:
- No ACL entry → 403 Forbidden
- Project not in list → 403 Forbidden
- Project in list → Stream allowed

### Rate Limiting

**OAuth Callback Protection**: 10 attempts per 5 minutes per IP address

**Mechanism**: KV token bucket
- Key: `ratelimit:oauth:cb:{ip}`
- Counter increments on each attempt
- Resets after 5 minutes
- Returns 429 with `Retry-After: 300` when exceeded

### Dev Session (Staging Only)

**Production**: Dev session DISABLED (users must authenticate via OAuth)

**Staging**: Dev session ENABLED via `ALLOW_DEV_SESSION=true`
- Allows `?session=dev` for testing
- Logs warning on each use
- Should NEVER be enabled in production

## Available Scripts

### `deploy.sh`
Deploy the Worker to Cloudflare with pre-flight checks.

```bash
./scripts/deploy.sh [staging|production]
```

**Checks**:
- Required secrets are set
- KV namespace is bound
- Environment-specific configuration is correct

### `set-secrets.sh`
Interactive script to configure Worker secrets.

```bash
./scripts/set-secrets.sh
```

**Sets**:
- `GITHUB_CLIENT_ID` (from GitHub OAuth app)
- `GITHUB_CLIENT_SECRET` (from GitHub OAuth app)
- `INTERNAL_AUTH_SECRET` (generates secure random value)

### `seed-acl.sh`
Seed KV with user ACL data.

```bash
./scripts/seed-acl.sh <github-login> <project1> [project2] [project3] ...
```

**Example**:
```bash
./scripts/seed-acl.sh octocat proj-alpha proj-beta
```

### `test-security.sh`
Run security validation tests against deployed Worker.

```bash
./scripts/test-security.sh [worker-url]
```

**Tests**:
- CSRF protection (C1)
- Session fixation prevention (C2)
- Rate limiting (C3)
- ACL enforcement (H2)

### `tail-logs.sh`
Stream Worker logs with helpful filters.

```bash
./scripts/tail-logs.sh [filter]
```

**Filters**:
- `auth` - Authentication events
- `acl` - ACL decisions
- `error` - Errors and failures
- `all` - Everything (default)

## GitHub OAuth App Setup

1. **View/Edit OAuth App**: https://github.com/organizations/mostlyharmless-ai/settings/applications

2. **Current Settings**:
   - **Application name**: "Watercooler Remote MCP"
   - **Homepage URL**: `https://mharmless-remote-mcp.mostlyharmless-ai.workers.dev/`
   - **Authorization callback URL**: `https://mharmless-remote-mcp.mostlyharmless-ai.workers.dev/auth/callback`
   - **Application description**: "Watercooler Remote MCP (staging or prod)"

3. **Scopes**: `read:user` (minimal)

4. **Copy**:
   - Client ID → Use in `./scripts/set-secrets.sh`
   - Client Secret → Use in `./scripts/set-secrets.sh`

**Note**: This is an organization-level OAuth app under `mostlyharmless-ai`.

## KV Namespace Setup

1. **Create KV namespace**:
   ```bash
   wrangler kv:namespace create "KV_PROJECTS"
   wrangler kv:namespace create "KV_PROJECTS" --preview
   ```

2. **Copy namespace IDs** to `wrangler.toml`:
   ```toml
   [[kv_namespaces]]
   binding = "KV_PROJECTS"
   id = "your_namespace_id_here"
   preview_id = "your_preview_namespace_id_here"
   ```

## Common Operations

### Deploy to Staging
```bash
./scripts/deploy.sh staging
```

### Deploy to Production
```bash
./scripts/deploy.sh production
```

### Add User Access
```bash
./scripts/seed-acl.sh octocat proj-alpha proj-beta
```

### View Logs
```bash
./scripts/tail-logs.sh auth
```

### Test Security
```bash
./scripts/test-security.sh https://mharmless-remote-mcp-staging.mostlyharmless-ai.workers.dev
```

## Troubleshooting

### "OAuth error: Unexpected token 'R'"
GitHub returned non-JSON response. Check:
- `redirect_uri` matches OAuth app exactly
- Secrets are set: `wrangler secret list`
- Client ID/Secret are valid

### "Access denied - No project permissions"
User has no ACL entry. Fix:
```bash
./scripts/seed-acl.sh <github-login> <project-name>
```

### "Unauthorized - Dev session not allowed"
`ALLOW_DEV_SESSION` not enabled. Either:
- Enable in staging: Set in `wrangler.toml` for staging env
- Use OAuth: Visit `/auth/login` to authenticate

### Rate limit exceeded
Too many OAuth attempts. Wait 5 minutes or:
```bash
# Clear rate limit for specific IP (requires wrangler KV access)
wrangler kv:key delete "ratelimit:oauth:cb:1.2.3.4" --binding=KV_PROJECTS
```

## Security Best Practices

1. **Never commit secrets** to version control
2. **Rotate `INTERNAL_AUTH_SECRET`** every 90 days
3. **Use different secrets** for staging and production
4. **Monitor logs** for suspicious activity (`wrangler tail`)
5. **Keep ACLs minimal** - only grant necessary project access
6. **Disable `ALLOW_DEV_SESSION`** in production
7. **Review KV data regularly** for stale sessions

## References

- **Worker Code**: `../src/index.ts`
- **Backend Code**: `../../src/watercooler_mcp/http_facade.py`
- **Watercooler Thread**: `../../.watercooler/oauth-and-acl.md`
- **Cloudflare Docs**: https://developers.cloudflare.com/workers/
- **GitHub OAuth**: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps
