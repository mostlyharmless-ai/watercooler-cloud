"""Watercooler MCP Server - Phase 1A MVP

FastMCP server that exposes watercooler-collab tools to AI agents.
Tools are namespaced as watercooler_v1_* for provider compatibility.
"""

__version__ = "0.1.0"

from .server import mcp

__all__ = ["mcp"]
