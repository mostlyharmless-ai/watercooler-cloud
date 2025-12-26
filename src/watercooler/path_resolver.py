"""Unified path resolution for threads and templates.

Consolidates git-aware path discovery logic used by both
the core library and MCP server. This eliminates duplication
between watercooler/config.py and watercooler_mcp/config.py.

Uses subprocess for git operations (no external dependencies).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class GitInfo:
    """Git repository information from subprocess git calls.

    Attributes:
        root: Repository root directory (resolved path)
        branch: Current branch name (None if detached HEAD)
        commit: Short commit hash (7 chars)
        remote: Origin remote URL
    """
    root: Optional[Path]
    branch: Optional[str]
    commit: Optional[str]
    remote: Optional[str]


def _expand_path(value: str) -> Path:
    """Expand environment variables and user home directory in path."""
    return Path(os.path.expanduser(os.path.expandvars(value)))


def _resolve_path(path: Path) -> Path:
    """Safely resolve path, handling errors gracefully."""
    try:
        return path.resolve(strict=False)
    except Exception:
        return path


def _run_git(args: list[str], cwd: Path) -> Optional[str]:
    """Run git command and return output.

    Args:
        args: Git command arguments (e.g., ["rev-parse", "--show-toplevel"])
        cwd: Working directory for git command

    Returns:
        Stripped stdout if successful, None on error
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def discover_git_info(code_root: Optional[Path]) -> GitInfo:
    """Discover git repository information using subprocess.

    Consolidates logic from watercooler/config.py and watercooler_mcp/config.py.
    Uses subprocess git calls (no GitPython dependency).

    Args:
        code_root: Directory to search from (searches parent dirs)

    Returns:
        GitInfo with repository details (all None if not a git repo)
    """
    if code_root is None or not code_root.exists():
        return GitInfo(None, None, None, None)

    # Check if we're in a git repository
    is_repo = _run_git(["rev-parse", "--is-inside-work-tree"], code_root)
    if not is_repo or is_repo.lower() != "true":
        return GitInfo(None, None, None, None)

    # Get repository root
    root_str = _run_git(["rev-parse", "--show-toplevel"], code_root)
    root = Path(root_str).resolve() if root_str else None

    # Get current branch (None if detached HEAD)
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], code_root)
    if branch == "HEAD":
        branch = None  # Detached HEAD state

    # Get short commit hash
    commit = _run_git(["rev-parse", "--short", "HEAD"], code_root)

    # Get origin remote URL
    remote = _run_git(["remote", "get-url", "origin"], code_root)

    return GitInfo(root=root, branch=branch, commit=commit, remote=remote)


def _default_threads_base(repo_root: Optional[Path]) -> Path:
    """Determine default base directory for threads repositories.

    Precedence:
    1. WATERCOOLER_THREADS_BASE env var
    2. Parent of repo_root (if available)
    3. Parent of current working directory

    Args:
        repo_root: Git repository root (if in a git repo)

    Returns:
        Resolved base directory path
    """
    base_env = os.getenv("WATERCOOLER_THREADS_BASE")
    if base_env:
        return _resolve_path(_expand_path(base_env))

    if repo_root is not None:
        try:
            parent = repo_root.parent
            if parent != repo_root:
                return _resolve_path(parent)
        except Exception:
            pass

    try:
        cwd = Path.cwd().resolve()
        parent = cwd.parent if cwd.parent != cwd else cwd
        return _resolve_path(parent)
    except Exception:
        # Fallback to current working directory if resolution fails
        return _resolve_path(Path.cwd())


def _strip_repo_suffix(value: str) -> str:
    """Strip .git suffix and trailing slashes from URL."""
    value = value.strip()
    if value.endswith(".git"):
        value = value[:-4]
    return value.rstrip("/")


def _extract_repo_path(remote: Optional[str]) -> Optional[str]:
    """Extract repository path from git remote URL.

    Handles various formats:
    - git@github.com:org/repo.git -> org/repo
    - https://github.com/org/repo.git -> org/repo
    - ssh://git@github.com/org/repo -> org/repo

    Args:
        remote: Git remote URL

    Returns:
        Extracted path (e.g., "org/repo") or None
    """
    if not remote:
        return None

    remote = _strip_repo_suffix(remote)

    # Handle git@ format (SSH)
    if remote.startswith("git@"):
        remote = remote.split(":", 1)[-1]
    # Handle URL format (https://, ssh://, etc.)
    elif "://" in remote:
        remote = remote.split("://", 1)[-1]
        if "/" in remote:
            remote = remote.split("/", 1)[-1]
        else:
            remote = ""

    remote = remote.lstrip("/")
    return remote or None


def _split_namespace_repo(slug: str) -> Tuple[Optional[str], str]:
    """Split repository slug into namespace and repo name.

    Examples:
    - "repo" -> (None, "repo")
    - "org/repo" -> ("org", "repo")
    - "group/subgroup/repo" -> ("group/subgroup", "repo")

    Args:
        slug: Repository slug (e.g., "org/repo")

    Returns:
        Tuple of (namespace, repo_name)
    """
    parts = [p for p in slug.split("/") if p]
    if not parts:
        return None, slug
    if len(parts) == 1:
        return None, parts[0]
    namespace = "/".join(parts[:-1])
    return namespace, parts[-1]


def _compose_threads_slug(code_repo: Optional[str], repo_root: Optional[Path]) -> Optional[str]:
    """Compose threads repository slug from code repository info.

    Appends "-threads" suffix to repository name if not already present.

    Args:
        code_repo: Code repository path (e.g., "org/repo")
        repo_root: Code repository root directory

    Returns:
        Threads repository slug (e.g., "org/repo-threads")
    """
    if code_repo:
        namespace, repo = _split_namespace_repo(code_repo)
        repo_name = repo if repo.endswith("-threads") else f"{repo}-threads"
        if namespace:
            return f"{namespace}/{repo_name}"
        return repo_name

    if repo_root:
        repo_name = repo_root.name
        return f"{repo_name}-threads"

    return None


def _compose_local_threads_path(base: Path, slug: str) -> Path:
    """Compose local path for threads directory from slug.

    Args:
        base: Base directory
        slug: Repository slug (e.g., "org/repo-threads")

    Returns:
        Resolved path combining base and slug parts
    """
    parts = [p for p in slug.split("/") if p]
    path = base
    for part in parts:
        path = path / part
    return _resolve_path(path)


def resolve_threads_dir(
    cli_value: Optional[str] = None,
    code_root: Optional[Path] = None
) -> Path:
    """Resolve threads directory with precedence: CLI > env > git-aware default.

    Consolidates logic from watercooler/config.py and watercooler_mcp/config.py.

    Precedence:
    1. CLI argument (if provided)
    2. WATERCOOLER_DIR environment variable
    3. Git-aware discovery:
       - <repo-parent>/<repo-name>-threads (if in git repo)
       - <base>/<org>/<repo>-threads (using remote URL)
       - <base>/_local (fallback)

    Args:
        cli_value: Explicit directory from CLI argument
        code_root: Code repository root for context

    Returns:
        Resolved threads directory path
    """
    def _normalize(candidate: Path) -> Path:
        """Normalize path (expand, resolve)."""
        candidate = candidate.expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (Path.cwd() / candidate).resolve()

    # 1. CLI argument takes precedence
    if cli_value:
        return _normalize(Path(cli_value))

    # 2. Explicit environment variable
    explicit = os.getenv("WATERCOOLER_DIR")
    if explicit:
        return _normalize(_expand_path(explicit))

    # 3. Git-aware discovery
    if code_root is None:
        code_root = Path.cwd()

    git_info = discover_git_info(code_root)
    repo_root = git_info.root
    remote = git_info.remote

    base = _default_threads_base(repo_root)
    repo_slug = _extract_repo_path(remote)
    threads_slug = _compose_threads_slug(repo_slug, repo_root)

    # Prefer <repo-parent>/<repo-name>-threads if we have a repo root
    if repo_root is not None:
        return (repo_root.parent / f"{repo_root.name}-threads").resolve()

    # Otherwise use base + slug
    if threads_slug:
        threads_dir = _compose_local_threads_path(base, threads_slug)

        # Never write threads inside the code repository
        try:
            if repo_root and threads_dir.is_relative_to(repo_root):
                return (base / "_local").resolve()
        except AttributeError:
            # Python <3.9: emulate is_relative_to
            repo_root_resolved = repo_root.resolve() if repo_root else None
            threads_resolved = threads_dir.resolve()
            if repo_root_resolved and str(threads_resolved).startswith(str(repo_root_resolved)):
                return (base / "_local").resolve()
        except ValueError:
            return (base / "_local").resolve()

        return threads_dir

    # Fallback
    return (base / "_local").resolve()


def resolve_templates_dir(cli_value: Optional[str] = None) -> Path:
    """Resolve templates directory with fallback chain.

    Precedence:
    1. CLI argument (--templates-dir)
    2. WATERCOOLER_TEMPLATES environment variable
    3. Project-local templates (./.watercooler/templates/ if exists)
    4. Package bundled templates (always available as fallback)

    Args:
        cli_value: Explicit directory from CLI argument

    Returns:
        Path to directory containing _TEMPLATE_*.md files
    """
    if cli_value:
        return Path(cli_value)

    env = os.getenv("WATERCOOLER_TEMPLATES")
    if env:
        return Path(env)

    # Check for project-local templates
    project_local = Path(".watercooler/templates")
    if project_local.exists() and project_local.is_dir():
        return project_local.resolve()

    # Fallback to package bundled templates
    # This returns src/watercooler/templates/ in development
    # or site-packages/watercooler/templates/ when installed
    return Path(__file__).parent / "templates"
