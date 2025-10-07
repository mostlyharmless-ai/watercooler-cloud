"""Configuration for Watercooler MCP Server - Phase 1A

Simple environment-based configuration for agent identity and directory discovery.
Phase 1B will add: upward .watercooler/ search to git root, git config user.name fallback.
"""

import os
from pathlib import Path


def get_agent_name() -> str:
    """Get agent identity from WATERCOOLER_AGENT environment variable.

    Returns:
        Agent name (e.g., "Codex", "Claude"). Defaults to "Agent" if not set.

    Phase 1A precedence:
    1. WATERCOOLER_AGENT env var
    2. Fallback: "Agent"

    Phase 1B will add:
    - MCP client identity (if available)
    - git config user.name
    """
    return os.getenv("WATERCOOLER_AGENT", "Agent")


def get_threads_dir() -> Path:
    """Get threads directory from WATERCOOLER_DIR environment variable.

    Returns:
        Path to threads directory. Defaults to .watercooler in current directory.

    Phase 1A precedence:
    1. WATERCOOLER_DIR env var (if set)
    2. Fallback: Path.cwd() / ".watercooler"

    Phase 1B will add:
    - Upward search for .watercooler/ from CWD to git root
    """
    dir_str = os.getenv("WATERCOOLER_DIR")
    if dir_str:
        return Path(dir_str)
    return Path.cwd() / ".watercooler"


def get_version() -> str:
    """Get the watercooler_mcp version."""
    from . import __version__
    return __version__
