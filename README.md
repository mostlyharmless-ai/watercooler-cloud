# watercooler-collab

File-based collaboration protocol for agentic coding projects.

## Status

L1 is complete and most of L2/L3 are implemented. The CLI is functional and covered by tests.

## Design Principles

- **Stdlib-only**: No external runtime dependencies
- **File-based**: Git-friendly markdown threads with explicit Status/Ball tracking
- **Zero-config**: Works out-of-box for standard project layouts
- **CLI parity**: Drop-in replacement for existing watercooler.py workflows

## Architecture

Thread-based collaboration with:
- **Status tracking**: OPEN, IN_REVIEW, CLOSED
- **Ball ownership**: Explicit tracking of who has the next action
- **Append-only entries**: Timestamped entries with agent identification
- **Advisory file locking**: PID-aware locks with TTL for concurrent safety
- **Automatic backups**: Rolling backups per thread in `.bak/<topic>/`
- **Index generation**: Actionable/Open/In Review summaries with NEW markers

## Implemented

- Core utilities: fs, lock, header, agents, metadata, templates
- CLI commands: init-thread, append-entry, say, ack, set-status, set-ball, list, reindex, search, web-export
- Tests: 20+ passing tests, stdlib-only

## Installation

Not yet published. For development:

```bash
git clone https://github.com/mostlyharmless-ai/watercooler-collab.git
cd watercooler-collab
pip install -e .
```

## Quick Examples

```bash
# Initialize a thread
watercooler init-thread feature_discussion --threads-dir ./watercooler --ball codex
watercooler append-entry feature_discussion --threads-dir ./watercooler --body "Proposal accepted"
watercooler set-status feature_discussion in-progress --threads-dir ./watercooler
watercooler list --threads-dir ./watercooler
watercooler reindex --threads-dir ./watercooler
watercooler search decision --threads-dir ./watercooler
watercooler web-export --threads-dir ./watercooler
```

## Development

Run tests:
```bash
pip install -e ".[dev]"
pytest tests/
```

## License

MIT License - see LICENSE file

## Links

- Repository: https://github.com/mostlyharmless-ai/watercooler-collab
- Issues: https://github.com/mostlyharmless-ai/watercooler-collab/issues
