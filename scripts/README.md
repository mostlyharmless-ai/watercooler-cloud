# Watercooler Scripts

## KV Setup for Remote MCP

### Quick Start

```bash
# 1. Install wrangler if needed
npm install -g wrangler

# 2. Login to Cloudflare
wrangler login

# 3. Run setup script
cd scripts
chmod +x kv_setup.sh
./kv_setup.sh
```

### Manual KV Setup

If you prefer to set up KV manually:

```bash
# Create KV namespace
wrangler kv:namespace create KV_PROJECTS

# Load user ACLs (example for user gh:caleb)
wrangler kv:key put \
  --namespace-id=<your-kv-id> \
  "gh:caleb" \
  '{"user_id":"gh:caleb","default":"watercooler-collab","projects":["watercooler-collab","proj-alpha"]}'

# Verify
wrangler kv:key get --namespace-id=<your-kv-id> "gh:caleb"
```

### KV Data Structure

Each user entry in KV follows this schema:

```json
{
  "user_id": "gh:username",
  "default": "default-project-id",
  "projects": ["project1", "project2", ...]
}
```

- **user_id**: GitHub username prefixed with `gh:` (matches OAuth identity)
- **default**: Project ID to use when `?project=` is not specified
- **projects**: Array of project IDs this user can access

### Adding New Users

Edit `kv_seed_projects.json` and add a new entry:

```json
{
  "key": "gh:newuser",
  "value": {
    "user_id": "gh:newuser",
    "default": "my-project",
    "projects": ["my-project", "shared-project"]
  }
}
```

Then re-run the setup script or use wrangler directly.

### Project Isolation

Each project gets its own threads directory:
- Local mode: `{BASE_THREADS_ROOT}/{user_id}/{project_id}/`
- Git mode: Mapped per project to separate repositories

This ensures complete data isolation between projects.
