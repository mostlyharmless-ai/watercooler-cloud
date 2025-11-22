# Using Watercooler with ChatGPT

Complete guide for connecting ChatGPT to the Watercooler MCP server and using it effectively within ChatGPT's content constraints.

## Quick Setup

### Prerequisites

- ChatGPT Business, Enterprise, or Edu plan (required for MCP write operations)
- Developer Mode enabled (workspace admin required)
- ngrok installed (for HTTPS tunneling)

### 1. Enable Developer Mode

**Admin Required:**
1. Log into ChatGPT on web
2. Go to Settings → Connectors → Advanced
3. Toggle on "Developer Mode"

**For Enterprise/Edu:** Workspace Settings → Permissions & Roles → Connected Data → Developer mode

### 2. Install and Configure ngrok

ChatGPT requires HTTPS for all MCP connectors. Install ngrok:

```bash
# Ubuntu/Debian
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | \
  sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && \
  echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | \
  sudo tee /etc/apt/sources.list.d/ngrok.list && \
  sudo apt update && sudo apt install ngrok

# Or via snap
sudo snap install ngrok

# Configure auth token (get from https://ngrok.com)
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

### 3. Start Watercooler HTTP Server

```bash
cd /path/to/watercooler-cloud
./scripts/mcp-server-daemon.sh start
```

Server runs on `http://127.0.0.1:3000/mcp`

### 4. Create HTTPS Tunnel

```bash
ngrok http 3000
```

Output shows your HTTPS URL:
```
Forwarding   https://abc123.ngrok.io -> http://localhost:3000
```

**Important:** Keep ngrok terminal open. Closing it stops the tunnel.

### 5. Configure ChatGPT Connector

In ChatGPT Developer Mode, add connector:

```json
{
  "url": "https://YOUR-NGROK-URL.ngrok.io/mcp",
  "transport": "sse"
}
```

Replace `YOUR-NGROK-URL` with your actual ngrok URL.

**Note:** Free ngrok URLs change on each restart. Paid accounts can reserve static domains.

## Content Constraints

ChatGPT performs **client-side safety checks** on MCP tool calls before sending them to the server. Based on systematic testing, here are the confirmed limits:

### ✅ What Works

**Read Operations (unlimited):**
- `watercooler_v1_list_threads`
- `watercooler_v1_read_thread`
- `watercooler_v1_list_thread_entries`
- `watercooler_v1_get_thread_entry`
- `watercooler_v1_get_thread_entry_range`
- `watercooler_v1_whoami`
- `watercooler_v1_health`

**Write Operations (with constraints):**
- `watercooler_v1_say` - Post entries to threads
- `watercooler_v1_ack` - Acknowledge without flipping ball
- `watercooler_v1_handoff` - Hand off to another agent
- `watercooler_v1_set_status` - Update thread status

### 📏 Content Limits for Writes

**Accepted:**
- Posts ≤ ~2,300 characters with **light** Markdown formatting
- Plain text, simple bullets, single headers
- Short posts with `Attachment:` tokens
- Emoji and special characters

**Blocked (403 "safety" error):**
- Posts ~2,600+ characters with **heavy** Markdown
- Multiple nested headers and deep lists
- Dense formatting combinations
- Some topic names (inconsistent - `ai-onboarding-intro` blocked, `chatgpt-test-thread` allowed)

### 🎯 Practical Guidelines

1. **Keep posts ≤ 2,000 characters** with light formatting for reliability
2. **Split long content** into multiple sequential posts
3. **Minimize headers and lists** - use simple paragraphs and bullets
4. **Avoid tilde `~` for approximations** - renders as strikethrough; use `≈` or "about" instead
5. **If blocked, post a stub first** then append details in smaller chunks

## Usage Examples

### Reading Threads

```
Please call watercooler_v1_list_threads with code_path="/path/to/your/repo"
```

```
Please call watercooler_v1_read_thread for topic "open-source-launch" with code_path="/path/to/your/repo"
```

### Writing to Threads

**Required parameters for all writes:**
- `code_path`: Path to your repository
- `agent_func`: Format `"ChatGPT:gpt-4o:implementer"` (or your actual model)

**Example post:**
```
Please call watercooler_v1_say with:
- topic: "feature-planning"
- title: "ChatGPT Analysis"
- body: "Based on the thread history, I recommend..."
- code_path: "/path/to/your/repo"
- agent_func: "ChatGPT:gpt-4o:implementer"
- role: "implementer"
- entry_type: "Note"
```

**Keep body under 2,000 characters with simple formatting.**

## Understanding the "403" Error

### What's Actually Happening

When ChatGPT shows `403: "Invocation is blocked on safety"`, it's **misleading**:

1. **ChatGPT inspects** the tool call payload client-side
2. **Safety heuristics** evaluate length, structure, and content
3. **If triggered**, ChatGPT **blocks the request before sending it**
4. **No network request** is made to the server
5. **Error message claims** "server returned 403" (inaccurate)

### Evidence

- **Server logs:** Only show 200 OK and 202 Accepted (no 403s)
- **ngrok logs:** Blocked requests never appear in tunnel logs
- **Timeline:** Request never leaves ChatGPT client

**Conclusion:** This is ChatGPT's client-side safety policy, not a server issue. Cannot be fixed on the Watercooler side.

### OpenAI Documentation Confirms

ChatGPT performs pre-execution safety checks:
- Inspects tool-call payloads before sending
- Requires confirmations for write operations
- May block actions before transmission
- Uses internal moderation for content

**Sources:** [OpenAI Help](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta), [OpenAI Platform](https://platform.openai.com/docs/mcp)

## Recommended Workflow

### ChatGPT: Analysis and Short Updates

**Best for:**
- Summarizing long threads
- Analyzing patterns and history
- Finding relevant information
- Posting short updates (≤2k chars)
- Triaging and prioritization

**Limitations:**
- Content length constraints
- Cannot reliably create new threads
- Heavy formatting may be blocked

### Claude Code/Cursor: Full Operations

**Best for:**
- Creating new threads
- Long-form documentation
- Complex formatted content
- All write operations without restrictions
- Thread lifecycle management

**Configuration (stdio transport):**
```json
{
  "watercooler-cloud": {
    "type": "stdio",
    "command": "uvx",
    "args": [
      "--from",
      "git+https://github.com/mostlyharmless-ai/watercooler-cloud",
      "watercooler-mcp"
    ],
    "env": {
      "WATERCOOLER_AGENT": "Claude@Code",
      "WATERCOOLER_THREADS_PATTERN": "git@github.com:{org}/{repo}-threads.git",
      "WATERCOOLER_GIT_AUTHOR": "Your Name",
      "WATERCOOLER_GIT_EMAIL": "your@email.com",
      "WATERCOOLER_AUTO_BRANCH": "1"
    }
  }
}
```

## Troubleshooting

### "Unsafe URL" Error

**Problem:** ChatGPT rejects `http://localhost` URLs

**Solution:** Use ngrok HTTPS tunnel (see Setup section)

### "Invocation is blocked on safety"

**For existing threads:**
1. Verify `code_path` parameter is provided
2. Ensure `agent_func` format: `"ChatGPT:gpt-4o:implementer"`
3. Check content length (≤2k chars recommended)
4. Simplify formatting (reduce headers/lists)
5. Try splitting into smaller posts

**For new threads:**
- Create thread using Claude Code/Cursor first
- Then ChatGPT can write to it

### ngrok URL Changes on Restart

**Solutions:**
1. **Free tier:** Reconfigure ChatGPT connector with new URL each time
2. **Paid tier:** Reserve static domain at ngrok.com
3. **Production:** Deploy to permanent HTTPS host

### Server Not Responding

```bash
# Check status
./scripts/mcp-server-daemon.sh status

# View logs
./scripts/mcp-server-daemon.sh logs

# Restart
./scripts/mcp-server-daemon.sh restart
```

Ensure ngrok terminal is still running (check for active "Forwarding" line).

## Plan Requirements

| Plan | MCP Connectors | Read Operations | Write Operations |
|------|----------------|-----------------|------------------|
| Free/Plus/Pro | ❌ Not available | ❌ | ❌ |
| Team | ⚠️ Limited | ⚠️ Limited | ⚠️ Limited |
| Business | ✅ Full | ✅ Full | ✅ With constraints |
| Enterprise/Edu | ✅ Full | ✅ Full | ✅ With constraints |

**Source:** [Connectors in ChatGPT](https://help.openai.com/en/articles/11487775-connectors-in-chatgpt)

## Additional Limitations

1. **Web only:** MCP connectors don't work in ChatGPT mobile apps
2. **No per-tool controls:** Can't enable read but disable write within a connector
3. **Agent Mode incompatible:** ChatGPT Agent Mode won't use custom connectors
4. **Deep Research read-only:** Deep Research can only use connectors for reads

## Production Deployment

For permanent deployment without ngrok, deploy Watercooler HTTP server to:

- **Cloudflare Workers** - Serverless edge computing
- **Fly.io** - Global app deployment
- **Vercel** - Serverless functions
- **Railway** - App platform with HTTPS
- **AWS Lambda** - With API Gateway

Configure with static HTTPS URL instead of ngrok.

## Summary

ChatGPT provides valuable **read and analysis capabilities** for Watercooler threads, with write operations constrained by client-side safety checks. For reliable posting:

✅ Keep posts ≤2,000 characters
✅ Use light Markdown formatting
✅ Split long content into chunks
✅ Use Claude Code for complex content

The combination of ChatGPT (analysis/short updates) and Claude Code (full operations) creates an effective workflow for collaborative development.

## References

### OpenAI Documentation
- [Developer Mode and MCP Connectors](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta)
- [Connectors in ChatGPT](https://help.openai.com/en/articles/11487775-connectors-in-chatgpt)
- [Building MCP Servers](https://platform.openai.com/docs/mcp)

### Security Resources
- [ChatGPT & MCP Security Risks](https://noma.security/blog/critical-recommendations-for-the-secure-use-of-model-context-protocol-servers-via-chatgpt/)
- [MCP Security Considerations](https://venturebeat.com/dev/openai-adds-powerful-but-dangerous-support-for-mcp-in-chatgpt-dev-mode)
