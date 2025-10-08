# Implementation Plan: L1-L4 Phases

## Overview

This document guides the implementation of watercooler-collab library extraction from the acpmonkey project. The goal is to create a reusable, stdlib-only Python package that maintains 100% CLI parity with the current watercooler.py implementation.

**Source Repository:** acpmonkey project at `/Users/jay/projects/acpmonkey/watercooler.py`

**Target Repository:** This repo (watercooler-collab)

**Constraint:** Each PR should be ≤200 LOC to maintain reviewability and minimize risk.

---

## L1 Phase: Core Utilities + CLI Stub

### Objective
Extract foundational utilities and create a minimal CLI that can be invoked, with no-op commands that exit cleanly.

### Source File Reference
All extraction from: `/Users/jay/projects/acpmonkey/watercooler.py`

### Modules to Create

#### 1. `src/watercooler/fs.py` - File System Utilities

Extract these functions from watercooler.py:
- `utcnow_iso()` - lines 49-50
- `read(p: Path) -> str` - lines 52-53
- `write(p: Path, s: str) -> None` - lines 55-56
- `ensure_exists(p: Path, hint: str) -> None` - lines 58-60
- `_now_ts() -> str` - lines 68-69
- `_backup_file(p: Path, keep: int = 3, topic: str | None = None) -> None` - lines 71-87
- `thread_path(topic: str, threads_dir: Path) -> Path` - lines 257-259
- `lock_path_for_topic(topic: str, threads_dir: Path) -> Path` - lines 261-264
- `read_body(maybe_path: str | None) -> str` - lines 187-208

Keep these functions pure with no side effects except file I/O.

#### 2. `src/watercooler/lock.py` - Advisory Locking

Extract the complete `AdvisoryLock` class:
- Class definition - lines 89-186
- Keep all PID tracking logic intact
- Preserve TTL, timeout, and force-break behavior
- Maintain environment variable configuration

This is a complete, self-contained class - extract as-is.

#### 3. `src/watercooler/header.py` - Thread Header Operations

Extract these functions:
- `_header_split(text: str) -> tuple[str, str]` - lines 221-229
- `_replace_header_line(block: str, key: str, value: str) -> str` - lines 231-245
- `bump_header(text: str, *, status: str | None = None, ball: str | None = None) -> str` - lines 247-253

These handle parsing and updating thread file headers (Status, Ball, etc.).

#### 4. `src/watercooler/agents.py` - Agent Registry & Canonicalization

Extract these functions:
- `_load_agents_registry(path: str | None) -> dict` - lines 270-317
- `_split_agent_and_tag(agent: str) -> tuple[str, str | None]` - lines 319-326
- `_get_git_user() -> str | None` - lines 328-336
- `_canonical_agent(agent: str, registry: dict | None = None) -> str` - lines 338-348
- `_counterpart_of(agent: str, registry: dict | None = None) -> str` - lines 350-356
- `_default_agent_and_role(registry: dict | None = None) -> tuple[str, str]` - lines 210-217

Handles mapping agent names (claude, codex, team) to canonical forms and determining counterparts for ball-flip logic.

#### 5. `src/watercooler/templates.py` - Template Processing

Extract:
- `_fill_template(src: str, mapping: dict[str, str]) -> str` - lines 358-380

Handles token replacement in templates.

#### 6. `src/watercooler/metadata.py` - Thread Metadata Extraction

Extract:
- `_last_entry_iso(s: str) -> str | None` - lines 266-268
- `_normalize_status(status: str) -> str` - lines 587-589
- `thread_meta(p: Path) -> tuple[str, str, str, str]` - lines 591-597
- Global regex patterns: `STAT_RE`, `BALL_RE`, `UPD_RE`, `TITLE_RE`, `CLOSED_STATES` - lines 580-585

#### 7. `src/watercooler/cli.py` - CLI Bootstrap

Create minimal argparse structure:
```python
#!/usr/bin/env python3
"""Watercooler CLI - command-line interface for thread management."""
import argparse
import sys

def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="watercooler",
        description="File-based collaboration for agentic coding"
    )

    # Add subparsers structure (no implementations yet)
    sub = ap.add_subparsers(dest="cmd", required=False)

    # Add command stubs
    sub.add_parser("init-thread", help="Initialize a new thread")
    sub.add_parser("append-entry", help="Append an entry")
    sub.add_parser("say", help="Quick team note")
    sub.add_parser("ack", help="Acknowledge without ball flip")
    sub.add_parser("set-status", help="Update thread status")
    sub.add_parser("set-ball", help="Update ball ownership")
    sub.add_parser("reindex", help="Rebuild index")
    sub.add_parser("list", help="List threads")
    sub.add_parser("web-export", help="Generate HTML index")
    sub.add_parser("search", help="Search threads")

    args = ap.parse_args(argv)

    if not args.cmd:
        ap.print_help()
        sys.exit(0)

    # No-op for L1 - all commands exit 0
    print(f"watercooler {args.cmd}: not yet implemented (L1 stub)")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

#### 8. Update `src/watercooler/__init__.py`

Add imports for public API:
```python
"""Watercooler: File-based collaboration for agentic coding."""

__version__ = "0.0.1"

from .lock import AdvisoryLock
from .fs import read, write, thread_path
from .header import bump_header

__all__ = ["AdvisoryLock", "read", "write", "thread_path", "bump_header", "__version__"]
```

#### 9. Add CLI Entry Point to pyproject.toml

```toml
[project.scripts]
watercooler = "watercooler.cli:main"
```

### Test Fixtures

Create `tests/fixtures/` directory and copy sample threads from acpmonkey:
```bash
mkdir tests/fixtures
cp /Users/jay/projects/acpmonkey/watercooler/watercooler_merge_strategy_thread.md tests/fixtures/
```

Add at least 2-3 representative thread files for testing.

### L1 Tests to Create

#### `tests/test_fs.py`
- Test `read()` and `write()` round-trip
- Test `_backup_file()` creates backups and rotates old ones
- Test `thread_path()` and `lock_path_for_topic()` path generation

#### `tests/test_lock.py`
- Test `AdvisoryLock` acquisition and release
- Test stale lock detection (TTL)
- Test PID tracking
- Test timeout behavior

#### `tests/test_header.py`
- Test `_header_split()` parsing
- Test `_replace_header_line()` with existing and new keys
- Test `bump_header()` updates Status and Ball

#### `tests/test_agents.py`
- Test `_canonical_agent()` name mapping
- Test `_counterpart_of()` ball flip logic
- Test `_split_agent_and_tag()` parsing

#### `tests/test_cli.py`
- Test `watercooler --help` exits 0
- Test `watercooler init-thread` stub exits 0
- Test all command stubs are registered

### L1 Acceptance Criteria

- [ ] All modules extracted with no behavior changes
- [ ] All tests pass
- [ ] `pip install -e .` succeeds
- [ ] `watercooler --help` shows all commands
- [ ] All command stubs exit cleanly with "not yet implemented" message
- [ ] CI passes on Ubuntu + macOS, Python 3.10-3.12
- [ ] No dependencies added (stdlib only)
- [ ] Code coverage >80% for extracted utilities

### L1 Deliverables

- PR #1: Extract fs.py, lock.py, header.py with tests (~150 LOC)
- PR #2: Extract agents.py, templates.py, metadata.py with tests (~120 LOC)
- PR #3: Add CLI stub, entry point, update __init__.py (~80 LOC)

Total: ~350 LOC across 3 PRs, each reviewable independently.

---

## L2 Phase: Command Parity

### Objective
Implement all CLI commands with identical behavior to acpmonkey watercooler.py.

### Commands to Implement

Each command function from watercooler.py:
- `cmd_init()` - lines 384-415
- `cmd_append()` - lines 417-458
- `cmd_say()` - lines 460-508
- `cmd_ack()` - lines 510-556
- `cmd_set_status()` - lines 558-566
- `cmd_set_ball()` - lines 568-576
- `cmd_reindex()` - lines 599-673
- `cmd_list()` - lines 675-687
- `cmd_web_export()` - lines 691-811
- `cmd_search()` - lines 815-842

### New Module: `src/watercooler/config.py`

Create configuration discovery class:
```python
class WatercoolerConfig:
    """Configuration with smart discovery.

    Precedence:
    1. Explicit constructor args
    2. Environment variables (WATERCOOLER_*)
    3. Git root discovery (find .git/, check for watercooler/)
    4. Current directory (./watercooler/)
    5. Create watercooler/ in cwd
    """

    def __init__(
        self,
        threads_dir: str | None = None,
        templates_dir: str | None = None,
        agents_file: str | None = None,
        lock_ttl: int = 300,
        lock_timeout: float = 10.0,
    ):
        self.threads_dir = self._discover_threads_dir(threads_dir)
        self.templates_dir = self._discover_templates_dir(templates_dir)
        self.agents_file = agents_file
        self.lock_ttl = lock_ttl
        self.lock_timeout = lock_timeout

    def _discover_threads_dir(self, explicit: str | None) -> Path:
        # Implementation: check explicit, then env, then git root, then cwd
        ...

    def _discover_templates_dir(self, explicit: str | None) -> Path:
        # Check explicit, env, then project watercooler/, then bundled
        ...
```

### Template Bundling

Copy template files to `src/watercooler/templates/`:
```bash
mkdir -p src/watercooler/templates
cp /Users/jay/projects/acpmonkey/watercooler/_TEMPLATE_topic_thread.md \
   src/watercooler/templates/topic_thread.md
cp /Users/jay/projects/acpmonkey/watercooler/_TEMPLATE_entry_block.md \
   src/watercooler/templates/entry_block.md
```

Update pyproject.toml to include templates as package data:
```toml
[tool.setuptools.package-data]
watercooler = ["py.typed", "templates/*.md"]
```

### L2 Implementation Strategy

Refactor each command function:
1. Replace hardcoded paths with `WatercoolerConfig` discovery
2. Import utilities from extracted modules
3. Keep command logic identical
4. Wire argparse subparsers to command functions

### L2 Tests: Snapshot Parity

Create integration tests that verify output matches acpmonkey:
```python
def test_reindex_parity():
    """Verify reindex output matches acpmonkey behavior."""
    # Use fixture threads
    # Run reindex
    # Compare output to expected snapshot
```

### L2 Acceptance Criteria

- [ ] All commands implemented
- [ ] Snapshot tests pass (output matches acpmonkey)
- [ ] Config discovery works in all precedence scenarios
- [ ] Templates bundled and discoverable
- [ ] No regressions in existing L1 tests
- [ ] CI passes
- [ ] Manual smoke test: can create thread, append, reindex in test project

### L2 Deliverables

- PR #4: Add config.py and bundle templates (~100 LOC)
- PR #5: Implement init, append, say, ack commands (~180 LOC)
- PR #6: Implement set-status, set-ball, list commands (~80 LOC)
- PR #7: Implement reindex command with snapshot test (~150 LOC)
- PR #8: Implement web-export and search (~180 LOC)

---

## L3 Phase: Advanced Features

### Objective
Ensure full feature parity including NEW marker computation, CLOSED filtering, and HTML export options.

### Features to Verify

1. **NEW Marker Logic**
   - Computed when last entry timestamp > last entry by current Ball owner
   - Appears in `_INDEX_OPEN.md` and `index.html`
   - Test with fixture threads that have multiple agents

2. **CLOSED Thread Filtering**
   - Threads with Status: CLOSED, DONE, or ARCHIVED excluded from index
   - Verify `_normalize_status()` handles all variants

3. **HTML Link Behavior**
   - Current: uses `file://` absolute paths
   - Verify clicking links opens threads in editor/viewer
   - Test on both macOS and Ubuntu

### L3 Tests

- Test NEW marker computation with fixture threads
- Test CLOSED filtering in reindex
- Test HTML export structure and links
- Test search with context parameter

### L3 Acceptance Criteria

- [ ] NEW markers appear correctly
- [ ] CLOSED threads excluded from indexes
- [ ] HTML export works and links are functional
- [ ] Search returns correct results with context
- [ ] All edge cases from acpmonkey tests pass

### L3 Deliverables

- PR #9: Add comprehensive integration tests (~100 LOC)
- PR #10: Fix any edge cases discovered in testing (~50 LOC)

---

## L4 Phase: Documentation + Publication

### Objective
Polish documentation and publish to PyPI as version 0.1.0.

### Documentation to Create

#### `docs/api.md`
- Document `WatercoolerConfig` class
- Document public functions: `read()`, `write()`, `thread_path()`, `bump_header()`
- Document `AdvisoryLock` context manager

#### `docs/integration.md`
Tutorial covering:
1. Installation: `pip install watercooler-collab`
2. Quick start: init thread, say, reindex
3. Configuration options (env vars, discovery)
4. Template customization

#### `docs/migration.md`
For acpmonkey users:
1. Update requirements.txt to add `watercooler-collab`
2. Remove old `watercooler.py`
3. Update tools/ wrappers to call `watercooler` command
4. Verify no behavior changes

### PyPI Publication Steps

1. **Test on TestPyPI**
   ```bash
   python -m build
   twine upload --repository testpypi dist/*
   pip install --index-url https://test.pypi.org/simple/ watercooler-collab
   # Verify installation works
   ```

2. **Publish to PyPI**
   ```bash
   twine upload dist/*
   ```

3. **Tag Release**
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

### L4 Acceptance Criteria

- [ ] All documentation complete and reviewed
- [ ] Published to TestPyPI successfully
- [ ] Test installation from TestPyPI works
- [ ] Published to PyPI
- [ ] GitHub release created with v0.1.0 tag
- [ ] README updated with installation instructions

### L4 Deliverables

- PR #11: Add API documentation (~150 LOC)
- PR #12: Add integration and migration guides (~200 LOC)
- Release: v0.1.0 to PyPI

---

## Testing Strategy

### Unit Tests (L1-L2)
- Test each extracted function in isolation
- Mock file system operations where appropriate
- Use pytest fixtures for common setup

### Integration Tests (L2-L3)
- Use real fixture threads from acpmonkey
- Verify command outputs match expected behavior
- Snapshot testing for reindex and web-export

### Manual Validation (L3-L4)
- Install in fresh test project
- Run through complete workflow: init → say → reindex → web-export
- Verify on both macOS and Ubuntu
- Test in acpmonkey with library installed

---

## Migration Path for acpmonkey

After L4 completion:

1. **Add dependency** to `requirements.txt`:
   ```
   watercooler-collab>=0.1.0
   ```

2. **Remove old code**:
   ```bash
   git rm watercooler.py
   ```

3. **Update shell wrappers** in `tools/`:
   ```bash
   # Old: python3 watercooler.py say ...
   # New: watercooler say ...
   sed -i 's/python3 watercooler.py/watercooler/' tools/watercooler-*
   ```

4. **Update CLAUDE.md**:
   - Remove references to `python3 watercooler.py`
   - Add note about `watercooler` command from package
   - Update examples

5. **Verify**:
   ```bash
   pytest  # All tests pass
   watercooler list --status OPEN  # Works
   ```

6. **Commit**:
   ```bash
   git commit -m "Migrate to watercooler-collab package"
   ```

---

## Key Constraints

1. **Stdlib only** - No external dependencies beyond dev tools (pytest, mypy)
2. **CLI parity** - All flags and behavior must match exactly
3. **Small PRs** - Target ≤200 LOC per PR for reviewability
4. **Test coverage** - Maintain >80% coverage throughout
5. **Cross-platform** - Test on Ubuntu + macOS in CI
6. **Backward compatibility** - acpmonkey must work unchanged after migration

---

## Questions or Issues?

If you encounter ambiguity during implementation:
1. Check the source: `/Users/jay/projects/acpmonkey/watercooler.py`
2. Check existing tests: `/Users/jay/projects/acpmonkey/tests/test_watercooler*.py`
3. Ask in watercooler thread: `watercooler_library_extraction.md`

When a phase is complete, update the README.md checkbox for that phase.
