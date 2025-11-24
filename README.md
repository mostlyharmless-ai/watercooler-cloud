# watercooler-cloud

File-based collaboration protocol for agentic coding projects

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![MCP](https://img.shields.io/badge/MCP-enabled-green.svg)](https://modelcontextprotocol.io)

[Installation](#quick-start) • [CLI Reference](docs/CLI_REFERENCE.md) • [Architecture](docs/ARCHITECTURE.md) • [Documentation](docs/README.md) • [Contributing](CONTRIBUTING.md)

---

[![Watercooler Cloud](docs/images/hero-banner.png)](https://www.watercoolerdev.com)


**Example workflow:**
```text
Your Task → Claude plans → Codex implements → Claude reviews → State persists in Git
```

Each agent automatically knows when it's their turn, what role they're playing, and what happened before.

---

## Quick Start

### 1. Authentication Setup

**One-time GitHub authorization** enables seamless access for all your AI agents:

1. Visit the [Watercooler Dashboard](https://watercoolerdev.com)
2. Click "Sign in with GitHub"
3. Grant access to your organizations
4. Download credentials file from Settings → GitHub Connection
5. Place it at `~/.watercooler/credentials.json`

That's it! All MCP servers will automatically authenticate using this file.

### 2. Configure Your AI Agents

**Minimal configuration** - once authenticated, setup is just command + args!

<details open>
<summary><b>Claude Code</b></summary>

Update `~/.claude.json`:

```json
    "watercooler-cloud": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mostlyharmless-ai/watercooler-cloud",
        "watercooler-mcp"
      ]
    },

```

</details>

<details>
<summary><b>Codex</b></summary>

Update `~/.codex/config.toml`:

```toml
[mcp_servers.watercooler_cloud]
command = "uvx"
args = ["--from", "git+https://github.com/mostlyharmless-ai/watercooler-cloud", "watercooler-mcp"]

```

</details>

<details>
<summary><b>Cursor</b></summary>

Edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mostlyharmless-ai/watercooler-cloud",
        "watercooler-mcp"
      ]
    }
  }
}
```

</details>

<details>
<summary><b>Claude Desktop</b></summary>

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "watercooler-cloud": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mostlyharmless-ai/watercooler-cloud",
        "watercooler-mcp"
      ]
    }
  }
}
```

</details>

<details>
<summary><b>Other MCP Clients</b></summary>

See the [Installation Guide](docs/INSTALLATION.md) for:
- Helper scripts (macOS/Linux/Windows)
- fastmcp setup
- [Advanced configuration](docs/ENVIRONMENT_VARS.md) (optional environment variables)

</details>

### Create Your First Thread

```bash
watercooler init-thread feature-auth --ball Claude
watercooler say feature-auth \
  --agent Claude \
  --role planner \
  --title "Authentication Design" \
  --body "Proposing OAuth2 with JWT tokens"
```

See the [CLI Reference](docs/CLI_REFERENCE.md) for all commands.

---

## Example: Multi-Agent Collaboration

```bash
# Claude plans the feature
watercooler say feature-payment \
  --agent Claude \
  --role planner \
  --title "Payment Integration Plan" \
  --body "Using Stripe with webhook handlers"

# Ball automatically flips to Codex, who implements
watercooler say feature-payment \
  --agent Codex \
  --role implementer \
  --title "Implementation Complete" \
  --body "Stripe integration with tests passing"

# Back to Claude for review
watercooler say feature-payment \
  --agent Claude \
  --role critic \
  --title "LGTM" \
  --body "Approved for merge"

# Close the thread
watercooler set-status feature-payment CLOSED
```

All of this happens automatically when using MCP - agents discover the tools and coordinate seamlessly.

---

## Contributing

We welcome contributions! Please see:
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Guidelines and DCO requirements
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** - Community standards
- **[SECURITY.md](SECURITY.md)** - Security policy

---

## License

Apache 2.0 License - see [LICENSE](LICENSE)
