from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from importlib import metadata as importlib_metadata  # type: ignore
except ImportError:  # pragma: no cover - Python <3.8 fallback
    import importlib_metadata  # type: ignore

from watercooler.agents import _canonical_agent, _load_agents_registry

from .git_sync import GitSyncManager, _diag

# GitPython for subprocess-free git discovery (fixes Windows stdio hang)
from git import Repo, InvalidGitRepositoryError, GitCommandError

from .provisioning import is_auto_provision_requested


__all__ = [
    "ThreadContext",
    "resolve_thread_context",
    "get_threads_dir",
    "get_threads_dir_for",
    "get_git_sync_manager",
    "get_git_sync_manager_for",
    "get_git_sync_manager_from_context",
    "get_code_context",
    "get_agent_name",
    "get_version",
]


@dataclass(frozen=True)
class ThreadContext:
    """Resolved configuration for operating on watercooler threads."""

    code_root: Optional[Path]
    threads_dir: Path
    threads_repo_url: Optional[str]
    code_repo: Optional[str]
    code_branch: Optional[str]
    code_commit: Optional[str]
    code_remote: Optional[str]
    threads_slug: Optional[str]
    explicit_dir: bool


@dataclass(frozen=True)
class _GitDetails:
    root: Optional[Path]
    branch: Optional[str]
    commit: Optional[str]
    remote: Optional[str]


_SYNC_MANAGER_CACHE: Dict[Tuple[str, str], GitSyncManager] = {}
_SYNC_MANAGER_LOCK = threading.Lock()


def _expand_path(value: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(value))
    return Path(expanded)


def _resolve_path(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except Exception:
        return path


def _default_threads_base(code_root: Optional[Path]) -> Path:
    base_env = os.getenv("WATERCOOLER_THREADS_BASE")
    if base_env:
        return _resolve_path(_expand_path(base_env))

    if code_root is not None:
        try:
            parent = code_root.parent
            if parent != code_root:
                return _resolve_path(parent)
        except Exception:
            pass

    try:
        cwd = Path.cwd().resolve()
        parent = cwd.parent if cwd.parent != cwd else cwd
        return _resolve_path(parent)
    except Exception:
        # Fallback to the current working directory if resolution fails
        return _resolve_path(Path.cwd())


def _normalize_code_root(code_root: Optional[Path]) -> Optional[Path]:
    if code_root is None:
        return None
    if not isinstance(code_root, Path):
        code_root = Path(code_root)
    try:
        code_root = code_root.expanduser()
    except Exception:
        pass
    return _resolve_path(code_root)


def _run_git(args: list[str], cwd: Path) -> Optional[str]:
    cmd = " ".join(args)
    _diag(f"CONFIG_GIT_START: git {cmd} (cwd={cwd})")
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        )
        _diag(f"CONFIG_GIT_END: git {cmd} (returned {len(result.stdout)} chars)")
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        _diag(f"CONFIG_GIT_FAIL: git {cmd} (error: {type(e).__name__})")
        return None


def _discover_git(code_root: Optional[Path]) -> _GitDetails:
    """Discover git repository info using GitPython (no subprocess, fixes Windows stdio hang)."""
    if code_root is None:
        return _GitDetails(None, None, None, None)
    if not code_root.exists():
        return _GitDetails(None, None, None, None)

    _diag(f"CONFIG: Discovering git info for {code_root}")

    try:
        # Use GitPython to discover git info (no subprocess)
        repo = Repo(code_root, search_parent_directories=True)

        # Get repository root
        root = Path(repo.working_dir) if repo.working_dir else None

        # Get current branch (None if detached HEAD)
        try:
            branch = repo.active_branch.name
        except TypeError:
            # Detached HEAD state
            branch = None

        # Get short commit hash
        try:
            commit = repo.head.commit.hexsha[:7]
        except (ValueError, AttributeError):
            commit = None

        # Get origin remote URL
        try:
            # repo.remotes returns IterableList - use repo.remote() for safe access
            remote = repo.remote('origin').url
        except (ValueError, AttributeError, IndexError):
            # ValueError raised if 'origin' remote doesn't exist
            remote = None

        if root is not None:
            root = _resolve_path(root)

        _diag(f"CONFIG: Git discovery complete (root={root}, branch={branch})")
        return _GitDetails(root=root, branch=branch, commit=commit, remote=remote)

    except InvalidGitRepositoryError:
        _diag(f"CONFIG: Not a git repository: {code_root}")
        return _GitDetails(None, None, None, None)
    except Exception as e:
        _diag(f"CONFIG: Git discovery error: {e}")
        return _GitDetails(None, None, None, None)


def _branch_has_upstream(code_root: Optional[Path], branch: Optional[str]) -> bool:
    """Check if branch has upstream using GitPython (no subprocess)."""
    if code_root is None or branch is None:
        return False

    try:
        repo = Repo(code_root, search_parent_directories=True)
        if branch not in [b.name for b in repo.heads]:
            return False
        branch_obj = repo.heads[branch]
        return branch_obj.tracking_branch() is not None
    except (InvalidGitRepositoryError, AttributeError, IndexError):
        return False


def _strip_repo_suffix(value: str) -> str:
    value = value.strip()
    if value.endswith(".git"):
        value = value[:-4]
    return value.rstrip("/")


def _extract_repo_path(remote: str) -> Optional[str]:
    remote = remote.strip()
    if not remote:
        return None
    remote = _strip_repo_suffix(remote)
    if remote.startswith("git@"):
        remote = remote.split(":", 1)[-1]
    elif "://" in remote:
        remote = remote.split("://", 1)[-1]
        if "/" in remote:
            remote = remote.split("/", 1)[-1]
        else:
            remote = ""
    remote = remote.lstrip("/")
    return remote or None


def _split_namespace_repo(slug: str) -> Tuple[Optional[str], str]:
    parts = [p for p in slug.split("/") if p]
    if not parts:
        return (None, slug)
    if len(parts) == 1:
        return (None, parts[0])
    namespace = "/".join(parts[:-1])
    return (namespace, parts[-1])


def _compose_threads_slug_from_code(code_repo: str) -> str:
    namespace, repo = _split_namespace_repo(code_repo)
    if repo.endswith("-threads"):
        slug_repo = repo
    else:
        slug_repo = f"{repo}-threads"
    if namespace:
        return f"{namespace}/{slug_repo}"
    return slug_repo


def _compose_local_threads_path(base: Path, slug: str) -> Path:
    parts = [p for p in slug.split("/") if p]
    path = base
    for part in parts[:-1]:
        path = path / part
    if parts:
        path = path / parts[-1]
    return _resolve_path(path)


def _infer_threads_repo_from_code(ctx: ThreadContext) -> Optional[str]:
    """Infer a threads repo URL from the code repo remote when explicit config is missing."""

    if ctx.threads_slug is None:
        return None

    remote = ctx.code_remote or ""
    remote = remote.strip()
    if not remote:
        return None

    slug = ctx.threads_slug.strip("/")
    if not slug:
        return None

    if remote.startswith("git@"):
        host = remote.split(":", 1)[0]
        return f"{host}:{slug}.git"

    if "://" in remote:
        scheme, rest = remote.split("://", 1)
        host = rest.split("/", 1)[0]
        return f"{scheme}://{host}/{slug}.git"

    # Fallback: append slug directly for cases like 'github.com/org/repo'
    if "/" in remote:
        host = remote.split("/", 1)[0]
        return f"git@{host}:{slug}.git"

    return None


def resolve_thread_context(code_root: Optional[Path] = None) -> ThreadContext:
    normalized_root = _normalize_code_root(code_root)
    git_details = _discover_git(normalized_root)

    explicit_dir_env = os.getenv("WATERCOOLER_DIR")
    explicit_dir = bool(explicit_dir_env)
    if explicit_dir_env:
        threads_dir = _resolve_path(_expand_path(explicit_dir_env))
    else:
        threads_dir = None

    code_repo_env = os.getenv("WATERCOOLER_CODE_REPO")

    code_remote = git_details.remote
    code_repo = code_repo_env or None

    if code_repo is None and code_remote:
        repo_path = _extract_repo_path(code_remote)
        if repo_path:
            parts = [p for p in repo_path.split("/") if p]
            if parts:
                code_repo = "/".join(parts)

    threads_repo_env = os.getenv("WATERCOOLER_GIT_REPO")
    threads_repo_url = threads_repo_env or None

    if not threads_repo_url and code_repo:
        namespace, repo = _split_namespace_repo(code_repo)
        pattern = os.getenv("WATERCOOLER_THREADS_PATTERN")
        if not pattern:
            default_pattern = "https://github.com/{org}/{repo}-threads.git"
            remote = code_remote or ""
            if remote.startswith("git@") or remote.startswith("ssh://"):
                default_pattern = "git@github.com:{org}/{repo}-threads.git"
            pattern = default_pattern
        format_kwargs = {
            "repo": repo,
            "namespace": namespace or "",
            "org": (namespace.split("/", 1)[0] if namespace else repo),
        }
        try:
            threads_repo_url = pattern.format(**format_kwargs)
        except (KeyError, IndexError, ValueError):
            threads_repo_url = None

    threads_slug = None
    if threads_repo_url:
        repo_path = _extract_repo_path(threads_repo_url)
        if repo_path:
            threads_slug = repo_path
    elif code_repo:
        threads_slug = _compose_threads_slug_from_code(code_repo)

    if threads_dir is None:
        env_base = os.getenv("WATERCOOLER_THREADS_BASE")
        base = _default_threads_base(git_details.root or normalized_root)

        if env_base:
            if threads_slug:
                threads_dir = _compose_local_threads_path(base, threads_slug)
            else:
                threads_dir = _resolve_path(base / "_local")
        elif git_details.root is not None:
            threads_dir = _resolve_path(git_details.root.parent / f"{git_details.root.name}-threads")
        elif normalized_root is not None:
            threads_dir = _resolve_path(normalized_root.parent / f"{normalized_root.name}-threads")
        elif threads_slug:
            local_name = threads_slug.split("/")[-1]
            threads_dir = _resolve_path(base / local_name)
        else:
            threads_dir = _resolve_path(base / "_local")

    return ThreadContext(
        code_root=git_details.root or normalized_root,
        threads_dir=threads_dir,
        threads_repo_url=threads_repo_url,
        code_repo=code_repo,
        code_branch=git_details.branch,
        code_commit=git_details.commit,
        code_remote=code_remote,
        threads_slug=threads_slug,
        explicit_dir=explicit_dir,
    )


def get_threads_dir() -> Path:
    return resolve_thread_context().threads_dir


def get_threads_dir_for(code_root: Optional[Path]) -> Path:
    return resolve_thread_context(code_root).threads_dir


def _get_cache_key(threads_dir: Path, repo_url: str) -> Tuple[str, str]:
    resolved_dir = _resolve_path(threads_dir)
    return (str(resolved_dir), repo_url)


def _get_git_identity() -> Tuple[str, str]:
    author = os.getenv("WATERCOOLER_GIT_AUTHOR")
    if not author:
        author = os.getenv("WATERCOOLER_AGENT", "Watercooler MCP")
    email = os.getenv("WATERCOOLER_GIT_EMAIL", "mcp@watercooler.dev")
    return author, email


def _get_git_ssh_key() -> Optional[Path]:
    key = os.getenv("WATERCOOLER_GIT_SSH_KEY")
    if not key:
        return None
    return _resolve_path(_expand_path(key))


def get_git_sync_manager() -> Optional[GitSyncManager]:
    ctx = resolve_thread_context()
    return _build_sync_manager(ctx)


def get_git_sync_manager_for(code_root: Optional[Path]) -> Optional[GitSyncManager]:
    ctx = resolve_thread_context(code_root)
    return _build_sync_manager(ctx)


def get_git_sync_manager_from_context(ctx: ThreadContext) -> Optional[GitSyncManager]:
    return _build_sync_manager(ctx)


def _build_sync_manager(ctx: ThreadContext) -> Optional[GitSyncManager]:
    repo_url = ctx.threads_repo_url or _infer_threads_repo_from_code(ctx)
    if not repo_url:
        return None

    branch_published = _branch_has_upstream(ctx.code_root, ctx.code_branch)

    key = _get_cache_key(ctx.threads_dir, repo_url)
    with _SYNC_MANAGER_LOCK:
        manager = _SYNC_MANAGER_CACHE.get(key)
        if manager:
            manager.set_remote_allowed(branch_published)
            return manager

        provision_requested = is_auto_provision_requested()
        enable_provision = bool(
            provision_requested
            and not ctx.explicit_dir
            and repo_url
            and ctx.threads_slug
            and repo_url.startswith("git@")
        )

        # Clear any stale cache entry for this directory (repo URL changed)
        stale_keys = [k for k in _SYNC_MANAGER_CACHE if k[0] == key[0]]
        for stale in stale_keys:
            old_manager = _SYNC_MANAGER_CACHE.pop(stale, None)
            if old_manager is not None:
                try:
                    old_manager.shutdown()
                except Exception:
                    pass

        author, email = _get_git_identity()
        ssh_key = _get_git_ssh_key()

        manager = GitSyncManager(
            repo_url=repo_url,
            local_path=ctx.threads_dir,
            ssh_key_path=ssh_key,
            author_name=author,
            author_email=email,
            threads_slug=ctx.threads_slug,
            code_repo=ctx.code_repo,
            enable_provision=enable_provision,
            remote_allowed=branch_published,
        )
        _SYNC_MANAGER_CACHE[key] = manager
        return manager


def get_code_context(code_root: Optional[Path]) -> Dict[str, str]:
    ctx = resolve_thread_context(code_root)
    return {
        "code_root": str(ctx.code_root) if ctx.code_root else "",
        "code_repo": ctx.code_repo or "",
        "code_branch": ctx.code_branch or "",
        "code_commit": ctx.code_commit or "",
        "threads_repo": ctx.threads_repo_url or "",
        "threads_dir": str(ctx.threads_dir),
    }


def get_agent_name(client_id: Optional[str] = None) -> str:
    agent_env = os.getenv("WATERCOOLER_AGENT")
    if agent_env:
        base_agent = agent_env
    else:
        base_agent = _infer_agent_from_client(client_id)
    registry_path = os.getenv("WATERCOOLER_AGENT_REGISTRY")
    registry = _load_agents_registry(registry_path)
    explicit_tag = os.getenv("WATERCOOLER_AGENT_TAG")
    return _canonical_agent(base_agent, registry, user_tag=explicit_tag)


def _infer_agent_from_client(client_id: Optional[str]) -> str:
    if not client_id:
        return "Agent"
    lowered = client_id.strip().lower()
    if not lowered:
        return "Agent"
    if lowered.startswith("claude"):
        return "Claude"
    if lowered.startswith("codex"):
        return "Codex"
    if lowered.startswith("gpt"):
        return "GPT"
    return client_id.split()[0]


def get_version() -> str:
    for dist_name in ("watercooler-cloud", "watercooler-mcp"):
        try:
            return importlib_metadata.version(dist_name)
        except importlib_metadata.PackageNotFoundError:
            continue
        except Exception:
            break
    return os.getenv("WATERCOOLER_MCP_VERSION", "0.0.0")
