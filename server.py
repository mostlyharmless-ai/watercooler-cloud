"""Entry point for FastMCP Cloud deployment.

This file sits at the repository root and imports the watercooler MCP server
from the src/ package structure to avoid relative import issues.
"""

import sys
from pathlib import Path

# Add src/ to Python path so imports work
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import and re-export the MCP server
from watercooler_mcp.server import mcp

__all__ = ["mcp"]
