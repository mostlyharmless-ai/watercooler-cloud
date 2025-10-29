# Install Script Improvements (2025-01-09)

## Major Refinements to `scripts/install-mcp.sh`

### Simplifications
1. **Removed agent registry creation** - The `agents.json` file was only used by CLI (not MCP), added confusion
2. **Removed installation method menus** - Now uses single method per client:
   - Claude: `claude mcp add` with `python -m watercooler_mcp` (always)
   - Codex: Direct `~/.codex/config.toml` update (always)
3. **Removed scope selection prompt** - Now automatically uses "user" scope for Claude (works globally)

### Bug Fixes from User Feedback
1. **Virtual environment check** - Warns if not in venv, provides activation instructions
2. **Python path resolution** - Uses absolute path (`${PY_PATH}`) instead of command name to ensure correct interpreter
3. **Codex config error handling** - Added `update_codex_config()` function with:
   - Directory creation with permissions checks
   - File backup before modification
   - Overwrite confirmation prompts
   - Robust error messages

### Installation Flow (Current)
1. Check virtual environment (warn if missing)
2. Choose client (Claude/Codex/Both)
3. Check/install `watercooler-cloud[mcp]`
4. Optional agent name overrides
5. Optional threads directory path
6. Preview and confirm
7. Execute installation

### Key Files Modified
- `scripts/install-mcp.sh` - Main installation script
- Removed ~30 lines of agent registry logic
- Removed ~60 lines of method selection menus
- Added ~80 lines of robust error handling

### Testing Notes
- User reported issues: venv, pip install, python path, codex directory
- All issues addressed in this session
- Ready for re-testing
