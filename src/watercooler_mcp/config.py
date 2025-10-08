"""Configuration for Watercooler MCP Server - Phase 1B

Environment-based configuration with upward directory search for .watercooler/
"""

import os
import subprocess
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


def _find_git_root(start_path: Path) -> Path | None:
    """Find git repository root by looking for .git directory.

    Args:
        start_path: Directory to start searching from

    Returns:
        Path to git root if found, None otherwise
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start_path,
            capture_output=True,
            text=True,
            timeout=1.0
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_threads_dir() -> Path:
    """Get threads directory with upward search.

    Returns:
        Path to threads directory.

    Resolution order (Phase 1B):
    1. WATERCOOLER_DIR env var (explicit override)
    2. Upward search from CWD for .watercooler/ (stops at git root or HOME)
    3. Fallback: Path.cwd() / ".watercooler" (for auto-creation)

    The upward search looks for an existing .watercooler/ directory starting
    from the current working directory and moving up the tree. It stops at:
    - The git repository root (if in a git repo)
    - The user's HOME directory
    - The filesystem root (as a safety limit)

    If no existing .watercooler/ is found, returns CWD/.watercooler for
    auto-creation by watercooler commands.
    """
    # 1. Explicit override
    dir_str = os.getenv("WATERCOOLER_DIR")
    if dir_str:
        return Path(dir_str)

    # 2. Upward search for existing .watercooler/
    cwd = Path.cwd()
    git_root = _find_git_root(cwd)
    home = Path.home()

    # Determine search boundary (stop at git root or HOME, whichever is closer)
    if git_root and cwd.is_relative_to(git_root):
        search_limit = git_root
    else:
        search_limit = home

    # Search upward from CWD to search_limit
    current = cwd
    while True:
        candidate = current / ".watercooler"
        if candidate.exists() and candidate.is_dir():
            return candidate

        # Stop if we've reached the search limit
        if current == search_limit:
            break

        # Stop if we've reached filesystem root (safety)
        if current == current.parent:
            break

        current = current.parent

    # 3. Fallback: CWD/.watercooler (for auto-creation)
    return cwd / ".watercooler"


def get_version() -> str:
    """Get the watercooler_mcp version."""
    from . import __version__
    return __version__


def get_git_sync_manager():
    """Get git sync manager if configured (cloud mode).

    Returns:
        GitSyncManager instance if WATERCOOLER_GIT_REPO is set, None otherwise

    Environment Variables:
        WATERCOOLER_GIT_REPO: Git repository URL (enables cloud mode)
        WATERCOOLER_GIT_SSH_KEY: Optional path to SSH private key
        WATERCOOLER_GIT_AUTHOR: Git commit author name (default: "Watercooler MCP")
        WATERCOOLER_GIT_EMAIL: Git commit author email (default: "mcp@watercooler.dev")

    Example:
        sync = get_git_sync_manager()
        if sync:
            # Cloud mode: use git sync
            sync.with_sync(operation, commit_message)
        else:
            # Local mode: no sync
            operation()
    """
    repo_url = os.getenv("WATERCOOLER_GIT_REPO")
    if not repo_url:
        return None  # Local mode

    from .git_sync import GitSyncManager

    ssh_key = os.getenv("WATERCOOLER_GIT_SSH_KEY")
    return GitSyncManager(
        repo_url=repo_url,
        local_path=get_threads_dir(),
        ssh_key_path=Path(ssh_key) if ssh_key else None,
        author_name=os.getenv("WATERCOOLER_GIT_AUTHOR", "Watercooler MCP"),
        author_email=os.getenv("WATERCOOLER_GIT_EMAIL", "mcp@watercooler.dev")
    )
