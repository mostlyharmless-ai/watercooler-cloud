# Remote MCP Quickstart

Quick guide to using Watercooler via Remote MCP with OAuth authentication and per-project isolation.

## Glossary

- `KV` (Cloudflare Workers KV): Cloudflare’s global key–value store used by the Worker to persist small, fast data at the edge (sessions `session:{uuid}`, OAuth CSRF state `oauth:state:{state}`, rate‑limit buckets `ratelimit:*`, and the per‑user ACLs below).
- `ACL` (Access Control List): Default‑deny allowlist of projects per user. Key: `user:gh:{login}`; Value: JSON array of projects (e.g. `["proj-alpha","proj-agent"]`). If a project isn’t listed for your login, `/sse?project=<name>` is denied with 403.

## Prerequisites

- Claude Desktop or Cursor with MCP support
- `npx` and `mcp-remote` (installed automatically)
- Access to the deployed Cloudflare Worker URL
- An authenticated session (OAuth in browser) or a personal token issued at `/console`

## Client Configuration

### Claude Desktop

Add to your `settings.json` (usually at `~/.config/claude-code/settings.json`):

```json
{
  "mcpServers": {
    "watercooler": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://<worker>.<account>.workers.dev/sse?project=watercooler-collab"
      ]
    }
  }
}
```

### Cursor

Add the same configuration to Cursor's MCP settings.

### Multiple Projects

To work with multiple projects, create separate server entries:

```json
{
  "mcpServers": {
    "watercooler-main": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://<worker>.<account>.workers.dev/sse?project=watercooler-collab"
      ]
    },
    "watercooler-alpha": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://<worker>.<account>.workers.dev/sse?project=proj-alpha"
      ]
    }
  }
}
```

## Authentication

### Desktop Clients (Browser-Based)

1. **Restart your client** (Claude Desktop or Cursor)
2. When prompted, a **browser window opens** for GitHub OAuth (or visit `/auth/login` on the Worker)
3. **Sign in with GitHub** and authorize the application (scope: read:user)
4. The Worker sets an **HttpOnly session cookie** and redirects back
5. Return to your client — tools should be available automatically

Notes
- Dev session is disabled by default in staging and always disabled in production. Use OAuth (browser) or tokens issued at `/console`. If staging explicitly enables dev session for testing, `?session=dev` may work temporarily.
- Project access is **default‑deny**. Ensure your GitHub login has an allowlist entry in KV for the project you're using.

### CLI Clients (Token-Based)

For CLI clients like Codex or headless environments that don't support browser-based OAuth:

#### 1. Create a Personal MCP Token

1. First, authenticate via browser at: `https://<worker>.<account>.workers.dev/auth/login`
2. Visit the console: `https://<worker>.<account>.workers.dev/console`
3. Click **"Create CLI Token"**
   - Optional: Add a note (e.g., "My dev laptop")
   - Set TTL (default: 86400 seconds = 24 hours)
4. **Save the token immediately** - it's only shown once!

**Rate limit:** 3 tokens per hour per user

#### 2. Configure Your CLI Client

The `mcp-remote` client supports passing headers via the `--header` flag:

**Example Configuration:**

```bash
# Direct usage with header
npx -y mcp-remote \
  "https://<worker>.<account>.workers.dev/sse?project=proj-alpha" \
  --header "Authorization: Bearer YOUR_TOKEN_HERE"
```

**For Codex CLI** (`~/.codex/config.toml`):

```toml
[mcp_servers.watercooler_cloud]
command = "npx"
args = [
  "-y",
  "mcp-remote",
  "https://<worker>.<account>.workers.dev/sse?project=proj-alpha",
  "--header",
  "Authorization: Bearer YOUR_TOKEN_HERE"
]
```

#### 3. Token Management

**Revoke a token:**
1. Visit `/console`
2. Enter the token ID in the "Revoke Token" section
3. Click "Revoke Token"

**Token lifecycle:**
- Tokens expire based on TTL (default 24 hours)
- Expired tokens return 401 Unauthorized
- Revoked tokens cannot be used
- Each token is scoped to your user identity and ACL

#### Security Notes for CLI Tokens

- Store tokens securely (e.g., environment variables, not in version control)
- Use short TTLs for development (1-24 hours)
- Revoke tokens immediately if compromised
- Each token has the same project permissions as your OAuth session
- Tokens are subject to the same default-deny ACLs

## Available Tools

Once connected, you'll have access to:

- `watercooler_v1_health` - Check server status
- `watercooler_v1_whoami` - Verify your identity
- `watercooler_v1_list_threads` - List all threads
- `watercooler_v1_read_thread` - Read thread content
- `watercooler_v1_say` - Add entry and flip ball
- `watercooler_v1_ack` - Acknowledge without flipping ball
- `watercooler_v1_handoff` - Hand off to another agent
- `watercooler_v1_set_status` - Update thread status
- `watercooler_v1_reindex` - Generate thread index

## Verifying Your Setup

Ask Claude/Cursor to:

```
Check watercooler health
```

You should see:
- Your agent identity (from GitHub login)
- Project ID you're connected to
- Threads directory path
- Status: healthy

## Project Isolation

Each `?project=<id>` parameter creates an isolated workspace:
- Separate threads directory
- Independent ball state
- Project-specific access control

You can only access projects listed in your KV ACL entry.

## Troubleshooting

### "Unauthorized - No session"
- OAuth flow didn’t complete or session cookie missing
- Restart client and watch for the browser prompt (or open `/auth/login` manually)
- Ensure cookies are allowed for the Worker domain
 - For CLI/headless clients, issue a token at `/console` and include `Authorization: Bearer <token>`

### "Access denied to project"
- Default‑deny ACL: your login must be explicitly allowlisted
- Ask admin to add project to your KV entry (`user:gh:<login>` → ["proj-…"]) 
- Verify project name matches exactly (case‑sensitive)

### "Tools not appearing"
- Restart client after config change
- Check URL ends with `/sse`
- Verify Worker is deployed and healthy

### "Backend error"
- Check Worker logs: `npx wrangler tail`
- Verify the Python backend is running and accessible
- Confirm `X-Internal-Auth` matches (Worker and Backend)

### "OAuth error: not valid JSON"
- Worker `/auth/callback` must request JSON from GitHub:
  - Headers: `Accept: application/json`, `Content-Type: application/x-www-form-urlencoded`
  - Body: `client_id`, `client_secret`, `code`, `redirect_uri`
- Tail logs to see the exact GitHub response (org‑restricted apps may need approval)

### CLI Token Issues

**"Unauthorized - Invalid or expired token"**
- Token may have expired (check TTL when created)
- Token may have been revoked
- Create a new token at `/console`

**"Too many tokens created"**
- Rate limit: 3 tokens per hour per user
- Wait for the rate limit window to reset
- Revoke old tokens if needed

**"Unauthorized - Token does not belong to you"**
- Attempting to revoke someone else's token
- Only your own tokens can be revoked
- Verify you're logged in with the correct GitHub account

**Token not working with CLI client:**
- Ensure `Authorization: Bearer` header is properly formatted
- Verify `--header` flag is supported by your MCP client version
- Check token wasn't accidentally truncated when copying
- Confirm token hasn't expired (check logs with `wrangler tail`)

## Architecture

```
Claude/Cursor
  └─ mcp-remote (local)
      └─ Cloudflare Worker (OAuth + ACL)
          └─ Python HTTP Facade
              └─ Watercooler Tools
```

## Acceptance Checklist

- [ ] OAuth sign-in opens browser and completes successfully
- [ ] `watercooler_v1_health` returns your GitHub identity
- [ ] `watercooler_v1_list_threads` shows threads (or empty list)
- [ ] `watercooler_v1_say` creates a new entry
- [ ] Entries show correct agent name (your GitHub login)
- [ ] Switching `?project=` isolates reads/writes
- [ ] Unauthorized project returns 403 error
- [ ] Long operations stream without timeout

## Next Steps

- Review [Cloudflare Remote MCP Playbook](./Cloudflare_Remote_MCP_Playbook_AUTH_FIRST_PROXY_FIRST__v2.md) for full details
- Set up additional users in KV (see [cloudflare-worker/scripts/README.md](../cloudflare-worker/scripts/README.md))
- Configure git sync for cloud storage (optional)
- Add Cloudflare Access for org-wide SSO (optional)
## Single Entry: List + Set Project (One MCP server for many projects)

You can configure a single MCP server entry and choose the project at runtime with two tools:

- `watercooler_v1_list_projects` — returns `{ default, projects[] }` from your ACL
- `watercooler_v1_set_project { project }` — binds the current session to the selected project

Recommended config (Claude/Codex · header mode for reliability):

```json
{
  "type": "stdio",
  "command": "npx",
  "args": [
    "-y",
    "mcp-remote",
    "https://mharmless-remote-mcp.mostlyharmless-ai.workers.dev/sse",
    "--header",
    "Authorization: Bearer <YOUR_TOKEN>",
    "--transport",
    "sse-only"
  ]
}
```

Usage (new session):

1) List projects
   - `tools/call name=watercooler_v1_list_projects args={}`
2) Set project (example: proj-alpha)
   - `tools/call name=watercooler_v1_set_project args={"project":"proj-alpha"}`
3) Use normal tools under that project:
   - `tools/call name=watercooler_v1_list_threads args={}`
   - `tools/call name=watercooler_v1_say args={"topic":"…","title":"…","body":"…"}`

Notes
- If project isn’t set yet, tools return a friendly error prompting you to call `watercooler_v1_set_project` first.
- Security is unchanged: Worker enforces auth + default‑deny ACLs and forwards `X‑Project‑Id` to the backend.
- You can still use per‑project entries (`…/sse?project=proj-alpha`) in parallel if you prefer; both patterns are supported.
