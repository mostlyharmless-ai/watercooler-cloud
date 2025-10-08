# Suggested Commands

## Development
```bash
# Install for development
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Install with MCP support
pip install -e ".[mcp]"
```

## Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_templates.py -v
```

## Type Checking
```bash
mypy src/
```

## MCP Server Setup
```bash
# Quick setup for Claude Code
./scripts/install-mcp.sh

# Manual registration
fastmcp install claude-code src/watercooler_mcp/server.py --env WATERCOOLER_AGENT=Claude
```

## Git Configuration
```bash
# Enable "ours" merge driver
git config merge.ours.driver true

# Enable pre-commit hook
git config core.hooksPath .githooks
```

## CLI Commands
```bash
# Initialize thread
watercooler init-thread <topic>

# Add entry
watercooler append-entry <topic>

# Quick note with ball flip
watercooler say <topic>

# Acknowledge without ball flip
watercooler ack <topic>

# Handoff to counterpart
watercooler handoff <topic>

# Set status/ball
watercooler set-status <topic> <status>
watercooler set-ball <topic> <agent>

# List/search
watercooler list
watercooler search <query>

# Index/export
watercooler reindex
watercooler web-export

# Unlock thread
watercooler unlock <topic>
```
