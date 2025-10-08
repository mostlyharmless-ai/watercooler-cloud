"""Watercooler MCP Server - Phase 1B

FastMCP server that exposes watercooler-collab tools to AI agents.
Tools are namespaced as watercooler_v1_* for provider compatibility.

Phase 1B features:
- Upward directory search for .watercooler/ (stops at git root or HOME)
- Comprehensive documentation (QUICKSTART.md, TROUBLESHOOTING.md)
- Codex TOML configuration support
"""

__version__ = "0.2.0"

from .server import mcp

__all__ = ["mcp"]
