"""Configuration for Watercooler MCP Server - Phase 1A

Simple environment-based configuration for agent identity and directory discovery.
Phase 1B will add: upward .watercooler/ search to git root, git config user.name fallback.
"""

import os
from pathlib import Path


def get_agent_name(client_id: str | None = None) -> str:
    """Get agent identity with automatic client detection.

    Args:
        client_id: MCP client identifier from Context (e.g., "Claude Desktop")

    Returns:
        Agent name (e.g., "Claude", "Codex"). Defaults to "Agent" if not available.

    Precedence:
    1. WATERCOOLER_AGENT env var (explicit override)
    2. client_id from MCP Context (automatic detection)
    3. Fallback: "Agent"

    Client ID mapping:
    - "Claude Desktop" -> "Claude"
    - "Claude Code" -> "Claude"
    - Other values passed through as-is
    """
    # Explicit override
    env_agent = os.getenv("WATERCOOLER_AGENT")
    if env_agent:
        return env_agent

    # Automatic client detection
    if client_id:
        # Normalize common Claude clients to "Claude"
        if "claude" in client_id.lower():
            return "Claude"
        # Otherwise use the client_id as-is
        return client_id

    # Fallback
    return "Agent"


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
