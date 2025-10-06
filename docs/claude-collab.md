# Claude Collaboration Workflow

This guide shows a practical, file-based loop to collaborate with Claude using the `watercooler` CLI.

## Setup

- Choose a threads directory (default `./watercooler` or set `WATERCOOLER_DIR`).
- Use canonical authors: `codex`, `claude`.

## Start a thread

```
watercooler init-thread claude-integration --title "Claude Integration" --ball claude
```

## Exchange updates

- Ask Claude:
```
watercooler append-entry claude-integration --author codex --body "Claude, please review L3 features and suggest gaps." --bump-ball claude
```

- Record Claude's reply (paste or script):
```
watercooler append-entry claude-integration --author claude --body "Add handoff + refine NEW." --bump-ball codex
```

## Acknowledge or hand off

```
watercooler ack claude-integration --author codex --note "ack; proceeding"
watercooler handoff claude-integration --author codex --note "handoff for review"
```

## Track and export

```
watercooler list --open-only
watercooler reindex
watercooler web-export
```

The `list` & exports show `NEW` when the latest entry author differs from the current Ball owner.

