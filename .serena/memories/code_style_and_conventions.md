# Code Style and Conventions

## Python Standards
- **Python Version**: 3.9+ compatibility required
- **Type Hints**: Use mypy for type checking
- **Package Structure**: Standard src-layout (src/watercooler/, src/watercooler_mcp/)

## Design Principles
1. **Stdlib-only**: No external runtime dependencies in core library
2. **File-based**: Git-friendly markdown format
3. **Zero-config**: Works out-of-box for standard layouts
4. **CLI parity**: Drop-in replacement workflows

## Module Organization
- Core library in `src/watercooler/`
- MCP server integration in `src/watercooler_mcp/`
- Tests mirror source structure in `tests/`
- Templates bundled with package

## Entry Format
- Structured metadata: Agent, Role, Type, Title
- Agent format: `Agent (user)` e.g., "Claude (agent)"
- Timestamp: ISO 8601 format
- Markdown body with YAML frontmatter

## Naming Conventions
- CLI commands: kebab-case (e.g., init-thread, append-entry)
- Python modules: snake_case
- Agent roles: lowercase (planner, critic, implementer, tester, pm, scribe)
- Entry types: PascalCase (Note, Plan, Decision, PR, Closure)
