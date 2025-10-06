# watercooler-collab

File-based collaboration protocol for agentic coding projects.

## Status

**Phase: L0 - Repository Scaffolding** ✓

This library is under active development following a staged extraction plan.

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

## Roadmap (L-Series)

- [x] **L0**: Repository scaffolding
  - pyproject.toml, src/ layout, CI smoke tests
  - No functional code yet

- [ ] **L1**: Core utilities + CLI stub
  - Extract: `fs.py` (paths/backups), `lock.py` (AdvisoryLock), `header.py` (parsing), `agents.py` (canonical names)
  - CLI: `watercooler --help` with command stubs
  - Tests with sample thread fixtures

- [ ] **L2**: Command parity (append/set/list/reindex)
  - Port all core commands with snapshot parity validation
  - Maintain stdlib-only constraint

- [ ] **L3**: Advanced features (web-export/search)
  - NEW marker computation
  - CLOSED filtering
  - HTML export with configurable link behavior

- [ ] **L4**: Documentation + PyPI publication
  - API reference + 2-3 tutorials
  - Publish to TestPyPI, then PyPI
  - Version 0.1.0

## Installation

Not yet published. For development:

```bash
git clone https://github.com/mostlyharmless-ai/watercooler-collab.git
cd watercooler-collab
pip install -e .
```

## Quick Example (Coming in L2+)

```bash
# Initialize a thread
watercooler init-thread feature_discussion --ball Codex

# Say something (quick note)
echo "Proposal accepted, moving forward" | watercooler say feature_discussion "Decision"

# Check status
watercooler list --status OPEN
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