# Watercooler Scripts

Utility scripts for watercooler-cloud development and deployment.

## Memory Graph

### build_memory_graph.py

Builds a memory graph from watercooler threads and exports to LeanRAG format.

```bash
# Basic usage - build graph from threads
python scripts/build_memory_graph.py /path/to/threads-repo

# Export to LeanRAG format
python scripts/build_memory_graph.py /path/to/threads-repo --export-leanrag ./output

# Save intermediate graph JSON
python scripts/build_memory_graph.py /path/to/threads-repo -o graph.json --export-leanrag ./output
```

Output:
- `documents.json` - Entries with chunks for LeanRAG processing
- `threads.json` - Thread metadata
- `manifest.json` - Export statistics

See [docs/MEMORY.md](../docs/MEMORY.md) for the full LeanRAG integration pipeline.

## MCP Server

### install-mcp.sh / install-mcp.ps1

Install the watercooler MCP server for AI coding assistants.

```bash
# Linux/macOS
./scripts/install-mcp.sh

# Windows (PowerShell)
.\scripts\install-mcp.ps1
```

Configures:
- Claude Code (`~/.claude/claude_desktop_config.json`)
- Codex CLI (`~/.codex/config.toml`)

### mcp-server-daemon.sh

Run the MCP server as a persistent daemon with HTTP transport.

```bash
./scripts/mcp-server-daemon.sh [host] [port]
# Default: 127.0.0.1:8080
```

## Git Integration

### git-credential-watercooler

Git credential helper for GitHub authentication via watercooler-site dashboard.

```bash
# Install as git credential helper
git config --global credential.helper /path/to/scripts/git-credential-watercooler

# Usage (automatic - git calls this when credentials needed)
echo "protocol=https\nhost=github.com" | ./scripts/git-credential-watercooler get
```

Retrieves GitHub tokens from the watercooler dashboard OAuth flow.
