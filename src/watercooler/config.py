from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _expand_path(value: str) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(value)))


def _default_threads_base(repo_root: Path | None) -> Path:
    base_env = os.getenv("WATERCOOLER_THREADS_BASE")
    if base_env:
        return _expand_path(base_env).resolve()

    if repo_root is not None and repo_root.parent != repo_root:
        return repo_root.parent.resolve()

    cwd = Path.cwd().resolve()
    parent = cwd.parent if cwd.parent != cwd else cwd
    return parent.resolve()


def _run_git(args: list[str], cwd: Path) -> str | None:
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


def _discover_git_root(start: Path) -> tuple[Path | None, str | None]:
    if not start.exists():
        return None, None
    is_repo = _run_git(["rev-parse", "--is-inside-work-tree"], start)
    if not is_repo or is_repo.lower() != "true":
        return None, None
    root_str = _run_git(["rev-parse", "--show-toplevel"], start)
    remote = _run_git(["remote", "get-url", "origin"], start)
    root = Path(root_str).resolve() if root_str else None
    return root, remote


def _strip_repo_suffix(value: str) -> str:
    value = value.strip()
    if value.endswith(".git"):
        value = value[:-4]
    return value.rstrip("/")


def _extract_repo_path(remote: str | None) -> str | None:
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


def _split_namespace_repo(slug: str) -> tuple[str | None, str]:
    parts = [p for p in slug.split("/") if p]
    if not parts:
        return None, slug
    if len(parts) == 1:
        return None, parts[0]
    namespace = "/".join(parts[:-1])
    return namespace, parts[-1]


def _compose_threads_slug(code_repo: str | None, repo_root: Path | None) -> str | None:
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
    parts = [p for p in slug.split("/") if p]
    path = base
    for part in parts[:-1]:
        path = path / part
    if parts:
        path = path / parts[-1]
    return path.resolve()


def resolve_threads_dir(cli_value: str | None = None) -> Path:
    """Resolve threads directory using precedence: CLI > env > git-aware default."""

    def _normalise(candidate: Path) -> Path:
        candidate = candidate.expanduser()
        if not candidate.is_absolute():
            candidate = Path.home() / candidate
        return candidate.resolve()

    if cli_value:
        return _normalise(Path(cli_value))

    explicit = os.getenv("WATERCOOLER_DIR")
    if explicit:
        return _normalise(_expand_path(explicit))

    cwd = Path.cwd()
    repo_root, remote = _discover_git_root(cwd)
    base = _default_threads_base(repo_root)
    repo_slug = _extract_repo_path(remote)
    threads_slug = _compose_threads_slug(repo_slug, repo_root)

    if repo_root is not None:
        return (repo_root.parent / f"{repo_root.name}-threads").resolve()

    if threads_slug:
        threads_dir = _compose_local_threads_path(base, threads_slug)
        try:
            if repo_root and threads_dir.is_relative_to(repo_root):
                # Never write threads inside the code repository
                raise ValueError
        except AttributeError:
            # Python <3.9: emulate is_relative_to
            repo_root_resolved = repo_root.resolve() if repo_root else None
            threads_resolved = threads_dir.resolve()
            if repo_root_resolved and str(threads_resolved).startswith(str(repo_root_resolved)):
                threads_dir = base / "_local"
                return threads_dir.resolve()
        except ValueError:
            return (base / "_local").resolve()
        return threads_dir

    return (base / "_local").resolve()


def resolve_templates_dir(cli_value: str | None = None) -> Path:
    """Resolve templates directory using precedence: CLI > env > project-local > package default.

    Precedence:
    1. CLI argument (--templates-dir)
    2. Environment variable (WATERCOOLER_TEMPLATES)
    3. Project-local templates (./.watercooler/templates/ if exists)
    4. Package bundled templates (always available as fallback)

    Returns Path to directory containing _TEMPLATE_*.md files.
    """
    if cli_value:
        return Path(cli_value)
    env = os.getenv("WATERCOOLER_TEMPLATES")
    if env:
        return Path(env)
    # Check for project-local templates
    project_local = Path(".watercooler/templates")
    if project_local.exists() and project_local.is_dir():
        return project_local
    # Fallback to package bundled templates
    # This returns src/watercooler/templates/ in development
    # or site-packages/watercooler/templates/ when installed
    return Path(__file__).parent / "templates"


def load_template(template_name: str, templates_dir: Path | None = None) -> str:
    """Load a template file with fallback to package bundled templates.

    Args:
        template_name: Name of template file (e.g., "_TEMPLATE_entry_block.md")
        templates_dir: Optional templates directory (uses resolve_templates_dir if None)

    Returns:
        Template content as string

    Raises:
        FileNotFoundError: If template not found in any location
    """
    if templates_dir is None:
        templates_dir = resolve_templates_dir()

    template_path = templates_dir / template_name

    # Try requested location first
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")

    # Fallback to package bundled templates
    bundled_path = Path(__file__).parent / "templates" / template_name
    if bundled_path.exists():
        return bundled_path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"Template '{template_name}' not found in {templates_dir} or bundled templates"
    )
