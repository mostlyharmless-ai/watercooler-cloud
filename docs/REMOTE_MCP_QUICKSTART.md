# Remote MCP Quickstart

Quick guide to using Watercooler via Remote MCP with OAuth authentication and per-project isolation.

## Prerequisites

- Claude Desktop or Cursor with MCP support
- `npx` and `mcp-remote` (installed automatically)
- Access to the deployed Cloudflare Worker URL

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

## First Connection

1. **Restart your client** (Claude Desktop or Cursor)
2. On first connection, a **browser window will open** for GitHub OAuth
3. **Sign in with GitHub** and authorize the application
4. The browser will show "OAuth successful! You can close this window."
5. Return to your client - you should now see watercooler tools available

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
- OAuth flow didn't complete
- Restart client and watch for browser popup
- Check browser isn't blocking popups

### "Access denied to project"
- Project not in your ACL
- Ask admin to add project to your KV entry
- Verify project name matches exactly (case-sensitive)

### "Tools not appearing"
- Restart client after config change
- Check URL ends with `/sse`
- Verify Worker is deployed and healthy

### "Backend error"
- Check Worker logs: `wrangler tail`
- Verify Python backend is running and accessible
- Check `X-Internal-Auth` secret matches

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
- Set up additional users in KV (see [scripts/README.md](../scripts/README.md))
- Configure git sync for cloud storage (optional)
- Add Cloudflare Access for org-wide SSO (optional)
