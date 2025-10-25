# Frequently Asked Questions

Common questions about watercooler-collab and troubleshooting tips.

## Table of Contents

- [General Questions](#general-questions)
- [Commands and Usage](#commands-and-usage)
- [Ball and Handoffs](#ball-and-handoffs)
- [Agents and Roles](#agents-and-roles)
- [Git Collaboration](#git-collaboration)
- [Troubleshooting](#troubleshooting)

---

## General Questions

### What is watercooler-collab?

Watercooler is a file-based collaboration protocol for coordinating work between humans and AI agents. It uses markdown thread files with Status/Ball tracking to manage who owns the next action.

### Why use watercooler instead of just git commits or GitHub issues?

- **Structured coordination**: Explicit Status and Ball tracking
- **Multi-agent workflows**: Role-based agent specialization
- **Persistent context**: Thread history for LLM extended context
- **Append-only safety**: Safe concurrent collaboration with git merge strategies
- **Lightweight**: No server, database, or external dependencies

### Should threads be in .gitignore?

**No!** Unlike `.git`, watercooler threads are meant to be versioned and shared. They enable cross-timezone collaboration by allowing team members to pull updates and see what happened while they were offline.

### What's the difference between watercooler-collab and acpmonkey?

Watercooler-collab is a clean-room reimplementation with:
- Stdlib-only (no external dependencies)
- Full test coverage (52 passing tests)
- Enhanced features (structured entries, agent registry, templates)
- Modern CLI patterns
- Comprehensive documentation

See [MIGRATION.md](MIGRATION.md) for migration guide.

---

## Commands and Usage

### When should I use `say` vs `ack` vs `handoff`?

- **`say`**: Standard work update that auto-flips ball to counterpart
  ```bash
  watercooler say topic --title "Done" --body "Completed feature"
  # Ball automatically flips to counterpart
  ```

- **`ack`**: Acknowledge without changing ball owner
  ```bash
  watercooler ack topic --title "Got it"
  # Ball stays with current owner
  ```

- **`handoff`**: Explicit handoff to specific agent (not counterpart)
  ```bash
  watercooler handoff topic --note "Passing to reviewer"
  # Ball explicitly set to target agent
  ```

### How do I reference a file in `--body`?

Use `@filename` syntax:

```bash
watercooler say topic \
  --title "Design Complete" \
  --body @design-doc.md
```

This reads the file contents and uses them as the entry body.

### Can I have multi-line body text without a file?

Yes, use shell heredoc:

```bash
watercooler say topic \
  --title "Summary" \
  --body "$(cat <<'EOF'
Line 1
Line 2
Line 3
EOF
)"
```

### How do I search across all threads?

```bash
watercooler search "keyword"
# Returns: file:line: matching text

# Examples:
watercooler search "authentication"
watercooler search "Decision"
watercooler search "Claude"
```

### What does the NEW marker mean?

NEW appears when the last entry author differs from the current ball owner:

```bash
$ watercooler list
2025-10-07T12:00:00Z  open  alice  NEW  Feature  feature.md
```

This means:
- Ball is currently with: `alice`
- Last entry was from: someone else (not alice)
- Action required: alice needs to respond

---

## Ball and Handoffs

### How does ball auto-flip work?

When using `say` command, ball automatically flips to the counterpart defined in the agent registry:

```json
{
  "agents": {
    "claude": {"counterpart": "codex"},
    "codex": {"counterpart": "claude"},
    "team": {"counterpart": "claude"}
  }
}
```

```bash
# Ball is with: codex
watercooler say topic --agent codex --title "Done"
# Ball auto-flips to: claude (codex's counterpart)
```

### Can I override auto-flip?

Yes, use explicit `--ball` argument:

```bash
watercooler say topic \
  --agent codex \
  --title "Done" \
  --ball team
# Ball explicitly set to: team (not counterpart)
```

### How do I set up counterpart mappings?

Create `agents.json`:

```json
{
  "agents": {
    "agent1": {"counterpart": "agent2"},
    "agent2": {"counterpart": "agent1"}
  }
}
```

Use with commands:

```bash
watercooler say topic --agents-file ./agents.json --agent agent1
```

Or set environment variable:

```bash
export WATERCOOLER_AGENTS=./agents.json
watercooler say topic --agent agent1
```

See [AGENT_REGISTRY.md](AGENT_REGISTRY.md) for details.

### Can I create a multi-agent chain?

Yes! Chain counterparts:

```json
{
  "agents": {
    "planner": {"counterpart": "implementer"},
    "implementer": {"counterpart": "reviewer"},
    "reviewer": {"counterpart": "planner"}
  }
}
```

Ball cycles: planner → implementer → reviewer → planner → ...

---

## Agents and Roles

### What are the 6 agent roles?

1. **planner** - Architecture and design decisions
2. **critic** - Code review and quality assessment
3. **implementer** - Feature implementation
4. **tester** - Test coverage and validation
5. **pm** - Project management and coordination
6. **scribe** - Documentation and notes

See [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md) for details.

### Can I have multiple agents with the same role?

Yes! Roles are not unique. You can have:
- `Claude` as `critic`
- `SecurityBot` as `critic`
- `PerformanceBot` as `critic`

Each provides different perspective on review.

### What are the 5 entry types?

1. **Note** - General observations and updates
2. **Plan** - Design proposals and roadmaps
3. **Decision** - Architectural or technical decisions
4. **PR** - Pull request related entries
5. **Closure** - Thread conclusion and summary

### Do I need to specify role and type every time?

Role is required. Type defaults to `Note` if not specified:

```bash
# Minimal (type defaults to Note)
watercooler say topic --agent Claude --role planner --title "Update"

# Explicit type
watercooler say topic --agent Claude --role planner --title "Design" --type Plan
```

### How are agent names formatted?

Agent names are automatically tagged with user:

```bash
watercooler say topic --agent Claude --title "Update"
# Stored as: Claude (agent)
```

User is determined by:
1. `$WATERCOOLER_USER` environment variable
2. System username (getpass.getuser())
3. "unknown" if neither available

---

## Git Collaboration

### What git configuration is required?

Two commands (one-time setup):

```bash
# Required: Enable "ours" merge driver
git config merge.ours.driver true

# Recommended: Enable pre-commit hook
git config core.hooksPath .githooks
```

See [.github/WATERCOOLER_SETUP.md](../.github/WATERCOOLER_SETUP.md) for details.

### How do merge strategies work?

Watercooler uses two different strategies:

1. **Thread files** (`.watercooler/*.md`): `merge=union`
   - Appends entries from both branches
   - Works because protocol is append-only
   - No manual conflict resolution needed

2. **Index files** (`.watercooler/index.md`): `merge=ours`
   - Keeps current branch's version
   - Regenerate after merge with `watercooler reindex`
   - Treats index as generated file

### What if I still get merge conflicts?

Even with `merge=union`, conflicts can occur if both developers modified the same header fields (Status/Ball/Updated).

**Resolution:**
1. Accept either version of conflicting headers
2. Run `watercooler reindex` to rebuild index
3. Commit the merge

The entries themselves (append-only) won't conflict.

### What does the pre-commit hook do?

The hook enforces the append-only protocol:

- ✅ Allows: Appending new entries
- ✅ Allows: Updating Status/Ball/Updated headers
- ❌ Blocks: Modifying existing entries
- ❌ Blocks: Changing other header fields

If blocked, use CLI commands instead:

```bash
watercooler set-status topic new-status
watercooler set-ball topic new-owner
watercooler append-entry topic --agent Agent --title "Update"
```

### Can I bypass the pre-commit hook?

Yes, but not recommended:

```bash
git commit --no-verify
```

**Warning:** Only bypass if you're certain your changes are safe and follow the append-only protocol.

### How do I collaborate across timezones?

Standard git workflow:

```bash
# Start of day: pull latest
git pull
watercooler list  # Check for NEW threads

# Do work
watercooler say topic --title "Update" --body "Progress made"

# Push updates
git add .watercooler/
git commit -m "watercooler: topic update"
git push

# Teammates pull to see updates
```

See [USE_CASES.md#async-team-collaboration](USE_CASES.md#async-team-collaboration) for examples.

---

## Troubleshooting

### Pre-commit hook not running

**Check if configured:**
```bash
git config --get core.hooksPath
# Should output: .githooks
```

**If not configured:**
```bash
git config core.hooksPath .githooks
```

**Make hook executable (Unix/Mac):**
```bash
chmod +x .githooks/pre-commit
```

### Pre-commit hook blocks valid changes

If the hook incorrectly blocks a commit:

1. Verify changes are truly append-only:
   ```bash
   git diff .watercooler/
   ```

2. Check you're only modifying allowed headers (Status/Ball/Updated)

3. If stuck, temporarily bypass:
   ```bash
   git commit --no-verify
   ```

4. Report issue: https://github.com/mostlyharmless-ai/watercooler-collab/issues

### Lock file stuck (thread won't update)

If you get lock timeout errors:

```bash
# Check lock status
watercooler unlock topic

# Force remove if stale
watercooler unlock topic --force
```

Lock files are in `.watercooler/.locks/` and contain PID/timestamp metadata.

### "merge.ours.driver" not configured

**Error:**
```
warning: Cannot merge binary files: .watercooler/index.md (HEAD vs. main)
```

**Fix:**
```bash
git config merge.ours.driver true
```

This must be done in each repository using watercooler.

### How do I check if git merge strategies are working?

**Test union merge** (thread files):
```bash
# Create test thread
watercooler init-thread test

# Create feature branch
git checkout -b test-branch

# Add entry on branch
watercooler say test --agent Team --title "Branch entry"
git add .watercooler/test.md
git commit -m "branch entry"

# Add entry on main
git checkout main
watercooler say test --agent Team --title "Main entry"
git add .watercooler/test.md
git commit -m "main entry"

# Merge - should auto-merge with both entries
git merge test-branch

# Check result
cat .watercooler/test.md
# Both entries should be present!
```

### Where are thread files stored?

Default: `.watercooler/` directory in current working directory

**Override with:**
- CLI: `--threads-dir /path/to/threads`
- Environment: `export WATERCOOLER_DIR=/path/to/threads`

### Can I use multiple threads directories?

Yes, specify `--threads-dir` per command:

```bash
watercooler list --threads-dir ./project-a/.watercooler
watercooler list --threads-dir ./project-b/.watercooler
```

Or use `$WATERCOOLER_DIR` per project.

### How do I delete a thread?

Threads are just markdown files:

```bash
rm .watercooler/topic.md
rm -rf .watercooler/.bak/topic/  # Remove backups too

# Rebuild index
watercooler reindex

# Commit deletion
git add .watercooler/
git commit -m "remove obsolete thread: topic"
```

### Web export creates wrong directory

If `watercooler web-export` creates `watercooler/` instead of `.watercooler/`:

**Check version:**
```bash
watercooler --version  # Should be >= L3
```

**Workaround:**
```bash
watercooler web-export --threads-dir .watercooler
```

This issue was fixed in commit 133432f.

### How do I integrate with CI/CD?

Example GitHub Actions:

```yaml
name: Watercooler Reindex

on:
  push:
    paths:
      - '.watercooler/*.md'

jobs:
  reindex:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install watercooler-collab
      - run: watercooler reindex
      - run: watercooler web-export
      - uses: stefanzweifel/git-auto-commit-action@v4
        with:
          commit_message: "watercooler: auto-reindex"
```

### How do I use watercooler with VS Code?

**Snippets** (add to `.vscode/snippets.code-snippets`):

```json
{
  "Watercooler Say": {
    "prefix": "wcsay",
    "body": [
      "watercooler say ${1:topic} \\",
      "  --agent ${2:Team} \\",
      "  --role ${3|pm,planner,implementer,critic,tester,scribe|} \\",
      "  --title \"${4:Title}\" \\",
      "  --body \"${5:Body}\""
    ]
  }
}
```

**Tasks** (add to `.vscode/tasks.json`):

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Watercooler: List Threads",
      "type": "shell",
      "command": "watercooler list",
      "problemMatcher": []
    },
    {
      "label": "Watercooler: Reindex",
      "type": "shell",
      "command": "watercooler reindex",
      "problemMatcher": []
    }
  ]
}
```

---

## See Also

- [USE_CASES.md](USE_CASES.md) - Comprehensive practical examples
- [STRUCTURED_ENTRIES.md](STRUCTURED_ENTRIES.md) - Entry format and roles
- [AGENT_REGISTRY.md](AGENT_REGISTRY.md) - Agent configuration
- [.github/WATERCOOLER_SETUP.md](../.github/WATERCOOLER_SETUP.md) - Git setup guide
- [README.md](../README.md) - Main documentation
