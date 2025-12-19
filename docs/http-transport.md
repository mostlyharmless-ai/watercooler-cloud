# HTTP Transport for Watercooler MCP Server

The Watercooler MCP server supports both **stdio** (default) and **HTTP** transports.

## Why HTTP Transport?

- **Reliability:** Better error handling than stdio
- **Debugging:** Easy to monitor with standard HTTP tools
- **Scalability:** Can handle larger payloads without buffer issues
- **Web Clients:** Enables future web-based MCP clients
- **Logging:** Standard HTTP access logs

## Quick Start

### Option 1: Using the Daemon Script (Recommended)

```bash
# Start server
./scripts/mcp-server-daemon.sh start

# Check status
./scripts/mcp-server-daemon.sh status

# View logs
./scripts/mcp-server-daemon.sh logs

# Follow logs in real-time
./scripts/mcp-server-daemon.sh logs -f

# Stop server
./scripts/mcp-server-daemon.sh stop

# Restart server
./scripts/mcp-server-daemon.sh restart
```

### Option 2: Manual Start

```bash
# Set environment variables
export WATERCOOLER_MCP_TRANSPORT=http
export WATERCOOLER_MCP_HOST=127.0.0.1
export WATERCOOLER_MCP_PORT=3000

# Start server
python3 -m watercooler_mcp
```

The server will start on `http://127.0.0.1:3000/mcp` using Server-Sent Events (SSE) for the MCP protocol.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WATERCOOLER_MCP_TRANSPORT` | `stdio` | Transport type: `http` or `stdio` |
| `WATERCOOLER_MCP_HOST` | `127.0.0.1` | HTTP server host (HTTP mode only) |
| `WATERCOOLER_MCP_PORT` | `3000` | HTTP server port (HTTP mode only) |
| `WATERCOOLER_LOG_DIR` | `~/.watercooler` | Directory for logs and PID files |

### Custom Port Example

```bash
WATERCOOLER_MCP_PORT=3001 ./scripts/mcp-server-daemon.sh start
```

## Client Configuration

### Claude Code

Update `~/.config/claude/claude-code/mcp-settings.json`:

**Before (stdio):**
```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "command": "python3",
      "args": ["-m", "watercooler_mcp"],
      "env": {}
    }
  }
}
```

**After (HTTP):**
```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "url": "http://127.0.0.1:3000/mcp",
      "transport": "sse"
    }
  }
}
```

### Cursor

Update `.cursor/mcp.json` with the same HTTP configuration.

## Health Checks

The MCP server exposes a `watercooler_health` tool via the MCP protocol for health checking. This is accessible through any MCP client, but not as a simple HTTP endpoint.

For monitoring, you can:
1. Check if the process is running: `./scripts/mcp-server-daemon.sh status`
2. Monitor the logs: `./scripts/mcp-server-daemon.sh logs`
3. Use the MCP health tool via a connected client

## Logs

Logs are written to `$WATERCOOLER_LOG_DIR/mcp-server.log` (default: `~/.watercooler/mcp-server.log`).

View logs:
```bash
# Last 50 lines
./scripts/mcp-server-daemon.sh logs

# Follow in real-time
./scripts/mcp-server-daemon.sh logs -f

# Direct file access
tail -f ~/.watercooler/mcp-server.log
```

## Troubleshooting

### Port Already in Use

If port 3000 is already in use:
```bash
WATERCOOLER_MCP_PORT=3001 ./scripts/mcp-server-daemon.sh start
```

### Server Won't Start

Check the logs:
```bash
cat ~/.watercooler/mcp-server.log
```

Common issues:
- Python environment not activated
- Missing dependencies: `pip install -e ".[mcp]"`
- Port already in use

### Server Not Responding

```bash
# Check if server is running
./scripts/mcp-server-daemon.sh status

# Restart server
./scripts/mcp-server-daemon.sh restart

# Check logs for errors
./scripts/mcp-server-daemon.sh logs
```

## Backward Compatibility

The default transport is `stdio` for backward compatibility. Existing configurations will continue to work without changes.

To switch to HTTP, either:
1. Set `WATERCOOLER_MCP_TRANSPORT=http` environment variable
2. Use the daemon script (automatically uses HTTP)
3. Update your client configuration to use the HTTP URL

## Technical Details

- **Protocol:** MCP over Server-Sent Events (SSE)
- **Endpoint:** `http://127.0.0.1:3000/mcp` (default)
- **Transport:** Streamable-HTTP
- **Server:** Uvicorn (via FastMCP)

The HTTP transport uses Server-Sent Events (SSE) for streaming MCP protocol messages. This provides better reliability than stdio while maintaining compatibility with the MCP protocol specification.
