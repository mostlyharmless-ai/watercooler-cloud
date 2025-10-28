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
    """Get threads directory (never default inside the code repo).

    Resolution order:
    0. Dynamic threads repo (universal dev mode) if resolvable
    1. WATERCOOLER_DIR env var (explicit override)
    2. Upward search from CWD for an existing .watercooler/ (stops at git root or HOME)
    3. Fallback: a safe global path under WATERCOOLER_THREADS_BASE (not CWD)

    Notes:
    - We intentionally do NOT default to CWD/.watercooler to avoid polluting the
      code repo with local thread state when dynamic resolution fails.
    """
    # 0. Dynamic threads repo (universal dev mode)
    dyn = get_dynamic_threads_dir()
    if dyn:
        return dyn

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

    # 3. Fallback: Global-safe path under THREADS_BASE
    base = Path(os.getenv("WATERCOOLER_THREADS_BASE", str(Path.home() / ".watercooler-threads")))
    return base / "_local"


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
    # Resolve explicit or dynamic threads repo
    resolved = resolve_threads_repo()
    if not resolved:
        return None  # Local mode (no git sync)
    repo_url, local_clone = resolved

    from .git_sync import GitSyncManager

    ssh_key = os.getenv("WATERCOOLER_GIT_SSH_KEY")
    return GitSyncManager(
        repo_url=repo_url,
        local_path=local_clone,
        ssh_key_path=Path(ssh_key) if ssh_key else None,
        author_name=os.getenv("WATERCOOLER_GIT_AUTHOR", "Watercooler MCP"),
        author_email=os.getenv("WATERCOOLER_GIT_EMAIL", "mcp@watercooler.dev")
    )


def _run_git(cmd: list[str], *, cwd: Path | None = None, timeout: float = 1.5) -> str | None:
    """Run a git command and return stdout.strip(), or None on failure.

    Keeps behavior lightweight and failure-tolerant; used for metadata capture.
    """
    try:
        result = subprocess.run(
            ["git", *cmd],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return (result.stdout or "").strip()
    except Exception:
        return None
    return None


def _parse_origin_to_org_repo(url: str | None) -> str | None:
    """Normalize a git remote URL to "org/repo" if possible.

    Supports SSH (git@github.com:org/repo.git) and HTTPS (https://github.com/org/repo.git).
    Returns None if parsing fails.
    """
    if not url:
        return None
    u = url.strip()
    # Remove trailing .git
    if u.endswith(".git"):
        u = u[:-4]
    # SSH form
    if ":" in u and u.startswith("git@"):
        try:
            after_colon = u.split(":", 1)[1]
            parts = after_colon.split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
        except Exception:
            return None
    # HTTPS form
    if "github.com/" in u:
        try:
            after = u.split("github.com/", 1)[1]
            parts = after.split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
        except Exception:
            return None
    # Fallback: if already looks like org/repo, accept
    if "/" in u and not u.startswith("http") and not u.startswith("git@"):  # e.g., org/repo
        return u
    return None


def get_code_context(code_root: Path | None = None) -> dict:
    """Best-effort capture of code repo context for commit footers.

    Returns a dict with optional keys: code_repo, code_branch, code_commit.
    Resolution order:
    - Determine git root from the current working directory (preferred)
    - code_branch: `git rev-parse --abbrev-ref HEAD`
    - code_commit: `git rev-parse --short HEAD`
    - code_repo: parse org/repo from `git remote get-url origin` or env WATERCOOLER_CODE_REPO
    """
    ctx: dict[str, str] = {}

    # Determine base path for git commands: prefer provided code_root, then CWD
    try:
        base = code_root if code_root else Path.cwd()
        git_root = _find_git_root(base)
    except Exception:
        git_root = None

    # Branch and commit
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)
    if branch and branch != "HEAD":  # detached HEAD returns HEAD
        ctx["code_branch"] = branch
    commit = _run_git(["rev-parse", "--short", "HEAD"], cwd=git_root)
    if commit:
        ctx["code_commit"] = commit

    # Repo (org/repo)
    env_repo = os.getenv("WATERCOOLER_CODE_REPO")
    if env_repo:
        ctx["code_repo"] = env_repo.strip()
    else:
        origin = _run_git(["remote", "get-url", "origin"], cwd=git_root)
        normalized = _parse_origin_to_org_repo(origin)
        if normalized:
            ctx["code_repo"] = normalized

    return ctx


def _compose_threads_url(org_repo: str, pattern: str) -> str:
    org, repo = org_repo.split("/", 1)
    return pattern.replace("{org}", org).replace("{repo}", repo)


def resolve_threads_repo(code_root: Path | None = None) -> tuple[str, Path] | None:
    """Resolve the threads repo URL and local clone path dynamically.

    Uses the active code workspace git context to derive org/repo and then
    composes the threads repo URL via WATERCOOLER_THREADS_PATTERN.

    Returns (repo_url, local_clone_path) or None if unresolved.
    """
    # Prefer explicit override first
    explicit = os.getenv("WATERCOOLER_GIT_REPO")
    if explicit:
        # Map URL to a local path under base using org/repo if possible
        org_repo = _parse_origin_to_org_repo(explicit)
        base = Path(os.getenv("WATERCOOLER_THREADS_BASE", str(Path.home() / ".watercooler-threads")))
        local = base
        if org_repo:
            org, repo = org_repo.split("/", 1)
            local = base / org / repo
        return explicit, local

    # Resolve from code repo
    ctx = get_code_context(code_root)
    org_repo = ctx.get("code_repo") or os.getenv("WATERCOOLER_CODE_REPO")
    if not org_repo or "/" not in org_repo:
        return None

    pattern = os.getenv("WATERCOOLER_THREADS_PATTERN", "git@github.com:{org}/{repo}-threads.git")
    url = _compose_threads_url(org_repo, pattern)
    base = Path(os.getenv("WATERCOOLER_THREADS_BASE", str(Path.home() / ".watercooler-threads")))
    org, repo = org_repo.split("/", 1)
    local = base / org / f"{repo}-threads"
    return url, local


def get_threads_dir_for(code_root: Path | None = None) -> Path:
    """Return threads dir for a specific code root if resolvable, else fallback."""
    resolved = resolve_threads_repo(code_root)
    if resolved:
        _, local = resolved
        return local
    return get_threads_dir()


def get_git_sync_manager_for(code_root: Path | None = None):
    """Return a GitSyncManager bound to a specific code root, or fallback."""
    resolved = resolve_threads_repo(code_root)
    if not resolved:
        return get_git_sync_manager()
    repo_url, local_clone = resolved
    from .git_sync import GitSyncManager
    ssh_key = os.getenv("WATERCOOLER_GIT_SSH_KEY")
    return GitSyncManager(
        repo_url=repo_url,
        local_path=local_clone,
        ssh_key_path=Path(ssh_key) if ssh_key else None,
        author_name=os.getenv("WATERCOOLER_GIT_AUTHOR", "Watercooler MCP"),
        author_email=os.getenv("WATERCOOLER_GIT_EMAIL", "mcp@watercooler.dev")
    )


def get_dynamic_threads_dir() -> Path | None:
    """Return dynamic threads directory if resolvable, else None."""
    resolved = resolve_threads_repo()
    if not resolved:
        return None
    _, local = resolved
    return local
