# Frequently Asked Questions

Watercooler’s docs are now organized so each topic has a single home. Use this page as your map—follow the links to the definitive guides instead of reading duplicated content.

## Where do I start?
- **Setup & first actions:** [SETUP_AND_QUICKSTART.md](SETUP_AND_QUICKSTART.md)
- **Identity, roles, entry format:** [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md)
- **Tool signatures & parameters:** [mcp-server.md](mcp-server.md)
- **CLI helpers & library usage:** [integration.md](integration.md#python-api-reference)
- **Problem solving:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

## Quick answers
- **What is watercooler-collab?** A file-based collaboration protocol that mirrors your git workflow with branch-paired threads, explicit ball ownership, and structured entries. Read the overview in the [Setup & Quickstart](SETUP_AND_QUICKSTART.md#what-you-get).
- **Why use it instead of Slack/GitHub issues?** It keeps discussions versioned beside code, preserves provenance (`Code-Repo/Branch/Commit` footers), and remains offline-friendly. See the “Why this works” notes in [BRANCH_PAIRING.md](BRANCH_PAIRING.md).
- **When do I use `say`, `ack`, or `handoff`?** `say` posts an update and flips the ball to your counterpart, `ack` acknowledges without flipping, and `handoff` sets an explicit ball owner. Detailed patterns live in [claude-collab.md](claude-collab.md#exchange-updates-with-claude).
- **How do agents declare identity?** Call `watercooler_v1_set_agent(base="<Agent>", spec="<role>")` or pass `agent_func` on each write, and include `Spec:` in the entry body. See [STRUCTURED_ENTRIES.md#identity-pre-flight](STRUCTURED_ENTRIES.md#identity-pre-flight).
- **Where are advanced deployment docs?** Hosted/remote instructions are archived under `.mothballed/docs/` for reference; the active path is the local universal MCP server.

## Need something else?
- Browse the [Use Cases guide](USE_CASES.md) for end-to-end examples.
- Check the [Roadmap](../ROADMAP.md) to see which deferred features (pagination, JSON output, etc.) are still planned.
- Still stuck? Jump to [TROUBLESHOOTING.md](TROUBLESHOOTING.md) and include the output of `watercooler_v1_health(code_path=".")` when you ask for help.
