# Watercooler Cloud - Quick Start Deployment Guide

One-page guide for deploying staging and production environments.

## Prerequisites

- Node.js and npm installed
- Cloudflare account with Workers access
- GitHub account for OAuth
- Git repository access (mostlyharmless-ai/watercooler-cloud)

## Overview

Watercooler Cloud uses a dual-stack architecture:
- **Staging**: `watercooler-cloud-staging` (testing and development)
- **Production**: `watercooler-cloud` (live service)

Each stack consists of:
- Cloudflare Worker (edge proxy with OAuth)
- Render backend (MCP server with git storage)

## Step 1: Clone and Install

```bash
git clone git@github.com:mostlyharmless-ai/watercooler-cloud.git
cd watercooler-cloud/cloudflare-worker
npm install
```

## Step 2: Configure Environments

The repo includes pre-configured environment files:
- `.env.staging` - Staging configuration
- `.env.production` - Production configuration

Both are already populated with correct values for:
- Backend URLs (Render services)
- Worker URLs (Cloudflare Workers)
- GitHub OAuth app credentials
- KV namespace IDs

**No manual configuration needed** - proceed to deployment.

## Step 3: Deploy Workers

### Deploy Staging
```bash
npx wrangler deploy --env staging
```

### Deploy Production
```bash
npx wrangler deploy
```

Expected output shows bindings for:
- Durable Objects (SESSION_MANAGER)
- KV Namespace (KV_PROJECTS)
- Environment Variables (BACKEND_URL, etc.)

## Step 4: Set Secrets (CRITICAL)

⚠️ **Known Issue**: Piping values to `wrangler secret put` fails - secrets upload but don't bind at runtime.

**Solution**: Use interactive CLI input (wrangler prompts for the secret value)

### For Staging:
```bash
cd cloudflare-worker

npx wrangler secret put GITHUB_CLIENT_ID --name watercooler-cloud-staging
# When prompted, paste: Ov23liApSu2EHry14NOU

npx wrangler secret put GITHUB_CLIENT_SECRET --name watercooler-cloud-staging
# When prompted, paste: 79d92d3825db8007a430810b0f5d9bc2e4c48f91

npx wrangler secret put INTERNAL_AUTH_SECRET --name watercooler-cloud-staging
# When prompted, paste: 14506b0c1b8d17e6637cf4d0a8cf4d99486592e612847451478609e06c17fe22
```

### For Production:
```bash
cd cloudflare-worker

npx wrangler secret put GITHUB_CLIENT_ID --name watercooler-cloud
# When prompted, paste: Ov23liribAJnjXimz8aD

npx wrangler secret put GITHUB_CLIENT_SECRET --name watercooler-cloud
# When prompted, paste: 0952cc397d191f22762d0e9680e781dbe6d0b497

npx wrangler secret put INTERNAL_AUTH_SECRET --name watercooler-cloud
# When prompted, paste: 49ed7413182bf7fb442c57aec4c887b76bbe521dc7271eb2455a9d32e6ffe599
```

**Note**: Values can also be found in `.env.staging` and `.env.production` files.

## Step 5: Verify Deployment

### Test Staging Health
```bash
curl https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev/health
```

Expected: `{"status":"ok","service":"watercooler-cloud-worker","backend":"..."}`

### Test Staging OAuth
```bash
curl -sI https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev/auth/login | grep location
```

Expected: GitHub OAuth URL with populated `client_id=Ov23liApSu2EHry14NOU`

**If you see `client_id=` (empty)**: Secrets aren't binding - verify Step 4

**If you get HTTP 503**: Secrets missing - complete Step 4

### Test Production
```bash
curl https://watercooler-cloud.mostlyharmless-ai.workers.dev/health
curl -sI https://watercooler-cloud.mostlyharmless-ai.workers.dev/auth/login | grep location
```

## Step 6: Seed User ACLs

Add your GitHub username to both environments:

```bash
# Staging
npx wrangler kv key put "user:gh:YOUR_GITHUB_USERNAME" '{"user_id":"YOUR_GITHUB_USERNAME","default":"watercooler-cloud","projects":["watercooler-cloud"]}' --namespace-id=b9b8b18bba6943878c892c4108371dc2 --remote

# Production
npx wrangler kv key put "user:gh:YOUR_GITHUB_USERNAME" '{"user_id":"YOUR_GITHUB_USERNAME","default":"watercooler-cloud","projects":["watercooler-cloud"]}' --namespace-id=2f2d304b3d8c4522830a9460098b5559 --remote
```

## Step 7: Configure MCP in Claude Code and Codex

The `get-token.sh` script automatically configures both Claude CLI and Codex CLI with the MCP server:

```bash
# Configure staging at user level (all projects)
./scripts/get-token.sh staging user

# Configure production at user level (all projects)
./scripts/get-token.sh production user

# Or configure at project level (this project only - Claude only, Codex uses global)
./scripts/get-token.sh staging project
./scripts/get-token.sh production project
```

**Script workflow:**
1. Opens `/console` page in browser (auto-redirects to OAuth login if needed)
2. You click "Create Token" in the web UI
3. Copy the displayed Bearer token (30-day default expiry)
4. Paste token into script prompt
5. Script automatically removes existing MCP configs if present (both Claude and Codex)
6. Script configures MCP servers using stdio transport (matches production format)
7. Restart your IDE(s) to load the new servers

**Features:**
- Automatically detects and configures both Claude and Codex CLI (if installed)
- Uses `claude mcp add --transport stdio` and `codex mcp add` commands
- Creates consistent stdio format with `npx mcp-remote` wrapper
- No manual JSON/TOML editing required

**Manual console access:**
- Staging: https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev/console
- Production: https://watercooler-cloud.mostlyharmless-ai.workers.dev/console

**Configuration scopes:**
- `user`: Saves to `~/.claude.json` (all projects) and `~/.codex/config.toml` (global)
- `project`: Saves to `./.claude.json` (this project only); Codex always uses global config

**Configuration locations:**
- Claude: `~/.claude.json` (user) or `./.claude.json` (project)
- Codex: `~/.codex/config.toml` (always global)

## Complete Test Flow

1. Visit staging OAuth: https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev/auth/login
2. Authorize with GitHub
3. Should redirect back with session cookie
4. Test MCP endpoint (requires MCP client configuration)

## Troubleshooting

### Secrets Not Binding (503 Error)
**Symptom**: `curl /auth/login` returns HTTP 503 with `{"error":"missing_secrets",...}`

**Solution**: Use interactive CLI method (Step 4). Do NOT pipe values - let wrangler prompt you for input.

### OAuth Redirect Has Empty client_id
**Symptom**: GitHub OAuth URL shows `client_id=` (empty parameter)

**Solution**: Same as above - use interactive CLI method (not piping)

### Health Endpoint Returns 404
**Symptom**: `/health` returns 404

**Solution**: Worker not deployed - run `npx wrangler deploy --env staging`

### Wrong Service Name in Health Response
**Symptom**: Health returns `"service":"mharmless-remote-mcp"`

**Solution**: You're hitting old service, check your URLs

## Architecture Notes

### Dual-Stack Design
- Staging and production are completely isolated
- Each has separate: GitHub OAuth app, KV namespace, backend server, secrets
- Safe to test in staging without affecting production

### Security Model
- OAuth via GitHub for authentication
- Per-user project ACLs stored in KV
- Internal auth secret for worker-to-backend communication
- All secrets encrypted at rest by Cloudflare

### URLs Reference
```
Staging:
  Worker: https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev
  Backend: https://watercooler-cloud-staging.onrender.com
  Threads: https://github.com/mostlyharmless-ai/watercooler-cloud-threads-staging

Production:
  Worker: https://watercooler-cloud.mostlyharmless-ai.workers.dev
  Backend: https://watercooler-cloud.onrender.com
  Threads: https://github.com/mostlyharmless-ai/watercooler-cloud-threads
```

## Support

- Issues: https://github.com/mostlyharmless-ai/watercooler-cloud/issues
- Watercooler threads: Use `watercooler_v1_say` tool in Claude Code
