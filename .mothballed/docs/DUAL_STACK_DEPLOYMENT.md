# [ARCHIVED] Watercooler Cloud - Dual Stack Deployment Guide (Mothballed)

> This guide pertains to the remote Cloudflare/Render stack. It is archived.
> Preferred path: local stdio MCP (universal dev mode). See docs/TESTER_SETUP.md.

**Version:** 1.0
**Date:** 2025-10-25
**Architecture:** Complete Staging/Production Isolation

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Resource Naming Scheme](#resource-naming-scheme)
3. [Prerequisites](#prerequisites)
4. [Deployment Process](#deployment-process)
5. [Staging Stack Deployment](#staging-stack-deployment)
6. [Production Stack Deployment](#production-stack-deployment)
7. [Verification & Testing](#verification--testing)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### Design Philosophy

**Complete isolation between staging and production:**
- Separate Render backends (different code branches, different deploys)
- Separate threads repositories (isolated data)
- Separate Cloudflare Workers (separate OAuth apps, KV namespaces)
- Independent secrets for each environment

**Benefits:**
- Test code changes in staging without affecting production
- Test deployment process safely
- Experiment with configuration changes
- Full data isolation

### Data Flow

```
User → Cloudflare Worker → Render Backend → GitHub Threads Repo
       (Edge Proxy)          (FastAPI)        (Git Storage)
```

**Staging Stack:**
```
Claude CLI/Codex CLI
    ↓
watercooler-cloud-staging.mostlyharmless-ai.workers.dev
    ↓ (OAuth + INTERNAL_AUTH_SECRET)
watercooler-cloud-staging.onrender.com
    ↓ (SSH Deploy Key)
git@github.com:mostlyharmless-ai/watercooler-cloud-threads-staging.git
```

**Production Stack:**
```
Claude CLI/Codex CLI
    ↓
watercooler-cloud.mostlyharmless-ai.workers.dev
    ↓ (OAuth + INTERNAL_AUTH_SECRET)
watercooler-cloud.onrender.com
    ↓ (SSH Deploy Key)
git@github.com:mostlyharmless-ai/watercooler-cloud-threads.git
```

---

## Resource Naming Scheme

### Staging Stack

| Resource Type | Name | URL/Identifier |
|---------------|------|----------------|
| **Render Backend** | `watercooler-cloud-staging` | `https://watercooler-cloud-staging.onrender.com` |
| **Threads Repo** | `watercooler-cloud-threads-staging` | `git@github.com:mostlyharmless-ai/watercooler-cloud-threads-staging.git` |
| **Cloudflare Worker** | `watercooler-cloud-staging` | `https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev` |
| **GitHub OAuth App** | `Watercooler Cloud Staging` | - |
| **Cloudflare KV Namespace** | `KV_PROJECTS` (staging env) | Unique namespace ID |
| **Deploy Key** | `Watercooler Staging Backend` | SSH ed25519 key pair |

### Production Stack

| Resource Type | Name | URL/Identifier |
|---------------|------|----------------|
| **Render Backend** | `watercooler-cloud` | `https://watercooler-cloud.onrender.com` |
| **Threads Repo** | `watercooler-cloud-threads` | `git@github.com:mostlyharmless-ai/watercooler-cloud-threads.git` |
| **Cloudflare Worker** | `watercooler-cloud` | `https://watercooler-cloud.mostlyharmless-ai.workers.dev` |
| **GitHub OAuth App** | `Watercooler Cloud` | - |
| **Cloudflare KV Namespace** | `KV_PROJECTS` (production env) | Unique namespace ID |
| **Deploy Key** | `Watercooler Production Backend` | SSH ed25519 key pair |

---

## Prerequisites

### Required Accounts & Access

- **GitHub:** Admin access to `mostlyharmless-ai` organization
- **Cloudflare:** Account with Workers enabled, `wrangler` CLI authenticated
- **Render:** Account with ability to create web services

### Required Tools

```bash
# Check installations
openssl version       # For secret generation
ssh-keygen           # For deploy keys
git --version        # For repository operations
npx --version        # For wrangler CLI
```

### Cloudflare Authentication

```bash
npx wrangler login
npx wrangler whoami  # Verify authentication
```

### GitHub SSH Authentication

```bash
ssh -T git@github.com
# Should see: "Hi mostlyharmless-ai! You've successfully authenticated"
```

---

## Deployment Process

### Overview

Each stack (staging and production) requires the following steps:

1. **Generate Secrets** - INTERNAL_AUTH_SECRET, SSH deploy key
2. **Create Threads Repository** - Private GitHub repo for thread storage
3. **Add Deploy Key** - SSH key for backend→repo authentication
4. **Create OAuth App** - GitHub OAuth for user authentication
5. **Create Render Backend** - FastAPI service with persistent disk
6. **Create KV Namespace** - Cloudflare KV for ACLs
7. **Configure Worker** - Update wrangler.toml and set secrets
8. **Deploy Worker** - Deploy to Cloudflare
9. **Seed ACLs** - Add initial user permissions
10. **Verify Stack** - Test OAuth, MCP, git sync

We'll deploy **staging first**, verify it works, then deploy production.

---

## Staging Stack Deployment

### Step 1: Generate Staging Secrets

```bash
cd /path/to/watercooler-cloud

# Generate INTERNAL_AUTH_SECRET
STAGING_INTERNAL_AUTH_SECRET=$(openssl rand -hex 32)
echo "STAGING_INTERNAL_AUTH_SECRET=${STAGING_INTERNAL_AUTH_SECRET}"

# Generate SSH deploy key
mkdir -p .secrets
ssh-keygen -t ed25519 -C "watercooler-staging" -f .secrets/staging_deploy_key -N ""

# Display public key (for GitHub)
cat .secrets/staging_deploy_key.pub

# Save to config file
cat > .env.staging << EOF
# Watercooler Staging Configuration
# Generated: $(date +%Y-%m-%d)

ENVIRONMENT=staging
INTERNAL_AUTH_SECRET=${STAGING_INTERNAL_AUTH_SECRET}
SSH_PRIVATE_KEY_PATH=.secrets/staging_deploy_key
THREADS_REPO=git@github.com:mostlyharmless-ai/watercooler-cloud-threads-staging.git
BACKEND_URL=https://watercooler-cloud-staging.onrender.com
WORKER_URL=https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev
EOF

echo "✅ Secrets generated and saved to .env.staging"
```

**Save these values - you'll need them later!**

### Step 2: Create Staging Threads Repository

**Manual Step:** Go to https://github.com/organizations/mostlyharmless-ai/repositories/new

```
Repository name: watercooler-cloud-threads-staging
Description: Watercooler staging environment thread storage
Visibility: ✅ Private
Initialize: ❌ DO NOT check any boxes (create empty repo)
```

Click **"Create repository"**

### Step 3: Add SSH Deploy Key to Staging Repo

**Manual Step:** Go to https://github.com/mostlyharmless-ai/watercooler-cloud-threads-staging/settings/keys

Click **"Add deploy key"**:

```
Title: Watercooler Staging Backend
Key: <paste contents of .secrets/staging_deploy_key.pub>
✅ CHECK "Allow write access" (CRITICAL!)
```

Click **"Add key"**

### Step 3a: Initialize Main Branch in Threads Repository

**CRITICAL:** GitHub repos created empty (no README/license) have no branches. The Render start command expects a cloneable repo with at least one branch.

**Manual Step:** Initialize the main branch locally:

```bash
cd /tmp
git clone git@github.com:mostlyharmless-ai/watercooler-cloud-threads-staging.git
cd watercooler-cloud-threads-staging
git config user.name "Your Name"
git config user.email "your.email@example.com"
git commit --allow-empty -m "Initialize staging threads repo"
git push -u origin main
```

⚠️ **Why this is needed:** Without this step, the Render service will fail to clone because the repository has no refs/branches. The start command can handle empty repos with a main branch, but not repos with zero branches.

### Step 4: Create Staging OAuth App

**Manual Step:** Go to https://github.com/organizations/mostlyharmless-ai/settings/applications

Click **"New OAuth App"**:

```
Application name: Watercooler Cloud Staging
Homepage URL: https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev
Authorization callback URL: https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev/auth/callback
```

⚠️ **NO trailing slash on callback URL!**

After creating, copy:
- **Client ID** → Save as `STAGING_GITHUB_CLIENT_ID`
- **Client Secret** → Save as `STAGING_GITHUB_CLIENT_SECRET`

```bash
# Add to config file
echo "GITHUB_CLIENT_ID=<paste-client-id>" >> .env.staging
echo "GITHUB_CLIENT_SECRET=<paste-client-secret>" >> .env.staging
```

### Step 5: Create Staging Render Backend

**Automated via Render MCP:**

```bash
# Note: This will be done via tool call - see below
```

**Configuration:**
- **Name:** `watercooler-cloud-staging`
- **Repo:** `https://github.com/mostlyharmless-ai/watercooler-cloud`
- **Branch:** `main`
- **Region:** `oregon`
- **Plan:** `starter`
- **Runtime:** `python`
- **Build Command:** `pip install -U pip setuptools wheel && pip install '.[http]'`
- **Start Command:**
  ```bash
  mkdir -p /data/secrets && \
  printf '%s' "$GIT_SSH_PRIVATE_KEY" > /data/secrets/wc_git_key && \
  chmod 600 /data/secrets/wc_git_key && \
  export GIT_SSH_COMMAND="ssh -i /data/secrets/wc_git_key -o StrictHostKeyChecking=no -o IdentitiesOnly=yes" && \
  export WATERCOOLER_DIR=/data/wc-staging BASE_THREADS_ROOT=/data/wc-staging && \
  if [ -n "$WATERCOOLER_GIT_REPO" ] && [ ! -d /data/wc-staging/.git ]; then \
    git clone "$WATERCOOLER_GIT_REPO" /data/wc-staging && \
    cd /data/wc-staging && \
    git config user.name "Watercooler Bot" && \
    git config user.email "bot@mostlyharmless.ai" && \
    git commit --allow-empty -m "Initialize staging threads repo" && \
    git push -u origin HEAD || true; \
  fi && \
  uvicorn src.watercooler_mcp.http_facade:app --host 0.0.0.0 --port "$PORT"
  ```

**Environment Variables (set in Render dashboard after creation):**
```bash
INTERNAL_AUTH_SECRET=<value from .env.staging>
WATERCOOLER_GIT_REPO=git@github.com:mostlyharmless-ai/watercooler-cloud-threads-staging.git
WATERCOOLER_DIR=/data/wc-staging
BASE_THREADS_ROOT=/data/wc-staging
GIT_SSH_PRIVATE_KEY=<entire contents of .secrets/staging_deploy_key>
```

**Persistent Disk (add in Render dashboard):**
- **Name:** `staging-data`
- **Mount Path:** `/data`
- **Size:** `1 GB`

### Step 6: Create Staging KV Namespace

```bash
cd cloudflare-worker

# Create KV namespace for staging
npx wrangler kv:namespace create "KV_PROJECTS" --env staging

# Output will show:
# [[kv_namespaces]]
# binding = "KV_PROJECTS"
# id = "<NAMESPACE_ID>"

# Save the namespace ID
echo "KV_NAMESPACE_ID_STAGING=<paste-id>" >> ../.env.staging
```

### Step 7: Configure Staging Worker

**Update cloudflare-worker/wrangler.toml:**

```toml
# Add or update staging environment section
[env.staging]
name = "watercooler-cloud-staging"
compatibility_date = "2024-01-01"

# Backend URL (no trailing slash)
[env.staging.vars]
BACKEND_URL = "https://watercooler-cloud-staging.onrender.com"
ALLOW_DEV_SESSION = "false"
AUTO_ENROLL_PROJECTS = "false"

# KV namespace binding
[[env.staging.kv_namespaces]]
binding = "KV_PROJECTS"
id = "<NAMESPACE_ID_FROM_STEP_6>"
```

**Set Worker Secrets:**

```bash
cd cloudflare-worker

# Load secrets from config
source ../.env.staging

# Set secrets (wrangler prompts for input via echo)
echo "$INTERNAL_AUTH_SECRET" | npx wrangler secret put INTERNAL_AUTH_SECRET --env staging
echo "$GITHUB_CLIENT_ID" | npx wrangler secret put GITHUB_CLIENT_ID --env staging
echo "$GITHUB_CLIENT_SECRET" | npx wrangler secret put GITHUB_CLIENT_SECRET --env staging

echo "✅ Secrets configured"
```

### Step 8: Deploy Staging Worker

```bash
cd cloudflare-worker

# Deploy to staging environment
npx wrangler deploy --env staging

# Should see:
# ✅ Successfully published watercooler-cloud-staging (X.XX sec)
#    https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev
```

### Step 9: Seed Staging User ACL

```bash
cd cloudflare-worker

# Get KV namespace ID
KV_ID=$(grep -A 3 "\[env.staging.kv_namespaces\]" wrangler.toml | grep "id =" | cut -d'"' -f2)

# Seed your GitHub user (replace <your-github-username>)
YOUR_GITHUB_USERNAME="<your-github-username>"

npx wrangler kv:key put \
  --namespace-id="$KV_ID" \
  "user:gh:${YOUR_GITHUB_USERNAME}" \
  "{\"user_id\":\"gh:${YOUR_GITHUB_USERNAME}\",\"default\":\"watercooler-cloud\",\"projects\":[\"watercooler-cloud\"]}"

# Verify
npx wrangler kv:key get \
  --namespace-id="$KV_ID" \
  "user:gh:${YOUR_GITHUB_USERNAME}"

echo "✅ ACL seeded for user: ${YOUR_GITHUB_USERNAME}"
```

### Step 10: Verify Staging Stack

```bash
# 1. Check backend health
curl https://watercooler-cloud-staging.onrender.com/health

# Should return: {"status":"ok","version":"..."}

# 2. Test OAuth flow
# Open in browser: https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev/auth/login
# Should redirect to GitHub → authorize → redirect back to /console

# 3. Test MCP connection (using mcp-remote)
npx -y mcp-remote \
  "https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev/sse?project=watercooler-cloud" \
  --header "Authorization: Bearer <token-from-console>"

# Should show available tools
```

---

## Production Stack Deployment

### Step 1: Generate Production Secrets

```bash
cd /path/to/watercooler-cloud

# Generate INTERNAL_AUTH_SECRET (DIFFERENT from staging!)
PRODUCTION_INTERNAL_AUTH_SECRET=$(openssl rand -hex 32)
echo "PRODUCTION_INTERNAL_AUTH_SECRET=${PRODUCTION_INTERNAL_AUTH_SECRET}"

# Generate SSH deploy key
ssh-keygen -t ed25519 -C "watercooler-production" -f .secrets/production_deploy_key -N ""

# Display public key (for GitHub)
cat .secrets/production_deploy_key.pub

# Save to config file
cat > .env.production << EOF
# Watercooler Production Configuration
# Generated: $(date +%Y-%m-%d)

ENVIRONMENT=production
INTERNAL_AUTH_SECRET=${PRODUCTION_INTERNAL_AUTH_SECRET}
SSH_PRIVATE_KEY_PATH=.secrets/production_deploy_key
THREADS_REPO=git@github.com:mostlyharmless-ai/watercooler-cloud-threads.git
BACKEND_URL=https://watercooler-cloud.onrender.com
WORKER_URL=https://watercooler-cloud.mostlyharmless-ai.workers.dev
EOF

echo "✅ Secrets generated and saved to .env.production"
```

### Step 2: Create Production Threads Repository

**Manual Step:** Go to https://github.com/organizations/mostlyharmless-ai/repositories/new

```
Repository name: watercooler-cloud-threads
Description: Watercooler production thread storage
Visibility: ✅ Private
Initialize: ❌ DO NOT check any boxes (create empty repo)
```

Click **"Create repository"**

### Step 3: Add SSH Deploy Key to Production Repo

**Manual Step:** Go to https://github.com/mostlyharmless-ai/watercooler-cloud-threads/settings/keys

Click **"Add deploy key"**:

```
Title: Watercooler Production Backend
Key: <paste contents of .secrets/production_deploy_key.pub>
✅ CHECK "Allow write access" (CRITICAL!)
```

Click **"Add key"**

### Step 3a: Initialize Main Branch in Threads Repository

**CRITICAL:** GitHub repos created empty (no README/license) have no branches. The Render start command expects a cloneable repo with at least one branch.

**Manual Step:** Initialize the main branch locally:

```bash
cd /tmp
git clone git@github.com:mostlyharmless-ai/watercooler-cloud-threads.git
cd watercooler-cloud-threads
git config user.name "Your Name"
git config user.email "your.email@example.com"
git commit --allow-empty -m "Initialize production threads repo"
git push -u origin main
```

⚠️ **Why this is needed:** Without this step, the Render service will fail to clone because the repository has no refs/branches. The start command can handle empty repos with a main branch, but not repos with zero branches.

### Step 4: Create Production OAuth App

**Manual Step:** Go to https://github.com/organizations/mostlyharmless-ai/settings/applications

Click **"New OAuth App"**:

```
Application name: Watercooler Cloud
Homepage URL: https://watercooler-cloud.mostlyharmless-ai.workers.dev
Authorization callback URL: https://watercooler-cloud.mostlyharmless-ai.workers.dev/auth/callback
```

⚠️ **NO trailing slash on callback URL!**

After creating, copy:
- **Client ID** → Save as `PRODUCTION_GITHUB_CLIENT_ID`
- **Client Secret** → Save as `PRODUCTION_GITHUB_CLIENT_SECRET`

```bash
# Add to config file
echo "GITHUB_CLIENT_ID=<paste-client-id>" >> .env.production
echo "GITHUB_CLIENT_SECRET=<paste-client-secret>" >> .env.production
```

### Step 5: Create Production Render Backend

**Same process as staging, but with production values:**

- **Name:** `watercooler-cloud`
- **Branch:** `main`
- **Environment Variables:**
  ```bash
  INTERNAL_AUTH_SECRET=<value from .env.production>
  WATERCOOLER_GIT_REPO=git@github.com:mostlyharmless-ai/watercooler-cloud-threads.git
  WATERCOOLER_DIR=/data/wc-production
  BASE_THREADS_ROOT=/data/wc-production
  GIT_SSH_PRIVATE_KEY=<entire contents of .secrets/production_deploy_key>
  ```
- **Persistent Disk:** `/data` (1 GB)

### Step 6: Create Production KV Namespace

```bash
cd cloudflare-worker

# Create KV namespace for production
npx wrangler kv:namespace create "KV_PROJECTS" --env production

# Save the namespace ID
echo "KV_NAMESPACE_ID_PRODUCTION=<paste-id>" >> ../.env.production
```

### Step 7: Configure Production Worker

**Update cloudflare-worker/wrangler.toml:**

```toml
# Add production environment section
[env.production]
name = "watercooler-cloud"
compatibility_date = "2024-01-01"

[env.production.vars]
BACKEND_URL = "https://watercooler-cloud.onrender.com"
# Note: ALLOW_DEV_SESSION is NOT set (defaults to false)
# Note: AUTO_ENROLL_PROJECTS is NOT set (defaults to false)

[[env.production.kv_namespaces]]
binding = "KV_PROJECTS"
id = "<NAMESPACE_ID_FROM_STEP_6>"
```

**Set Worker Secrets:**

```bash
cd cloudflare-worker
source ../.env.production

echo "$INTERNAL_AUTH_SECRET" | npx wrangler secret put INTERNAL_AUTH_SECRET --env production
echo "$GITHUB_CLIENT_ID" | npx wrangler secret put GITHUB_CLIENT_ID --env production
echo "$GITHUB_CLIENT_SECRET" | npx wrangler secret put GITHUB_CLIENT_SECRET --env production
```

### Step 8: Deploy Production Worker

```bash
cd cloudflare-worker
npx wrangler deploy --env production
```

### Step 9: Seed Production User ACL

```bash
cd cloudflare-worker

KV_ID=$(grep -A 3 "\[env.production.kv_namespaces\]" wrangler.toml | grep "id =" | cut -d'"' -f2)
YOUR_GITHUB_USERNAME="<your-github-username>"

npx wrangler kv:key put \
  --namespace-id="$KV_ID" \
  "user:gh:${YOUR_GITHUB_USERNAME}" \
  "{\"user_id\":\"gh:${YOUR_GITHUB_USERNAME}\",\"default\":\"watercooler-cloud\",\"projects\":[\"watercooler-cloud\"]}"
```

### Step 10: Verify Production Stack

Same verification steps as staging, using production URLs.

---

## Verification & Testing

### Test with Claude CLI

**Add to ~/.claude/mcp.json:**

```json
{
  "mcpServers": {
    "watercooler-staging": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://watercooler-cloud-staging.mostlyharmless-ai.workers.dev/sse?project=watercooler-cloud"
      ],
      "env": {
        "WC_AUTH_COOKIE": "<your-staging-session-cookie>"
      }
    },
    "watercooler-production": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://watercooler-cloud.mostlyharmless-ai.workers.dev/sse?project=watercooler-cloud"
      ],
      "env": {
        "WC_AUTH_COOKIE": "<your-production-session-cookie>"
      }
    }
  }
}
```

**Get session cookie:**
1. Visit staging/production /auth/login in browser
2. Open dev tools → Application → Cookies
3. Copy `wc_session` cookie value

**Test in Claude CLI:**
```bash
# Restart Claude after updating config
# In Claude, type:
@watercooler-staging list threads
@watercooler-production list threads
```

### Test with Codex CLI

**Similar configuration for Codex CLI**

---

## Troubleshooting

### Backend Health Check Fails

```bash
# Check backend logs in Render dashboard
# Verify environment variables are set correctly
# Ensure persistent disk is mounted at /data
```

### OAuth Flow Fails

```bash
# Verify callback URL has NO trailing slash
# Check GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET are correct
# Ensure Worker secrets are set (not in wrangler.toml)
```

### Git Sync Fails

```bash
# Verify SSH deploy key has WRITE access
# Check GIT_SSH_PRIVATE_KEY is complete (including headers)
# Test SSH key: ssh -i .secrets/staging_deploy_key git@github.com
```

### MCP Connection Fails

```bash
# Verify user is in ACL (check KV)
# Check INTERNAL_AUTH_SECRET matches between Worker and Backend
# Ensure BACKEND_URL in wrangler.toml has no trailing slash
```

---

## Summary Checklist

### Staging Stack
- [ ] Secrets generated
- [ ] Threads repo created
- [ ] Deploy key added (with write access)
- [ ] OAuth app created
- [ ] Render backend created with disk
- [ ] Backend environment variables set
- [ ] KV namespace created
- [ ] Worker configured (wrangler.toml + secrets)
- [ ] Worker deployed
- [ ] User ACL seeded
- [ ] Backend health verified
- [ ] OAuth flow tested
- [ ] MCP connection tested

### Production Stack
- [ ] Secrets generated (different from staging)
- [ ] Threads repo created
- [ ] Deploy key added (with write access)
- [ ] OAuth app created
- [ ] Render backend created with disk
- [ ] Backend environment variables set
- [ ] KV namespace created
- [ ] Worker configured (wrangler.toml + secrets)
- [ ] Worker deployed
- [ ] User ACL seeded
- [ ] Backend health verified
- [ ] OAuth flow tested
- [ ] MCP connection tested

---

**End of Dual Stack Deployment Guide**
