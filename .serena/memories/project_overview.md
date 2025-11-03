# Project Overview

## Purpose
Watercooler Cloud is a file-based collaboration protocol for agentic coding projects. It enables structured multi-agent collaboration through Git-friendly markdown threads with explicit Status/Ball tracking.

## Tech Stack
- **Language**: Python 3.9+
- **Dependencies**: Stdlib-only (no external runtime dependencies)
- **Optional**: fastmcp>=2.0 for MCP server integration
- **Testing**: pytest>=7.0
- **Type Checking**: mypy>=1.0

## Key Features
- Thread-based collaboration with status/ball tracking
- 12 CLI commands for thread management
- 6 agent roles (planner, critic, implementer, tester, pm, scribe)
- 5 entry types (Note, Plan, Decision, PR, Closure)
- Agent registry with counterpart mappings
- Template system for customization
- MCP server for AI agent integration
- 56 passing tests with comprehensive coverage

## Architecture
- **Core**: src/watercooler/ - Main library
- **MCP Server**: src/watercooler_mcp/ - AI agent integration
- **Tests**: tests/ - Comprehensive test suite
- **Templates**: Bundled markdown templates
- **Storage**: .watercooler/ directory for threads
