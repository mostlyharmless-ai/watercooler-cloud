# Project Status: watercooler-collab

**Last Updated:** 2025-10-06
**Current Phase:** L4 Prep (Documentation & Publication)
**Repository:** https://github.com/mostlyharmless-ai/watercooler-collab

## Quick Summary

Watercooler-collab is a stdlib-only Python library extracted from acpmonkey's watercooler.py. The library provides file-based collaboration threads for agentic coding projects with CLI parity to the original implementation.

**Current Status:** L1, L2, and L3 complete. Ready for L4 (docs + publication)

## Completed Work

### L0: Repository Scaffolding ✓
- Commit: 11caecb
- Basic package structure, CI, README

### L1: Core Utilities ✓
- Commit: 7102608
- Modules: fs.py, lock.py, header.py, agents.py, metadata.py, templates.py
- All core functionality extracted from acpmonkey watercooler.py

### L2: Command Parity ✓
- Commit: 7102608
- All 11 CLI commands implemented: init-thread, append-entry, say, ack, handoff, set-status, set-ball, list, reindex, search, web-export
- Config discovery: CLI flag > WATERCOOLER_DIR env > ./watercooler default
- CLI entry point: `watercooler` command

### L3: Advanced Features ✓
- Commit: 7102608 + recent updates
- reindex: Markdown table output with NEW markers
- search: Case-insensitive with line numbers
- web-export: Static HTML with styled table and NEW badges
- NEW marker logic: Compares last entry author vs ball owner
- CLOSED filtering: Excludes closed/done/merged/resolved threads from indexes
- handoff command: Automatic ball flipping to counterpart agent
- Templates bundled: _TEMPLATE_topic_thread.md, _TEMPLATE_entry_block.md

## Test Status

- **Total Tests:** 25
- **Status:** All passing
- **Coverage:** Core modules covered, including handoff command
- **CI:** Passing on Ubuntu + macOS, Python 3.9-3.12

## Remaining Work

### Pre-L4 Polishing

**CLI Flag Parity Audit**
- **What:** Verify all flags match acpmonkey watercooler.py exactly
- **Check:**
  - Flag names (--status vs --set-status, etc.)
  - Default values
  - Required vs optional flags
  - Help text consistency
- **Reference:** Compare `src/watercooler/cli.py` with acpmonkey watercooler.py lines 847-938

### L4: Documentation + Publication

**1. API Documentation (`docs/api.md`)**
- Document `WatercoolerConfig` class (when implemented)
- Document public functions: `read()`, `write()`, `thread_path()`, `bump_header()`
- Document `AdvisoryLock` context manager
- Include code examples

**2. Integration Guide (`docs/integration.md`)**
- Quick start: `pip install watercooler-collab`
- Initialize thread, say, ack, reindex workflow
- Configuration options (env vars, CLI flags)
- Template customization (when bundled)

**3. Migration Guide (`docs/migration.md`)**
- For acpmonkey users
- Step-by-step: requirements.txt, remove watercooler.py, update tools/
- Behavior differences (if any)
- Rollback plan

**4. PyPI Publication**
- Build: `python -m build`
- TestPyPI: `twine upload --repository testpypi dist/*`
- Test install: `pip install --index-url https://test.pypi.org/simple/ watercooler-collab`
- Production: `twine upload dist/*`
- Tag release: `git tag v0.1.0 && git push origin v0.1.0`

**5. Update README**
- Installation from PyPI
- Remove "not yet published" notices
- Link to docs

## Known Gaps

### Not Yet Implemented

1. **WatercoolerConfig Class**
   - Currently have `resolve_threads_dir()` helper only
   - Original plan called for full config class with multiple path types
   - Current implementation is simpler and works

2. **Shell Wrapper Generator**
   - Original plan: `watercooler generate-wrappers` command
   - Not critical - users can write their own or copy from acpmonkey

3. **Agent Registry JSON File**
   - acpmonkey has agent registry support via `--agents-file`
   - Not implemented in library yet
   - May not be needed for v0.1.0

## Source References

**Primary Source:** `/Users/jay/projects/acpmonkey/watercooler.py` (~950 lines)

**Key Line References:**
- Advisory locking: lines 89-186
- File ops: lines 47-87
- Header ops: lines 219-253
- Agent registry: lines 270-356
- Commands: lines 382-842
- Reindex with NEW: lines 599-673

**Watercooler Thread:** `/Users/jay/projects/acpmonkey/watercooler/watercooler_library_extraction.md`

**Implementation Plan:** `/Users/jay/projects/watercooler-collab/IMPLEMENTATION_PLAN.md`

## Design Constraints

1. **Stdlib only** - No external dependencies except dev tools
2. **CLI parity** - All flags and behavior must match acpmonkey
3. **Small commits** - Target ≤200 LOC per commit when practical
4. **Cross-platform** - Test on Ubuntu + macOS
5. **Backward compatible** - acpmonkey must work unchanged after migration

## Next Session Recommendations

**Current Status: L3 Complete!**

**Immediate Next Steps:**
1. CLI flag parity audit against acpmonkey (verify exact match)
2. Start L4 Documentation:
   - Create docs/api.md
   - Create docs/integration.md
   - Create docs/migration.md
3. Test manual installation in fresh project
4. Prepare for PyPI publication

**Recommended Path:** CLI audit → L4 docs → Test install → Publish v0.1.0

## Testing Checklist Before Publication

- [x] All 25 tests pass
- [ ] CI green on all platforms
- [ ] Manual test: init → say → reindex → web-export workflow
- [ ] Manual test: Install in fresh project and run commands
- [ ] Manual test: acpmonkey integration (vendor library locally)
- [x] NEW marker appears correctly in indexes
- [x] CLOSED threads excluded from indexes
- [ ] All CLI flags work as documented
- [x] Templates bundled and accessible
- [ ] README accurate and complete

## Collaboration Context

**Participants:**
- Jay (human, project owner)
- Claude (AI assistant, implementation)
- Codex (AI assistant, primary implementer for L1-L3)

**Watercooler Protocol:**
- Status: OPEN
- Ball: Codex (as of last update)
- Thread: watercooler_library_extraction.md in acpmonkey repo

**Decision History:**
- L-series phased approach approved
- Stdlib-only constraint maintained
- Repository: mostlyharmless-ai/watercooler-collab
- Package name: watercooler-collab (PyPI)
- Internal module: watercooler (for import ergonomics)

## Quick Commands

```bash
# Run tests
pytest tests/ -v

# Install locally
pip install -e .

# Use CLI
watercooler --help
watercooler init-thread test_topic --threads-dir ./test_watercooler

# Check what's uncommitted
git status

# View recent commits
git log --oneline -5

# Run CI locally
pytest tests/ && echo "Tests pass"
```

## Files of Interest

- `src/watercooler/commands.py` - Where to add NEW marker and CLOSED filtering
- `src/watercooler/cli.py` - CLI argument parsing
- `src/watercooler/config.py` - Path discovery logic
- `tests/test_cli_reindex_search.py` - Test reindex behavior
- `IMPLEMENTATION_PLAN.md` - Detailed L1-L4 roadmap
- `README.md` - User-facing documentation

## Environment

- Python: 3.9-3.12 supported
- Conda env: acpmonkey (when working in acpmonkey repo)
- Git: Required for agent name discovery (`_get_git_user()`)
- CI: GitHub Actions on push/PR
