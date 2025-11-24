# Watercooler Git Configuration

This guide explains the git configuration required for multi-user watercooler collaboration.

## Required: Git Merge Driver Setup

The `.gitattributes` file references a custom merge driver (`merge=ours`) that must be configured in your local Git environment.

### One-Time Setup

Run this command in your repository:

```bash
git config merge.ours.driver true
```

This configures Git to use the "ours" merge strategy for files marked with `merge=ours` in `.gitattributes`.

### What This Does

The watercooler collaboration protocol uses two different merge strategies:

#### 1. `merge=union` for Thread Files

- **Pattern**: `.watercooler/*.md` and `watercooler/*.md`
- **Behavior**: Preserves entries from both branches by appending them
- **Why it works**: Watercooler protocol enforces append-only entries
  - Agents never modify existing entries
  - Headers (Status/Ball) are updated in-place, but conflicts are rare
  - When conflicts occur, `merge=union` preserves all entries from both sides
- **Built-in**: No configuration needed - `merge=union` is a Git built-in

#### 2. `merge=ours` for Index Files

- **Pattern**: `.watercooler/index.md` and `watercooler/index.md`
- **Behavior**: Always keeps the current branch's version during merge
- **Why it works**: The index file is **regenerated** after every change
  - Using `merge=ours` keeps the feature branch version during merge
  - Run `watercooler reindex` after merging to regenerate with latest data
  - This treats the index as a generated file
- **Requires**: One-time `git config merge.ours.driver true` setup

### Verification

Check if the driver is configured:

```bash
git config --get merge.ours.driver
```

Expected output: `true`

### GitHub Server-Side Merges

GitHub's merge infrastructure honors built-in merge drivers. The `merge=ours` driver is a no-op driver that simply returns success, which GitHub supports.

After server-side merges to main, regenerate the index:

```bash
watercooler reindex
```

## Required: Pre-commit Hook Setup

**CRITICAL FOR TEAM COLLABORATION**: The pre-commit hook enforces the append-only protocol and prevents data corruption during team merges. While the MCP server automatically installs hooks in threads repositories, you should also configure hooks in your code repositories.

### Installation

```bash
git config core.hooksPath .githooks
```

### Why Hooks Are Required

Without the pre-commit hook, manual edits to thread files can violate the append-only protocol:

- **Scenario**: Developer manually edits `project-threads/feature-auth.md` in vim
- **Problem**: Modifies existing entry body (violates append-only)
- **Result**: Later merge with another developer's changes corrupts thread
- **Solution**: Hook blocks the commit and suggests using CLI commands

### What the Hook Does

The pre-commit hook in `.githooks/pre-commit` validates that commits follow the watercooler protocol:

- **Enforces append-only**: Existing entries cannot be modified
- **Allows header updates**: Status, Ball, and Updated fields can change
- **Prevents corruption**: Blocks commits that violate the protocol
- **Clear errors**: Provides actionable error messages with CLI hints

If you accidentally modify an existing entry, the hook will block the commit and suggest using the CLI commands instead:

```bash
# Use CLI commands to update threads safely
watercooler set-status topic in-review
watercooler set-ball topic codex
watercooler append-entry topic --agent Claude --title "Update" --body "..."
```

### Bypassing the Hook (Not Recommended)

If you need to temporarily bypass the hook:

```bash
git commit --no-verify
```

**Warning**: Only bypass the hook if you're certain your changes are safe!

## Why This Works

### Append-Only Protocol

The watercooler protocol is designed for safe concurrent collaboration:

1. **Thread files** (`.watercooler/*.md`):
   - Entries are only appended, never modified
   - Headers have minimal update frequency
   - `merge=union` preserves all concurrent entries

2. **Index files** (`.watercooler/index.md`):
   - Generated from thread files
   - Can be regenerated at any time
   - `merge=ours` avoids conflicts, regenerate after merge

3. **Pre-commit hook**:
   - Validates append-only constraint locally
   - Catches accidental modifications before they reach remote
   - Maintains data integrity across the team

### Collaboration Workflow

```bash
# Developer A (East Coast)
watercooler say feature-auth --title "Design Complete" --body "JWT approach approved"
git add .watercooler/feature-auth.md
git commit -m "watercooler: design approval"
git push

# Developer B (West Coast) - working in parallel
watercooler say feature-auth --title "Tests Written" --body "Coverage at 95%"
git add .watercooler/feature-auth.md
git commit -m "watercooler: test coverage"
git pull  # merge=union combines both entries automatically
git push
```

Both entries are preserved! No manual conflict resolution needed.

## Troubleshooting

### Merge conflicts still occur

Even with `merge=union`, you may see conflicts if:
- Both developers modified the same header fields (Status/Ball/Updated)
- Solution: Accept either version, then run `watercooler reindex`

### Pre-commit hook blocks valid changes

If the hook incorrectly blocks a commit:
1. Verify your changes are truly append-only
2. Check that you're only modifying Status/Ball/Updated headers
3. If stuck, use `watercooler unlock topic --force` to clear locks
4. Report the issue at https://github.com/mostlyharmless-ai/watercooler-cloud/issues

### Hook not running

If the pre-commit hook doesn't run:
```bash
# Check hook configuration
git config --get core.hooksPath

# Should output: .githooks

# If not set, configure it:
git config core.hooksPath .githooks

# Make hook executable (Unix/Mac)
chmod +x .githooks/pre-commit
```

## See Also

- [README.md](../README.md) - Installation and usage
- [MIGRATION.md](../docs/MIGRATION.md) - Migration from acpmonkey
- [STRUCTURED_ENTRIES.md](../docs/STRUCTURED_ENTRIES.md) - Entry format guide
