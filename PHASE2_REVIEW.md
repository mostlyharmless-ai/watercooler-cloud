# Phase 2 Implementation Review

**Date:** 2025-10-06
**Phase:** Command Implementation - Structured Entries and Templates
**Status:** ✅ Complete, Ready for Test Updates

---

## Summary

Phase 2 implements full CLI parity with acpmonkey by updating all command functions and CLI handlers to support structured entries, template loading, and agent registry customization. These changes enable rich collaboration metadata while maintaining backward compatibility through fallback logic.

---

## Files Modified

### 1. `src/watercooler/commands.py` (Updated: init_thread, append_entry, say, ack, handoff)

#### `init_thread()` - Template Support
**Changes:**
- Added `owner: str | None = None` parameter
- Added `participants: str | None = None` parameter
- Added `templates_dir: Path | None = None` parameter
- Loads `_TEMPLATE_topic_thread.md` via `load_template()`
- Fills template with `TOPIC`, `OWNER`, `PARTICIPANTS`, `UTC`, `BALL`
- Falls back to simple format if template not found

**Example:**
```python
init_thread(
    "feature-auth",
    threads_dir=Path("watercooler"),
    owner="Jay",
    participants="Jay, Claude, Codex",
    templates_dir=Path("custom-templates")
)
# Uses custom template with owner/participants metadata
```

---

#### `append_entry()` - COMPLETE REWRITE
**Before (Phase 1):**
```python
def append_entry(topic, *, threads_dir, author, body, bump_status=None, bump_ball=None):
    # Simple entry with just timestamp and body
```

**After (Phase 2):**
```python
def append_entry(
    topic: str,
    *,
    threads_dir: Path,
    agent: str,              # CHANGED from author
    role: str,               # NEW (required)
    title: str,              # NEW (required)
    entry_type: str = "Note",  # NEW
    body: str,
    status: str | None = None,  # Renamed from bump_status
    ball: str | None = None,    # Auto-flips if None
    templates_dir: Path | None = None,  # NEW
    registry: dict | None = None,       # NEW
) -> Path:
```

**Features:**
- Loads `_TEMPLATE_entry_block.md` template
- Canonicalizes agent name with auto user tagging
- Fills template with `UTC`, `AGENT`, `TYPE`, `ROLE`, `TITLE`, `BODY`
- Auto-flips ball to counterpart if not explicitly provided
- Falls back to simple format if template not found
- Updates thread header with new status/ball

**Example Entry Output:**
```markdown
---

**2025-10-06T22:00:00Z** | **Claude (jay)** | **critic** | **Decision**

### Approve Phase 2 Implementation

All commands now support structured entries with role-based attribution.
Ready to proceed with test updates in Phase 3.
```

---

#### `say()` - Convenience Wrapper with Auto-Flip
**Changes:**
- Changed `author` → `agent` (optional, defaults to Team)
- Added `role` parameter (optional, defaults from registry)
- Added `title` parameter (required)
- Added `entry_type` parameter (default: "Note")
- Added `status`, `ball`, `templates_dir`, `registry` parameters
- **Auto-flips ball** via `append_entry()` if ball not provided

**Example:**
```python
say(
    "feature-auth",
    threads_dir=Path("watercooler"),
    title="Authentication complete",
    body="Implemented OAuth2 flow with refresh tokens",
    # Ball auto-flips from current owner to counterpart
)
```

---

#### `ack()` - Acknowledge Without Ball Flip
**Changes:**
- Changed `author` → `agent` (optional, defaults to Team)
- Added `role` parameter (optional, defaults from registry)
- Changed `note` → `body` (optional, defaults to "ack")
- Added `title` parameter (optional, defaults to "Ack")
- Added `entry_type`, `status`, `ball`, `templates_dir`, `registry` parameters
- **Does NOT auto-flip ball** - only changes if explicitly provided

**Example:**
```python
ack(
    "feature-auth",
    threads_dir=Path("watercooler"),
    body="Reviewed, looks good"
    # Ball stays with current owner
)
```

---

#### `handoff()` - Multi-Agent Handoff with Structured Entry
**Before:**
```python
def handoff(topic, *, threads_dir, author=None, note=None, registry=None):
    # Used old append_entry signature
    return append_entry(..., author=author, bump_ball=target)
```

**After:**
```python
def handoff(
    topic: str,
    *,
    threads_dir: Path,
    agent: str | None = None,        # CHANGED from author
    role: str = "pm",                # NEW (default: project management)
    note: str | None = None,
    registry: dict | None = None,
    templates_dir: Path | None = None,  # NEW
) -> Path:
```

**Features:**
- Uses `thread_meta()` to get current ball
- Determines target via `_counterpart_of()`
- Creates structured handoff entry with role="pm"
- Title: "Handoff to {target}"
- Explicitly sets ball to target (no auto-flip needed)

**Example:**
```python
handoff(
    "feature-auth",
    threads_dir=Path("watercooler"),
    note="OAuth implementation ready for review"
)
# Creates: "Handoff to Claude (jay)" entry, sets ball to Claude
```

---

### 2. `src/watercooler/cli.py` (Updated: All command parsers and handlers)

#### Argument Parser Updates

**init-thread:**
```bash
watercooler init-thread <topic> \
  [--owner OWNER] \
  [--participants PARTICIPANTS] \
  [--templates-dir TEMPLATES_DIR] \
  # ... existing args
```

**append-entry:** (BREAKING CHANGES)
```bash
# Before:
--author AUTHOR --body BODY [--bump-status STATUS] [--bump-ball BALL]

# After:
--agent AGENT --role ROLE --title TITLE \
  [--type TYPE] --body BODY \
  [--status STATUS] [--ball BALL] \
  [--templates-dir TEMPLATES_DIR] \
  [--agents-file AGENTS_FILE]
```

**say:** (BREAKING CHANGES)
```bash
# Before:
--author AUTHOR --body BODY

# After:
--agent AGENT --role ROLE --title TITLE \
  [--type TYPE] --body BODY \
  [--status STATUS] [--ball BALL] \
  [--templates-dir TEMPLATES_DIR] \
  [--agents-file AGENTS_FILE]
```

**ack:** (BREAKING CHANGES)
```bash
# Before:
--author AUTHOR [--note NOTE]

# After:
--agent AGENT --role ROLE [--title TITLE] \
  [--type TYPE] [--body BODY] \
  [--status STATUS] [--ball BALL] \
  [--templates-dir TEMPLATES_DIR] \
  [--agents-file AGENTS_FILE]
```

**handoff:** (BREAKING CHANGES)
```bash
# Before:
--author AUTHOR [--note NOTE]

# After:
--agent AGENT [--role ROLE] [--note NOTE] \
  [--templates-dir TEMPLATES_DIR] \
  [--agents-file AGENTS_FILE]
```

---

#### CLI Handler Updates

All command handlers now:
1. Import `resolve_templates_dir`, `_load_agents_registry` as needed
2. Load agent registry if `--agents-file` provided
3. Resolve templates directory if `--templates-dir` provided
4. Pass new parameters to command functions

**Example (say command):**
```python
if args.cmd == "say":
    body = read_body(args.body)
    registry = _load_agents_registry(args.agents_file) if args.agents_file else None
    out = say(
        args.topic,
        threads_dir=resolve_threads_dir(args.threads_dir),
        agent=args.agent,
        role=args.role,
        title=args.title,
        entry_type=args.entry_type,
        body=body,
        status=args.status,
        ball=args.ball,
        templates_dir=resolve_templates_dir(args.templates_dir) if args.templates_dir else None,
        registry=registry,
    )
```

---

## Test Impact

### ❌ Expected Test Failures (10 tests)

All failures are due to **intentional breaking changes** in CLI signatures:

1. **test_split_and_canonical** - Agent format changed from `#tag` to `(user)`
2. **test_counterpart_and_default** - Counterpart now returns tagged format
3. **test_all_commands_exist_and_exit_zero** - append-entry requires new args
4. **test_handoff_flips_ball** - handoff signature changed
5. **test_init_thread_creates_file** - Template format differs from simple format
6. **test_init_thread_respects_overrides_and_body** - Template format differs
7. **test_reindex_and_search** - Entry format changed (includes metadata)
8. **test_say_and_ack** - say requires `--title`, ack has different args
9. **test_handoff** - handoff uses `--agent` not `--author`
10. **test_append_entry** - append-entry requires `--agent`, `--role`, `--title`

### ✅ Passing Tests (15 tests)

Core infrastructure still works:
- File operations (read, write, backup)
- Header parsing and updates
- Advisory locking
- Path resolution
- Import/version checks
- set-status, set-ball (unchanged)
- list command (unchanged)
- web-export (unchanged)

---

## Breaking Changes Summary

### Command Function Signatures

| Function | Old Parameter | New Parameter | Required? |
|----------|---------------|---------------|-----------|
| `init_thread` | - | `owner` | Optional |
| `init_thread` | - | `participants` | Optional |
| `init_thread` | - | `templates_dir` | Optional |
| `append_entry` | `author` | `agent` | **Required** |
| `append_entry` | - | `role` | **Required** |
| `append_entry` | - | `title` | **Required** |
| `append_entry` | - | `entry_type` | Optional (default: "Note") |
| `append_entry` | `bump_status` | `status` | Optional |
| `append_entry` | `bump_ball` | `ball` | Optional (auto-flips) |
| `append_entry` | - | `templates_dir` | Optional |
| `append_entry` | - | `registry` | Optional |
| `say` | `author` | `agent` | Optional |
| `say` | - | `role` | Optional |
| `say` | - | `title` | **Required** |
| `say` | - | `entry_type` | Optional |
| `say` | - | `status`, `ball` | Optional |
| `say` | - | `templates_dir`, `registry` | Optional |
| `ack` | `author` | `agent` | Optional |
| `ack` | `note` | `body` | Optional |
| `ack` | - | `role`, `title` | Optional |
| `ack` | - | `entry_type`, `status`, `ball` | Optional |
| `ack` | - | `templates_dir`, `registry` | Optional |
| `handoff` | `author` | `agent` | Optional |
| `handoff` | - | `role` | Optional (default: "pm") |
| `handoff` | - | `templates_dir`, `registry` | Optional |

### CLI Argument Changes

| Command | Old Args | New Args | Notes |
|---------|----------|----------|-------|
| `append-entry` | `--author --body --bump-status --bump-ball` | `--agent --role --title --type --body --status --ball --templates-dir --agents-file` | **BREAKING** |
| `say` | `--author --body` | `--agent --role --title --type --body --status --ball --templates-dir --agents-file` | **BREAKING** (`--title` required) |
| `ack` | `--author --note` | `--agent --role --title --type --body --status --ball --templates-dir --agents-file` | **BREAKING** (`--note` → `--body`) |
| `handoff` | `--author --note` | `--agent --role --note --templates-dir --agents-file` | **BREAKING** (`--author` → `--agent`) |
| `init-thread` | (existing) | Added: `--owner --participants --templates-dir` | **Backward compatible** |

---

## Backward Compatibility

### ✅ Maintained
- Simple format fallback if templates not found
- All existing commands still work (set-status, set-ball, list, reindex, search, web-export)
- File operations unchanged
- Locking mechanism unchanged
- Header operations unchanged

### ❌ Broken (Intentional)
- CLI signatures for: append-entry, say, ack, handoff
- Function signatures for same commands
- Entry format (now structured with metadata)
- Agent format (now includes user tag)

---

## Integration with Phase 1

Phase 2 successfully uses all Phase 1 infrastructure:

✅ **Template Loading**
```python
template = load_template("_TEMPLATE_entry_block.md", templates_dir)
```

✅ **Template Filling**
```python
entry = _fill_template(template, {
    "AGENT": "Claude (jay)",
    "ROLE": "critic",
    "TYPE": "Decision",
    "TITLE": "Approve Phase 2",
    "BODY": "Looks good!"
})
```

✅ **Agent Canonicalization**
```python
agent = _canonical_agent("claude", registry)  # → "Claude (jay)"
```

✅ **Counterpart Resolution**
```python
next_ball = _counterpart_of("Codex (jay)", registry)  # → "Claude (jay)"
```

✅ **Role/Type Validation** (implicitly via CLI choices)

---

## Next Steps (Phase 3)

### Phase 3.1: Update Tests
Update all failing tests to use new signatures:
- `test_split_and_canonical` - Expect `(user)` format
- `test_counterpart_and_default` - Expect tagged returns
- `test_all_commands_exist_and_exit_zero` - Add required args
- `test_handoff_flips_ball` - Use new handoff signature
- `test_init_thread_*` - Expect template format
- `test_say_and_ack` - Add `--title` arg
- `test_append_entry` - Add `--agent --role --title`

### Phase 3.2: Add New Tests
- Template loading and filling
- Agent registry loading and merging
- Counterpart chain resolution with cycles
- Structured entry format validation
- Ball auto-flip vs explicit set
- User tagging behavior

### Phase 3.3: Update Documentation
- README: New command examples
- STATUS.md: Phase 2 complete
- New guides: Agent registry, templates customization
- CLI reference: Updated command signatures

---

## Commit Message Preview

```
feat(commands): Phase 2 - Full CLI parity with structured entries

Implement complete acpmonkey CLI compatibility with structured collaboration:

**Commands (commands.py)**
- init_thread: Add owner, participants, templates support
- append_entry: COMPLETE REWRITE for structured entries
  - Changed: author → agent (with auto-tagging)
  - Added: role (required), title (required), entry_type
  - Added: templates_dir, registry parameters
  - Auto-flip ball to counterpart if not provided
  - Load/fill _TEMPLATE_entry_block.md template
- say: Wrapper for append_entry with auto-flip
  - Requires --title, auto-flips ball if not provided
- ack: Like say but NO auto-flip
  - Changed: --note → --body
  - Ball only changes if explicitly provided
- handoff: Updated for structured entries
  - Changed: author → agent
  - Creates role="pm" entry with explicit ball set

**CLI (cli.py)**
- Updated ALL command parsers with new arguments
- Added: --agent, --role, --title, --type, --templates-dir, --agents-file
- Removed: --author, --bump-status, --bump-ball
- All handlers now load registry and resolve templates directory

**Breaking Changes:**
- CLI: append-entry, say, ack, handoff require new arguments
- Functions: Signatures changed for same commands
- Entry format: Now includes Agent, Role, Type, Title metadata
- Ball behavior: Auto-flips in append_entry/say, not in ack

**Test Impact:**
- 15 tests passing (core functionality intact)
- 10 tests failing (expected - signatures changed)
- Tests will be updated in Phase 3

**Integration:**
- Successfully uses Phase 1 template system
- Successfully uses Phase 1 agent registry
- Successfully uses Phase 1 constants (ROLE_CHOICES, ENTRY_TYPES)

Next: Phase 3 - Update tests and documentation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Review Checklist

- [x] All Phase 2 command updates completed
- [x] CLI argument parsers updated
- [x] CLI handlers updated
- [x] Auto-flip ball logic in append_entry/say
- [x] No auto-flip in ack
- [x] handoff uses new signature
- [x] Fallback logic for missing templates
- [x] Breaking changes documented
- [x] Test failures expected and documented
- [x] Integration with Phase 1 verified

**Status:** ✅ Ready for Phase 3 (test updates)
