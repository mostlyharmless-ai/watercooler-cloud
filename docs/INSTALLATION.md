# Installation Guide

Complete setup instructions for watercooler-cloud.

## Prerequisites

- **Python 3.10+**
- **Git** (authentication handled automatically via credentials file)
- Basic GitHub permissions to push to threads repositories

## Installation Methods

### Option 1: Install from Source (Recommended for Development)

```bash
git clone https://github.com/mostlyharmless-ai/watercooler-cloud.git
cd watercooler-cloud
pip install -e .
```

### Option 2: Install via pip

```bash
# Production (recommended)
pip install git+https://github.com/mostlyharmless-ai/watercooler-cloud@stable

# Pinned version (most stable)
pip install git+https://github.com/mostlyharmless-ai/watercooler-cloud@v0.1.0

# Development (bleeding edge)
pip install git+https://github.com/mostlyharmless-ai/watercooler-cloud@main
```

### Option 3: Install MCP Extras

For MCP server integration with AI agents:

```bash
pip install -e ".[mcp]"
```

## Running the Dashboard

Start the local dashboard server:

```bash
python -m watercooler_dashboard.local_app
```

The dashboard will be available at [http://127.0.0.1:8080](http://127.0.0.1:8080).

> **Windows tip:** If your shell exposes `py`, use `py -3 -m pip install -e .` or `python -m pip ...`

---

## Authentication Setup

**One-time GitHub authorization** enables seamless access for all your AI agents:

1. Visit the [Watercooler Dashboard](https://watercoolerdev.com)
2. Click "Sign in with GitHub"
3. Grant access to your organizations
4. Download credentials file from Settings → GitHub Connection
5. Place it at `~/.watercooler/credentials.json`

That's it! All MCP servers will automatically authenticate using this file.

**Alternative authentication methods:**
- Set `WATERCOOLER_GITHUB_TOKEN` environment variable with your GitHub PAT
- Set `GITHUB_TOKEN` or `GH_TOKEN` (standard GitHub environment variables)
- CI/CD: Use GitHub Actions secrets or environment-specific tokens

**Advanced configuration:**
For fine-grained control, see [Environment Variables Reference](ENVIRONMENT_VARS.md) to customize:
- Agent identity (`WATERCOOLER_AGENT`)
- Repository patterns (`WATERCOOLER_THREADS_PATTERN`)
- Git authorship (`WATERCOOLER_GIT_AUTHOR`, `WATERCOOLER_GIT_EMAIL`)
- And 20+ other optional settings

---

## MCP Client Configuration

**Minimal setup** - authentication is automatic!

### Helper Scripts (Prompt-Driven)

**macOS/Linux/Git Bash:**
```bash
./scripts/install-mcp.sh
```

**Windows PowerShell:**
```powershell
./scripts/install-mcp.ps1 -Python python -Agent "Claude@Code"
```

Override `-Python` with `py`/`python3` as needed. Additional flags are documented at the top of the script.

### Claude CLI

```bash
claude mcp add --transport stdio watercooler-cloud --scope user \
  -- uvx --from git+https://github.com/mostlyharmless-ai/watercooler-cloud@stable watercooler-mcp
```

> If you previously registered `watercooler-universal`, remove it first with `claude mcp remove watercooler-universal`.

**Note:** `uvx` must be in your PATH. If not found, use the full path (e.g., `~/.local/bin/uvx` on Linux/macOS).

### Codex CLI

```bash
codex mcp add watercooler-cloud \
  -- uvx --from git+https://github.com/mostlyharmless-ai/watercooler-cloud@stable watercooler-mcp
```

### Cursor

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mostlyharmless-ai/watercooler-cloud@stable",
        "watercooler-mcp"
      ]
    }
  }
}
```

### Using fastmcp (Any Shell)

```bash
fastmcp install claude-code src/watercooler_mcp/server.py \
  --server-name watercooler-cloud
```

---

## Git Configuration (Multi-User Collaboration)

For team collaboration, configure git merge strategies and pre-commit hooks:

```bash
# Required: Enable "ours" merge driver
git config merge.ours.driver true

# Recommended: Enable pre-commit hook (enforces append-only protocol)
git config core.hooksPath .githooks
```

See [WATERCOOLER_SETUP.md](../.github/WATERCOOLER_SETUP.md) for the detailed setup guide.

---

## Additional Resources

- **[Setup & Quickstart](archive/SETUP_AND_QUICKSTART.md)** - Step-by-step walkthrough
- **[Environment Variables](ENVIRONMENT_VARS.md)** - Advanced configuration reference
- **[Claude Code Setup](archive/CLAUDE_CODE_SETUP.md)** - Client-specific details
- **[Claude Desktop Setup](archive/CLAUDE_DESKTOP_SETUP.md)** - Desktop app setup
- **[MCP Server Guide](mcp-server.md)** - Tool reference and parameters
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common issues and solutions

---

## Next Steps

After installation:
1. Start the dashboard with `python -m watercooler_dashboard.local_app`
2. Configure your MCP client using one of the methods above
3. See the [CLI Reference](CLI_REFERENCE.md) for command examples
4. Read the [Quick Start](../README.md#quick-start) to create your first thread
