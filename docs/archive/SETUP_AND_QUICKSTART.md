> **📦 Archived Documentation**: This document may contain outdated installation URLs. For current setup instructions, see [INSTALLATION.md](../INSTALLATION.md). Production users should install from the `@stable` branch.

# Watercooler — Setup & Quickstart

Your single stop for getting the Watercooler MCP server running in universal dev mode, wiring branch-paired threads, and performing the first few calls. The goal: clone one repo, run one registration command, and be productive in minutes.

## What You Get
- **Universal MCP server** that discovers the active repo, branch, and commit automatically
- **Git-native shadow repo** with 1:1 branch mirroring (see [Branch Pairing Contract](BRANCH_PAIRING.md))
- **Identity guardrails** so every entry carries an explicit specialization (`Spec:`)
- **First-call walkthrough** for `list`, `read`, `say`, `ack`, `handoff`, and `set_status`

## 1. Prerequisites
- Python 3.10+
- Git (with SSH or PAT access to `<org>/<repo>-threads`)
- `pip install -e .[mcp]` from this repo (installs `fastmcp` and `watercooler-mcp`)
- Basic GitHub permissions to push to the threads repo

Optional but helpful:
- `fastmcp` CLI (bundled with the extras above)
- Git configured to use `merge=union` for markdown within the threads repo (see sample `.gitattributes` below)

## 2. Understand the architecture
- Each code repository pairs with a dedicated threads repository named `<repo>-threads`
- Branches mirror 1:1. Checking out `feature/payment` in the code repo causes the MCP server to open `feature/payment` in the threads repo (creating it if needed)
- Every write records `Code-Repo`, `Code-Branch`, `Code-Commit`, `Watercooler-Entry-ID`, `Watercooler-Topic`, and `Spec` footers for provenance

Dive deeper in [BRANCH_PAIRING.md](BRANCH_PAIRING.md) for the full rationale and edge cases.

## 3. Authentication setup

**One-time GitHub authorization** enables seamless access:

1. Visit the [Watercooler Dashboard](https://watercoolerdev.com)
2. Click "Sign in with GitHub"
3. Grant access to your organizations
4. Download credentials file from Settings → GitHub Connection
5. Place it at `~/.watercooler/credentials.json`

All git authentication now happens automatically via this credentials file.

### Optional: Configure threads repo merge strategy

In the threads repo itself, ensure markdown merges are append-friendly:

```
# .gitattributes (threads repo)
*.md    merge=union
*.jsonl merge=union
index.md merge=ours
```

## 4. Register the universal MCP server

Run **one** command per client. It registers a user-scope server that adapts to whatever repo you open.

**Claude CLI:**
```bash
claude mcp add --transport stdio watercooler-cloud --scope user \
  -- uvx --from git+https://github.com/mostlyharmless-ai/watercooler-cloud watercooler-mcp
```

**Codex CLI:**
```bash
codex mcp add watercooler-cloud \
  -- uvx --from git+https://github.com/mostlyharmless-ai/watercooler-cloud watercooler-mcp
```

**Cursor:**
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

**Note:** `uvx` must be in your PATH. If it's not found, use the full path (e.g., `~/.local/bin/uvx` on Linux/macOS). The `uvx` command ensures you always get the latest code from the repository and runs in an isolated environment.

For Claude Desktop, see the client appendices referenced from the main [README](README.md).

## 5. Identity pre-flight

Before any write (`say`, `ack`, `handoff`, `set_status`), your session must declare identity:

1. Call `watercooler_set_agent(base="Claude Code", spec="implementer-code")` **or** supply `agent_func="Claude Code:sonnet-4:implementer"` on each write (format: `<platform>:<model>:<role>`)
2. Include a visible `Spec: <value>` line in your entry body (Watercooler protocol requirement)
3. Keep `spec` aligned with the entry role (`planner`, `critic`, `implementer`, `tester`, `pm`, `scribe`)

See [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md#identity-pre-flight) for deeper rules, including enforcement via `WATERCOOLER_REQUIRE_IDENTITY`.

## 6. Call the tools (with required parameters)

`code_path` is mandatory for every tool. Use `"."` when your MCP client runs inside the repo; otherwise pass an absolute path.

```text
watercooler_list_threads(code_path=".")
watercooler_read_thread(topic="trial-run", code_path=".")
watercooler_say(topic="trial-run", title="Dev server OK", body="Spec: implementer-code — universal mode", role="implementer", code_path=".", agent_func="Claude Code:sonnet-4:implementer")
watercooler_ack(topic="trial-run", title="Ack", code_path=".", agent_func="Claude Code:sonnet-4:pm")
watercooler_handoff(topic="trial-run", note="Your turn", target_agent="Codex", code_path=".", agent_func="Claude Code:sonnet-4:pm")
watercooler_set_status(topic="trial-run", status="IN_REVIEW", code_path=".", agent_func="Claude Code:sonnet-4:pm")
```

If `code_path` or `agent_func` is omitted, the server fails fast with an actionable error. This protects you from writing into the wrong threads branch.

## 7. Verify the full loop

1. `watercooler_list_threads(code_path=".")` → confirm the thread index renders
2. `watercooler_say(...)` → wait a few seconds
3. Inspect the sibling `<repo>-threads` directory (e.g., `../<repo>-threads`) and run `git log -1 --pretty=raw` — you should see the footers (`Code-Repo`, `Code-Branch`, `Spec`, etc.)
4. Optional: `watercooler_reindex(code_path=".")` to regenerate the index and ensure the threads repo merges cleanly

## 8. Next steps

- Need CLI specifics? Read [archive/claude-collab.md](archive/claude-collab.md) for manual workflows
- Want the full tool surface area? See the [MCP Server Reference](mcp-server.md)
- Running validation? Follow the [Tester Playbook](archive/TESTER_SETUP.md)
- Custom agent behaviors? Configure [archive/AGENT_REGISTRY.md](archive/AGENT_REGISTRY.md)

## Coming soon

We plan to ship helper wrappers so clients can infer `code_path` automatically and remember `agent_func` per session. Until those land, keep the manual parameters above. Follow the prerelease-polish work queue in GitHub Issues for updates.

## Support & troubleshooting

Encounter friction? Jump to [TROUBLESHOOTING.md](TROUBLESHOOTING.md). When filing issues, include the output of `watercooler_health(code_path=".")` and your MCP client version.

Welcome to the shadow repo era—run the quickstart once and Watercooler becomes indispensable in every branch you touch.
