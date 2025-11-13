"""Git-based synchronization for cloud-hosted watercooler MCP servers.

This module provides GitSyncManager for syncing .watercooler threads via git,
enabling multi-user collaboration with automatic conflict resolution.

Architecture (sync mode):
- Pull before writes (get latest from remote)
- Commit + push after writes (propagate changes)
- Retry logic handles concurrent modifications
- Append-only operations minimize conflicts

When async mode is enabled, commits are written locally immediately and pushed
from a background worker that batches git operations.
"""

import atexit
import json
import os
import re
import shlex
import subprocess
from subprocess import TimeoutExpired
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, TypeVar, List, Dict, Any
import sys
import hashlib

# GitPython for in-process git operations (avoids subprocess stdio issues on Windows)
import git
from git import Repo, GitCommandError, InvalidGitRepositoryError

# Windows stdio hang diagnostic instrumentation
_DIAGNOSTICS_ENABLED = os.getenv("WATERCOOLER_DIAGNOSTICS", "").lower() in ("1", "true", "yes")

def _diag(message: str):
    """Log diagnostic message to stderr (doesn't interfere with MCP stdio protocol)."""
    if _DIAGNOSTICS_ENABLED:
        timestamp = datetime.now().isoformat()
        print(f"[DIAG {timestamp}] {message}", file=sys.stderr, flush=True)

try:  # pragma: no cover - fallback for direct module import (tests)
    from .provisioning import ProvisioningError, provision_threads_repo
except ImportError:  # pragma: no cover - executed when module is loaded stand-alone
    import importlib.util
    import sys

    _current_dir = Path(__file__).resolve().parent
    _spec = importlib.util.spec_from_file_location(
        "watercooler_mcp.provisioning", _current_dir / "provisioning.py"
    )
    if _spec and _spec.loader:
        _module = importlib.util.module_from_spec(_spec)
        sys.modules.setdefault("watercooler_mcp.provisioning", _module)
        _spec.loader.exec_module(_module)  # type: ignore[attr-defined]
        ProvisioningError = getattr(_module, "ProvisioningError")  # type: ignore[assignment]
        provision_threads_repo = getattr(_module, "provision_threads_repo")  # type: ignore[assignment]
    else:  # pragma: no cover - defensive guard if spec resolution fails
        raise

T = TypeVar('T')


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_from_epoch(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _normalize_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
        if value <= 0:
            return default
        return value
    except ValueError:
        return default


def _parse_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
        if value <= 0:
            return default
        return value
    except ValueError:
        return default


@dataclass
class _PendingCommit:
    sequence: int
    entry_id: Optional[str]
    topic: Optional[str]
    commit_message: str
    timestamp: str
    created_ts: float

    def to_payload(self) -> dict:
        return {
            "sequence": self.sequence,
            "entry_id": self.entry_id,
            "topic": self.topic,
            "commit_message": self.commit_message,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "_PendingCommit":
        timestamp = payload.get("timestamp")
        created_ts = time.time()
        if isinstance(timestamp, str):
            try:
                created_ts = datetime.fromisoformat(timestamp).timestamp()
            except ValueError:
                pass
        return cls(
            sequence=int(payload["sequence"]),
            entry_id=payload.get("entry_id"),
            topic=payload.get("topic"),
            commit_message=payload.get("commit_message", ""),
            timestamp=timestamp or _now_iso(),
            created_ts=created_ts,
        )


def _checksum_payload(payload: dict) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return digest


class GitSyncError(Exception):
    """Base exception for git sync operations."""
    pass


class GitPullError(GitSyncError):
    """Failed to pull latest changes from remote."""
    pass


class GitPushError(GitSyncError):
    """Failed to push changes to remote."""
    pass


class BranchPairingError(GitSyncError):
    """Branch pairing validation failed."""
    pass


@dataclass
class BranchMismatch:
    """Represents a branch pairing mismatch."""
    type: str  # "branch_name_mismatch", "code_branch_missing", "threads_branch_missing", etc.
    code: Optional[str]
    threads: Optional[str]
    severity: str  # "error", "warning"
    recovery: str  # Suggested recovery command or action


@dataclass
class BranchPairingResult:
    """Result of branch pairing validation."""
    valid: bool
    code_branch: Optional[str]
    threads_branch: Optional[str]
    mismatches: List[BranchMismatch]
    warnings: List[str]


class GitSyncManager:
    """Manages git-based synchronization for watercooler threads directory.

    This class handles all git operations for cloud-hosted watercooler
    deployments, including pulling latest changes, committing local changes,
    and pushing to remote with retry logic.

    Attributes:
        repo_url: Git repository URL (SSH or HTTPS)
        local_path: Path to local .watercooler directory
        ssh_key_path: Optional path to SSH private key
        author_name: Git commit author name
        author_email: Git commit author email

    Thread Safety:
        This class is not thread-safe. Use advisory locks at a higher level
        for concurrent access to the same repository.
    """

    def __init__(
        self,
        repo_url: str,
        local_path: Path,
        ssh_key_path: Path | None = None,
        author_name: str = "Watercooler MCP",
        author_email: str = "mcp@watercooler.dev",
        *,
        threads_slug: str | None = None,
        code_repo: str | None = None,
        enable_provision: bool = False,
        remote_allowed: bool = True,
    ):
        """Initialize GitSyncManager.

        Args:
            repo_url: Git repository URL (e.g., git@github.com:org/repo.git)
            local_path: Path to local threads directory
            ssh_key_path: Optional path to SSH key for authentication
            author_name: Git commit author name
            author_email: Git commit author email

        Note:
            For best results, use a dedicated repository where the repo root
            is the threads directory. This minimizes unrelated changes and
            simplifies staging.
        """
        self.repo_url = repo_url
        self.local_path = local_path
        self.ssh_key_path = ssh_key_path
        self.author_name = author_name
        self.author_email = author_email
        self.threads_slug = threads_slug
        self.code_repo = code_repo
        self._provision_enabled = bool(enable_provision and threads_slug)
        self._last_provision_output: str | None = None
        self._remote_allowed = bool(remote_allowed)
        self._last_pull_error: str | None = None
        self._last_push_error: str | None = None
        self._last_remote_error: str | None = None
        self._remote_missing: bool = False
        self._remote_empty: bool = False
        self._async: Optional[_AsyncSyncCoordinator] = None

        # Prepare git environment once (propagated to all git operations)
        self._env = os.environ.copy()
        # Disable interactive prompts so git fails fast instead of hanging when
        # credentials are required (particularly important inside MCP tools).
        self._env.setdefault("GIT_TERMINAL_PROMPT", "0")
        self._env.setdefault("GIT_ASKPASS", "echo")
        self._env.setdefault("GCM_INTERACTIVE", "never")
        self._env.setdefault("GIT_HTTP_LOW_SPEED_LIMIT", "1")
        self._env.setdefault("GIT_HTTP_LOW_SPEED_TIME", "30")
        if self.ssh_key_path:
            self._env["GIT_SSH_COMMAND"] = f"ssh -i {self.ssh_key_path} -o IdentitiesOnly=yes"

        self._log_enabled = os.getenv("WATERCOOLER_SYNC_LOG", "0") not in {"0", "false", "off"}
        self._log_path = self.local_path.parent / ".watercooler-sync.log"
        self._async_enabled = self._resolve_async_enabled()
        self._async_config = self._load_async_config()

        self._setup()
        if self._async_enabled:
            self._init_async()

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        if not self._log_enabled:
            return
        try:
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{timestamp} {message}\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # GitPython helpers
    # ------------------------------------------------------------------

    @property
    def _repo(self) -> Repo:
        """Get GitPython Repo object for the local repository."""
        try:
            return Repo(self.local_path)
        except InvalidGitRepositoryError:
            raise GitSyncError(f"Not a git repository: {self.local_path}")

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
        timeout: Optional[float] = None,
    ) -> subprocess.CompletedProcess[str]:
        cwd = cwd or self.local_path if self.local_path.exists() else cwd
        cwd_str = str(cwd) if cwd is not None else None
        quoted = " ".join(shlex.quote(part) for part in cmd)
        self._log(f"RUN cwd={cwd_str or os.getcwd()} cmd={quoted}")
        start = time.time()
        try:
            # On Windows, explicitly close file descriptors to prevent handle inheritance
            # which can block parent stdio even with capture_output=True
            close_fds = sys.platform == "win32"

            result = subprocess.run(
                cmd,
                cwd=cwd_str,
                env=self._env,
                capture_output=True,
                text=True,
                timeout=timeout,
                close_fds=close_fds,
            )
        except TimeoutExpired as exc:
            elapsed = time.time() - start
            self._log(f"TIMEOUT after {elapsed:.2f}s cmd={quoted}")
            raise
        elapsed = time.time() - start
        stdout = getattr(result, "stdout", "") or ""
        stderr = getattr(result, "stderr", "") or ""
        # Normalize attributes for test doubles that do not populate stdout/stderr.
        try:
            result.stdout = stdout
            result.stderr = stderr
        except Exception:
            pass

        if stdout:
            out = stdout.strip().splitlines()
            stdout_preview = out[0][:160] if out else ""
        else:
            stdout_preview = ""
        if stderr:
            err = stderr.strip().splitlines()
            stderr_preview = err[0][:160] if err else ""
        else:
            stderr_preview = ""
        self._log(
            f"DONE rc={result.returncode} elapsed={elapsed:.2f}s stdout='{stdout_preview}' stderr='{stderr_preview}'"
        )

        # Workaround for Windows stdio hang: Force flush and brief delay
        # On Windows, running git subprocess leaves stdio handles in bad state,
        # causing FastMCP's response to get stuck in stdout buffer.
        # Brief delay ensures subprocess handles are fully released.
        if sys.platform == "win32":
            try:
                import time as time_module
                time_module.sleep(0.01)  # 10ms delay for handle cleanup
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        return result

    def _setup(self):
        """Ensure repository is cloned and configured."""
        self._initialise_repository()
        self._configure_git()

    def _resolve_async_enabled(self) -> bool:
        override = _normalize_bool(os.getenv("WATERCOOLER_ASYNC_SYNC"))
        if override is not None:
            return override
        return sys.platform == "win32"

    def _load_async_config(self) -> dict:
        return {
            "batch_window": _parse_float_env("WATERCOOLER_BATCH_WINDOW", 5.0),
            "max_delay": _parse_float_env("WATERCOOLER_MAX_BATCH_DELAY", 30.0),
            "max_batch_size": _parse_int_env("WATERCOOLER_MAX_BATCH_SIZE", 50),
            "max_sync_retries": _parse_int_env("WATERCOOLER_MAX_SYNC_RETRIES", 5),
            "max_backoff": _parse_float_env("WATERCOOLER_MAX_BACKOFF", 300.0),
            "log_enabled": self._log_enabled,
            "sync_interval": _parse_float_env("WATERCOOLER_SYNC_INTERVAL", 30.0),
            "stale_threshold": _parse_float_env("WATERCOOLER_STALE_THRESHOLD", 60.0),
        }

    def _init_async(self) -> None:
        if self._async is not None:
            return
        self._async = _AsyncSyncCoordinator(self, **self._async_config)

    def _ensure_local_repo_ready(self) -> None:
        """Re-initialise the repository if the working tree was removed."""
        git_dir = self.local_path / ".git"
        if git_dir.exists():
            return
        self._initialise_repository()

    def _initialise_repository(self) -> None:
        """Prepare the local git repository, preferring remote clone when possible."""
        git_dir = self.local_path / ".git"
        if git_dir.exists():
            return

        if self._try_clone_remote():
            return

        self._bootstrap_local_repo()

    def _try_clone_remote(self) -> bool:
        """Attempt to clone the remote threads repository.

        Returns True on success, False if the remote is unavailable or clone fails.
        """
        try:
            self._clone()
            return True
        except GitSyncError:
            if self._provision_enabled:
                raise
            return False

    def _clone(self):
        """Clone the watercooler repository using GitPython (no subprocess).

        Raises:
            GitSyncError: If clone fails
        """
        self._log(f"Cloning {self.repo_url} to {self.local_path}")
        try:
            # If directory exists but isn't a git repo, remove it first
            if self.local_path.exists() and not (self.local_path / ".git").exists():
                import shutil
                shutil.rmtree(self.local_path)

            # Ensure parent directories exist for the clone target
            parent = self.local_path.parent
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            # Use GitPython to clone (in-process, no subprocess)
            # Configure environment for the clone operation
            _diag(f"GIT_OP_START: clone {self.repo_url}")
            with git.Git().custom_environment(**self._env):
                Repo.clone_from(
                    self.repo_url,
                    self.local_path,
                    env=self._env
                )
            _diag(f"GIT_OP_END: clone {self.repo_url}")
            self._log(f"Clone completed successfully")
        except GitCommandError as e:
            # Check if we should attempt provisioning
            if self._should_attempt_provision(e):
                self._handle_provisioning_clone_gitpython(e)
                return
            message = f"Failed to clone {self.repo_url}: {e}"
            raise GitSyncError(message) from e
        except Exception as e:
            message = f"Failed to clone {self.repo_url}: {e}"
            raise GitSyncError(message) from e

    def _format_process_error(
        self,
        error: subprocess.CalledProcessError,
        *,
        prefix: str | None = None,
    ) -> str:
        parts = [error.stderr or "", error.stdout or ""]
        body = "\n".join(p.strip() for p in parts if p and p.strip())
        if prefix:
            return f"{prefix}: {body}" if body else prefix
        return body

    def _should_attempt_provision(self, error: GitCommandError) -> bool:
        """Check if we should attempt auto-provisioning based on GitCommandError."""
        if not self._provision_enabled or not self._remote_allowed:
            return False
        # GitCommandError stores error message as string
        text = str(error).strip().lower()
        if not text:
            return False
        if "repository not found" in text:
            return True
        if "repository" in text and "not found" in text:
            return True
        return "repository" in text and "does not exist" in text

    def _handle_provisioning_clone(self, error: subprocess.CalledProcessError) -> None:
        if not self._remote_allowed or not self._provision_enabled:
            self._bootstrap_local_repo()
            return
        try:
            output = provision_threads_repo(
                repo_url=self.repo_url,
                slug=self.threads_slug,
                code_repo=self.code_repo,
                env=self._env,
            )
            self._last_provision_output = output or None
        except ProvisioningError as provision_error:
            message = self._format_process_error(
                error,
                prefix=(
                    f"Failed to clone {self.repo_url}; "
                    f"auto-provision attempt aborted: {provision_error}"
                ),
            )
            raise GitSyncError(message) from provision_error

        # After provisioning, retry clone with GitPython (no subprocess).
        # If the remote is still empty, fall back to bootstrapping a local repo.
        try:
            with git.Git().custom_environment(**self._env):
                Repo.clone_from(
                    self.repo_url,
                    self.local_path,
                    env=self._env
                )
            return
        except GitCommandError as retry_error:
            combined = str(retry_error)
            if combined:
                self._last_provision_output = (
                    (self._last_provision_output or "") + "\n" + combined
                ).strip()
            try:
                if self.local_path.exists() and not (self.local_path / ".git").exists():
                    import shutil
                    shutil.rmtree(self.local_path)
                self._bootstrap_local_repo()
            except Exception as bootstrap_exc:  # pragma: no cover - defensive
                message = (
                    self._last_provision_output
                    or "Provisioned threads repo but bootstrap failed"
                )
                raise GitSyncError(message) from bootstrap_exc

    def _handle_provisioning_clone_gitpython(self, error: GitCommandError) -> None:
        """Handle provisioning when GitPython reports a missing repository."""
        if not self._remote_allowed or not self._provision_enabled:
            self._bootstrap_local_repo()
            return

        try:
            output = provision_threads_repo(
                repo_url=self.repo_url,
                slug=self.threads_slug,
                code_repo=self.code_repo,
                env=self._env,
            )
            if output:
                self._last_provision_output = output
        except ProvisioningError as provision_error:
            message = (
                f"Failed to clone {self.repo_url}; auto-provision attempt aborted: "
                f"{provision_error}"
            )
            raise GitSyncError(message) from provision_error

        # After provisioning, retry clone. If it still fails, bootstrap locally.
        try:
            with git.Git().custom_environment(**self._env):
                Repo.clone_from(
                    self.repo_url,
                    self.local_path,
                    env=self._env,
                )
            return
        except GitCommandError as retry_error:
            message = str(retry_error)
            if message:
                self._last_provision_output = (
                    (self._last_provision_output or "") + "\n" + message
                ).strip()
            self._bootstrap_local_repo()

    def _bootstrap_local_repo(self) -> None:
        """Initialize local git repository using GitPython (no subprocess)."""
        self._log("Bootstrapping local repository")
        parent = self.local_path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        if not self.local_path.exists():
            self.local_path.mkdir(parents=True, exist_ok=True)

        # Use GitPython to init
        repo = Repo.init(self.local_path)

        # Add remote if not present
        if 'origin' not in [remote.name for remote in repo.remotes]:
            repo.create_remote('origin', self.repo_url)
        self._log("Local repository bootstrapped")

    def set_remote_allowed(self, allowed: bool) -> None:
        """Toggle whether remote interactions are permitted."""
        self._remote_allowed = bool(allowed)

    def _ensure_remote_repo_exists(self) -> bool:
        """Ensure the remote repository exists before network operations (GitPython, no subprocess).

        Returns True if the remote appears accessible (post-provisioning when
        enabled). Returns False if the remote is unavailable and cannot be
        auto-provisioned.
        """
        self._remote_missing = False
        self._last_remote_error = None
        self._remote_empty = False

        if not self._remote_allowed:
            self._remote_missing = True
            return False

        try:
            repo = self._repo
            origin = repo.remotes.origin

            # Use GitPython to list remote refs (equivalent to git ls-remote)
            _diag("GIT_OP_START: ls-remote (via origin.refs)")
            with git.Git().custom_environment(**self._env):
                refs = origin.refs
                self._remote_empty = len(refs) == 0
            _diag(f"GIT_OP_END: ls-remote (found {len(refs)} refs)")
            return True
        except GitCommandError as error:
            self._remote_empty = False
            message = str(error)
            lowered = (message or "").lower()

            if self._should_attempt_provision(error):
                try:
                    output = provision_threads_repo(
                        repo_url=self.repo_url,
                        slug=self.threads_slug,
                        code_repo=self.code_repo,
                        env=self._env,
                    )
                    if output:
                        self._last_provision_output = output

                    # Retry with GitPython after provisioning
                    repo = self._repo
                    origin = repo.remotes.origin
                    with git.Git().custom_environment(**self._env):
                        refs = origin.refs
                        self._remote_empty = len(refs) == 0
                    return True
                except ProvisioningError as provision_error:
                    self._last_provision_output = str(provision_error)
                    self._last_remote_error = self._last_provision_output
                    return False
                except GitCommandError as retry_error:
                    retry_message = str(retry_error)
                    self._last_remote_error = (
                        retry_message
                        or message
                        or "Unable to verify provisioned threads repository"
                    )
                    return False

            if "not found" in lowered or "repository" in lowered and "not found" in lowered:
                self._remote_missing = True
                self._last_remote_error = message or "Remote threads repository not found"
                return False

            self._last_remote_error = message or "Unable to contact remote threads repository"
            return False

    def _configure_git(self):
        """Configure git user for commits using GitPython (no subprocess).

        Raises:
            GitSyncError: If configuration fails
        """
        self._log("Configuring git user")
        try:
            repo = self._repo
            with repo.config_writer() as config:
                config.set_value('user', 'name', self.author_name)
                config.set_value('user', 'email', self.author_email)
            self._log("Git user configured")
        except Exception as e:
            raise GitSyncError(f"Failed to configure git: {e}") from e

    def pull(self) -> bool:
        """Pull latest changes from remote with rebase.

        Uses --rebase --autostash to:
        - Replay local commits on top of remote changes
        - Automatically stash and re-apply local modifications

        Returns:
            True if pull succeeded, False if rebase failed

        Note:
            On rebase failure, automatically aborts the rebase and returns False.
            Caller should handle this gracefully (e.g., retry, alert user).
        """
        self._last_pull_error = None

        if not self._remote_allowed:
            return True

        self._ensure_local_repo_ready()

        remote_available = self._ensure_remote_repo_exists()
        if not remote_available:
            if self._remote_missing:
                return True
            self._last_pull_error = (
                self._last_remote_error
                or "remote threads repository unavailable"
            )
            return False

        if self._remote_empty:
            return True

        # Use GitPython to pull (in-process, no subprocess)
        self._log("Pulling with rebase and autostash")
        try:
            repo = self._repo
            _diag("GIT_OP_START: fetch origin")
            with git.Git().custom_environment(**self._env):
                # Fetch first
                repo.remotes.origin.fetch()
            _diag("GIT_OP_END: fetch origin")
            _diag("GIT_OP_START: pull --rebase --autostash")
            with git.Git().custom_environment(**self._env):
                # Pull with rebase
                repo.git.pull('--rebase', '--autostash', env=self._env)
            _diag("GIT_OP_END: pull --rebase --autostash")
            self._log("Pull completed successfully")
            return True
        except GitCommandError as e:
            error_text = str(e).lower()
            # Fallback: explicitly specify remote/branch when git cannot infer upstream
            # This occurs when multiple refs match the branch name (e.g., remotes/origin/main and remotes/fork/main)
            if "cannot rebase onto multiple branches" in error_text:
                self._log("Pull failed due to ambiguous upstream; retrying with explicit remote/branch")
                try:
                    tracking = None
                    try:
                        tracking = repo.active_branch.tracking_branch()
                    except (AttributeError, TypeError):
                        # Could not determine tracking branch, will use defaults
                        self._log("Warning: Could not determine tracking branch, using defaults (origin/<branch>)")
                        tracking = None
                    remote_name = "origin"
                    remote_branch = repo.active_branch.name
                    if tracking is not None:
                        remote_name = tracking.remote_name or remote_name
                        remote_branch = tracking.remote_head or remote_branch
                    _diag(
                        f"GIT_OP_RETRY: pull --rebase --autostash {remote_name} {remote_branch}"
                    )
                    with git.Git().custom_environment(**self._env):
                        repo.git.pull(
                            remote_name,
                            remote_branch,
                            '--rebase',
                            '--autostash',
                            env=self._env,
                        )
                    self._log("Fallback pull completed successfully")
                    return True
                except GitCommandError as retry_error:
                    # Retry failed, continue with normal error handling using the retry error
                    self._log(f"Fallback pull also failed: {str(retry_error)}")
                    error_text = str(retry_error).lower()
                    e = retry_error
            # Handle various non-error conditions
            if "couldn't find remote ref" in error_text or "could not find remote ref" in error_text:
                return True
            if "does not match any" in error_text:
                return True
            if "no tracking information for the current branch" in error_text:
                return True
            # Network errors
            network_tokens = (
                "could not read from remote repository",
                "could not resolve hostname",
                "permission denied",
                "network is unreachable",
                "failed to connect to",
                "failed in sandbox",
            )
            if any(token in error_text for token in network_tokens):
                self._last_pull_error = str(e) or "network failure contacting remote threads repository"
                self._last_remote_error = self._last_pull_error
                return False
            self._last_pull_error = str(e)
            self._last_remote_error = self._last_pull_error
            # Rebase conflict or other pull failure - abort any in-progress rebase
            self._log(f"Pull failed: {e}, aborting rebase")
            try:
                repo.git.rebase('--abort')
            except:
                pass
            return False
        except Exception as e:
            self._last_pull_error = f"Unexpected error during pull: {e}"
            return False

    def commit_local(self, message: str) -> bool:
        """Commit staged changes locally without pushing (GitPython, no subprocess).

        Returns True if a commit was created, False if there were no staged changes.
        Raises GitSyncError if git commit fails.
        """
        self._log(f"Committing: {message[:60]}...")
        try:
            repo = self._repo
            _diag("GIT_OP_START: add -A")
            with git.Git().custom_environment(**self._env):
                # Stage all changes within local_path
                repo.git.add('-A')
            _diag("GIT_OP_END: add -A")

            # Check if there are changes to commit
            if not repo.is_dirty(untracked_files=True):
                self._log("No changes to commit")
                return False

            _diag(f"GIT_OP_START: commit -m '{message[:40]}'")
            with git.Git().custom_environment(**self._env):
                # Commit changes
                repo.git.commit('-m', message, env=self._env)
            _diag(f"GIT_OP_END: commit")
            self._log("Commit completed successfully")
        except GitCommandError as e:
            raise GitSyncError(f"Failed to commit: {e}") from e
        except Exception as e:
            raise GitSyncError(f"Failed to commit: {e}") from e
        return True

    def push_pending(self, max_retries: int = 3) -> bool:
        """Push local commits to the remote with retry logic."""
        self._last_push_error = None
        if not self._remote_allowed:
            return True

        self._ensure_local_repo_ready()

        remote_available = self._ensure_remote_repo_exists()
        if not remote_available:
            if self._remote_missing:
                return True
            self._last_push_error = (
                self._last_remote_error
                or "remote threads repository unavailable"
            )
            return False

        # Use GitPython to push (in-process, no subprocess)
        for attempt in range(max_retries):
            self._log(f"Pushing (attempt {attempt+1}/{max_retries})")
            try:
                repo = self._repo
                _diag(f"GIT_OP_START: push (attempt {attempt+1})")
                with git.Git().custom_environment(**self._env):
                    repo.remotes.origin.push(env=self._env)
                _diag(f"GIT_OP_END: push (attempt {attempt+1})")
                self._log("Push completed successfully")
                return True

            except GitCommandError as e:
                error_text = str(e).lower()

                # Network errors
                network_tokens = (
                    "could not read from remote repository",
                    "could not resolve hostname",
                    "permission denied",
                    "network is unreachable",
                    "failed to connect to",
                    "failed in sandbox",
                )
                if any(token in error_text for token in network_tokens):
                    self._last_push_error = str(e) or "network failure contacting remote threads repository"
                    return False

                # Handle missing upstream / no configured push destination
                if ("has no upstream branch" in error_text or
                    "no configured push destination" in error_text or
                    "does not match any" in error_text):
                    self._log("Setting upstream branch")
                    try:
                        repo.git.push('-u', 'origin', 'HEAD', env=self._env)
                        self._log("Upstream set successfully")
                        return True
                    except GitCommandError as push_error:
                        self._last_push_error = str(push_error) or "failed to set upstream for threads branch"
                        if attempt >= max_retries - 1:
                            return False
                        continue

                if attempt < max_retries - 1:
                    # Push rejected - pull and retry
                    self._log("Push rejected, pulling before retry")
                    if not self.pull():
                        # Pull failed (rebase conflict or no upstream yet)
                        # Give one more chance on next loop iteration
                        pass
                    # Small exponential backoff to reduce contention
                    try:
                        time.sleep(0.25 * (2 ** attempt))
                    except Exception:
                        pass
                    continue

                self._last_push_error = str(e) or "failed to push threads updates"
                # Max retries exceeded
                return False
        return False

    def commit_and_push(self, message: str, max_retries: int = 3) -> bool:
        """Commit changes and push to remote with retry logic."""
        committed = self.commit_local(message)
        if not committed:
            return True
        return self.push_pending(max_retries=max_retries)

    def ensure_branch(self, branch: str) -> bool:
        """Ensure the local repo is on the given branch, creating it if needed (GitPython, no subprocess).

        Also sets upstream to origin/<branch> on first creation.
        Returns True on success, False on failure (non-fatal; caller can proceed).
        """
        try:
            self._ensure_local_repo_ready()
            repo = self._repo

            # What branch are we on now?
            current = repo.active_branch.name
            if current == branch:
                return True

            # Does the branch exist locally?
            exists = branch in [ref.name for ref in repo.heads]

            remote_available = self._remote_allowed and self._ensure_remote_repo_exists()
            remote_has_branch = False

            if remote_available:
                # Check if remote has the branch
                with git.Git().custom_environment(**self._env):
                    origin = repo.remotes.origin
                    remote_has_branch = f"origin/{branch}" in [ref.name for ref in origin.refs]

            if exists:
                # Checkout existing local branch
                _diag(f"GIT_OP_START: checkout {branch}")
                with git.Git().custom_environment(**self._env):
                    repo.git.checkout(branch, env=self._env)
                _diag(f"GIT_OP_END: checkout {branch}")
            else:
                if remote_has_branch:
                    # Fetch and checkout remote branch
                    _diag(f"GIT_OP_START: fetch {branch}")
                    with git.Git().custom_environment(**self._env):
                        origin = repo.remotes.origin
                        origin.fetch(refspec=f"{branch}:refs/heads/{branch}", env=self._env)
                    _diag(f"GIT_OP_END: fetch {branch}")
                    _diag(f"GIT_OP_START: checkout {branch}")
                    with git.Git().custom_environment(**self._env):
                        repo.git.checkout(branch, env=self._env)
                    _diag(f"GIT_OP_END: checkout {branch}")
                else:
                    # Create new branch
                    _diag(f"GIT_OP_START: checkout -b {branch}")
                    with git.Git().custom_environment(**self._env):
                        repo.git.checkout('-b', branch, env=self._env)
                    _diag(f"GIT_OP_END: checkout -b {branch}")

            # Ensure upstream is set when remote branch exists
            try:
                # Check if upstream is set (will raise if not)
                repo.active_branch.tracking_branch()
                has_upstream = True
            except (AttributeError, TypeError):
                has_upstream = False

            if not has_upstream and remote_has_branch:
                # Set upstream to origin/branch
                with git.Git().custom_environment(**self._env):
                    repo.git.branch('--set-upstream-to', f'origin/{branch}', branch, env=self._env)
            elif not has_upstream and self._remote_allowed and not remote_has_branch:
                # Remote unavailable or branch missing - leave as-is (local-only)
                pass
            return True
        except Exception:
            return False

    def with_sync(
        self,
        operation: Callable[[], T],
        commit_message: str,
        *,
        topic: Optional[str] = None,
        entry_id: Optional[str] = None,
        priority_flush: bool = False,
    ) -> T:
        """Execute operation with git synchronization.

        When async mode is disabled this preserves the legacy behaviour of
        pull → operation → commit → push. When async mode is enabled the
        operation is executed immediately, the commit is recorded locally, and
        a background worker pushes it to the remote (flushing immediately for
        priority operations such as ball hand-offs).
        """
        if self._async is None:
            return self._with_sync_sync(
                operation,
                commit_message,
            )

        return self._with_sync_async(
            operation,
            commit_message,
            topic=topic,
            entry_id=entry_id,
            priority_flush=priority_flush,
        )

    def _with_sync_sync(self, operation: Callable[[], T], commit_message: str) -> T:
        if not self.pull():
            detail = self._last_pull_error or "unknown error"
            raise GitPullError(
                f"Failed to pull latest changes before operation: {detail}"
            )

        result = operation()

        if not self.commit_and_push(commit_message):
            detail = self._last_push_error or "unknown push error"
            raise GitPushError(f"Failed to push changes: {detail}")

        return result

    def _with_sync_async(
        self,
        operation: Callable[[], T],
        commit_message: str,
        *,
        topic: Optional[str],
        entry_id: Optional[str],
        priority_flush: bool,
    ) -> T:
        if self._async is None:
            return self._with_sync_sync(operation, commit_message)

        self._ensure_local_repo_ready()
        result = operation()

        committed = self.commit_local(commit_message)
        if committed:
            self._async.enqueue_commit(
                commit_message=commit_message,
                topic=topic,
                entry_id=entry_id,
                priority_flush=priority_flush,
            )
            if priority_flush:
                self._async.flush_now()
        elif priority_flush:
            # No commit was produced but we must honor the caller's expectation
            # that remote state is consistent (e.g., ball hand-off without body).
            self._async.flush_now()

        return result

    def flush_async(self, timeout: Optional[float] = None) -> None:
        """Force the async worker to push queued commits immediately."""
        if self._async is None:
            raise GitPushError("Async sync is disabled for this repository")
        self._async.flush_now(timeout=timeout or 60.0)

    def get_async_status(self) -> dict:
        """Return diagnostic information about the async queue."""
        if self._async is None:
            return {
                "mode": "sync",
                "pending": 0,
                 "pending_topics": [],
                "priority": False,
                "retry_at": None,
                "retry_in_seconds": None,
                "last_error": None,
                 "last_pull": None,
                 "last_pull_age_seconds": None,
                 "stale": False,
                 "stale_threshold": self._async_config.get("stale_threshold"),
                 "next_pull_eta_seconds": None,
                 "is_syncing": False,
                 "sync_interval": self._async_config.get("sync_interval"),
            }
        return self._async.status()


def _detect_squash_merge(code_repo_obj: Repo, branch: str) -> tuple[bool, str | None]:
    """Detect if a code branch was squash-merged to main.
    
    Args:
        code_repo_obj: GitPython Repo object for code repository
        branch: Branch name to check
        
    Returns:
        Tuple of (is_squash_merged, squash_commit_sha)
        Returns (False, None) if branch doesn't exist or wasn't merged
    """
    try:
        if branch not in [b.name for b in code_repo_obj.heads]:
            return (False, None)
        
        if "main" not in [b.name for b in code_repo_obj.heads]:
            return (False, None)
        
        # Get commits on feature branch that aren't on main
        feature_commits = list(code_repo_obj.iter_commits(f"main..{branch}"))
        if not feature_commits:
            # Branch is fully merged or has no unique commits
            return (False, None)
        
        # Check if any of these commits exist on main (by message or content)
        # If none exist, it's likely a squash merge
        main_commits = list(code_repo_obj.iter_commits("main", max_count=50))
        main_commit_shas = {c.hexsha for c in main_commits}
        main_commit_messages = {c.message.strip() for c in main_commits}
        
        # Check if feature branch commits exist on main
        feature_commits_on_main = 0
        for commit in feature_commits[:10]:  # Check first 10 commits
            if commit.hexsha in main_commit_shas:
                feature_commits_on_main += 1
            elif commit.message.strip() in main_commit_messages:
                # Same message might indicate squash
                feature_commits_on_main += 1
        
        # If no feature commits exist on main, likely squash merge
        if feature_commits_on_main == 0 and len(feature_commits) > 1:
            # Find the merge commit on main that might be the squash
            for commit in main_commits[:20]:
                if branch.lower() in commit.message.lower() or "squash" in commit.message.lower():
                    return (True, commit.hexsha[:7])
            # Return True but no specific commit
            return (True, None)
        
        return (False, None)
    except Exception:
        return (False, None)


def _fuzzy_match_branches(branch1: str, branch2: str) -> float:
    """Calculate similarity score between two branch names.
    
    Uses simple character-based similarity (ratio of common characters).
    Returns a score between 0.0 and 1.0, where 1.0 is exact match.
    
    Args:
        branch1: First branch name
        branch2: Second branch name
        
    Returns:
        Similarity score (0.0 to 1.0)
    """
    # Normalize branch names (lowercase, remove common prefixes)
    def normalize(name: str) -> str:
        name = name.lower()
        # Remove common prefixes
        for prefix in ['feature/', 'feat/', 'fix/', 'bugfix/', 'hotfix/', 'release/']:
            if name.startswith(prefix):
                name = name[len(prefix):]
        return name
    
    norm1 = normalize(branch1)
    norm2 = normalize(branch2)
    
    if norm1 == norm2:
        return 1.0
    
    # Simple character overlap calculation
    set1 = set(norm1)
    set2 = set(norm2)
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def _detect_branch_rename(
    code_repo_obj: Repo,
    threads_repo_obj: Repo,
    code_branch: str | None,
    threads_branch: str | None,
) -> tuple[bool, str | None, float]:
    """Detect if a branch was renamed by finding similar branch names.
    
    Args:
        code_repo_obj: GitPython Repo object for code repository
        threads_repo_obj: GitPython Repo object for threads repository
        code_branch: Current code branch name (or None)
        threads_branch: Current threads branch name (or None)
        
    Returns:
        Tuple of (is_rename, suggested_branch, similarity_score)
        Returns (False, None, 0.0) if no rename detected
    """
    if not code_branch or not threads_branch:
        return (False, None, 0.0)
    
    try:
        # Get all branches from both repos
        code_branches = {b.name for b in code_repo_obj.heads}
        threads_branches = {b.name for b in threads_repo_obj.heads}
        
        # If branches match exactly, no rename
        if code_branch in threads_branches and threads_branch in code_branches:
            return (False, None, 0.0)
        
        # Check if code branch exists in threads repo with different name
        if code_branch not in threads_branches:
            # Find most similar branch in threads repo
            best_match = None
            best_score = 0.0
            for thread_branch in threads_branches:
                score = _fuzzy_match_branches(code_branch, thread_branch)
                if score > best_score and score > 0.6:  # Threshold for similarity
                    best_score = score
                    best_match = thread_branch
            
            if best_match:
                return (True, best_match, best_score)
        
        # Check if threads branch exists in code repo with different name
        if threads_branch not in code_branches:
            # Find most similar branch in code repo
            best_match = None
            best_score = 0.0
            for code_branch_candidate in code_branches:
                score = _fuzzy_match_branches(threads_branch, code_branch_candidate)
                if score > best_score and score > 0.6:  # Threshold for similarity
                    best_score = score
                    best_match = code_branch_candidate
            
            if best_match:
                return (True, best_match, best_score)
        
        return (False, None, 0.0)
    except Exception:
        return (False, None, 0.0)


def validate_branch_pairing(
    code_repo: Path,
    threads_repo: Path,
    strict: bool = True,
) -> BranchPairingResult:
    """Validate that code and threads repos are on matching branches.

    Args:
        code_repo: Path to code repository root
        threads_repo: Path to threads repository root (or .watercooler directory)
        strict: If True, return valid=False on any mismatch. If False, only return
                valid=False on critical errors.

    Returns:
        BranchPairingResult with validation status, branch names, and any mismatches
    """
    mismatches: List[BranchMismatch] = []
    warnings: List[str] = []

    # Get code repo branch
    code_branch: Optional[str] = None
    try:
        code_repo_obj = Repo(code_repo, search_parent_directories=True)
        if code_repo_obj.head.is_detached:
            warnings.append("Code repo is in detached HEAD state")
        else:
            code_branch = code_repo_obj.active_branch.name
    except InvalidGitRepositoryError:
        mismatches.append(BranchMismatch(
            type="code_repo_not_git",
            code=None,
            threads=None,
            severity="error",
            recovery=f"Code path {code_repo} is not a git repository"
        ))
        return BranchPairingResult(
            valid=False,
            code_branch=None,
            threads_branch=None,
            mismatches=mismatches,
            warnings=warnings,
        )
    except Exception as e:
        mismatches.append(BranchMismatch(
            type="code_repo_error",
            code=None,
            threads=None,
            severity="error",
            recovery=f"Failed to read code repo: {str(e)}"
        ))
        return BranchPairingResult(
            valid=False,
            code_branch=None,
            threads_branch=None,
            mismatches=mismatches,
            warnings=warnings,
        )

    # Get threads repo branch
    threads_branch: Optional[str] = None
    try:
        threads_repo_obj = Repo(threads_repo, search_parent_directories=True)
        if threads_repo_obj.head.is_detached:
            warnings.append("Threads repo is in detached HEAD state")
        else:
            threads_branch = threads_repo_obj.active_branch.name
    except InvalidGitRepositoryError:
        mismatches.append(BranchMismatch(
            type="threads_repo_not_git",
            code=code_branch,
            threads=None,
            severity="error",
            recovery=f"Threads path {threads_repo} is not a git repository"
        ))
        return BranchPairingResult(
            valid=False,
            code_branch=code_branch,
            threads_branch=None,
            mismatches=mismatches,
            warnings=warnings,
        )
    except Exception as e:
        mismatches.append(BranchMismatch(
            type="threads_repo_error",
            code=code_branch,
            threads=None,
            severity="error",
            recovery=f"Failed to read threads repo: {str(e)}"
        ))
        return BranchPairingResult(
            valid=False,
            code_branch=code_branch,
            threads_branch=None,
            mismatches=mismatches,
            warnings=warnings,
        )

    # Compare branches
    if code_branch is None and threads_branch is None:
        # Both in detached HEAD - this is a warning, not an error
        warnings.append("Both repos in detached HEAD state")
        return BranchPairingResult(
            valid=not strict,
            code_branch=None,
            threads_branch=None,
            mismatches=mismatches,
            warnings=warnings,
        )

    if code_branch is None:
        mismatches.append(BranchMismatch(
            type="code_branch_detached",
            code=None,
            threads=threads_branch,
            severity="error",
            recovery="Checkout a branch in code repo or create one"
        ))
    elif threads_branch is None:
        mismatches.append(BranchMismatch(
            type="threads_branch_detached",
            code=code_branch,
            threads=None,
            severity="error",
            recovery=f"Checkout branch '{code_branch}' in threads repo"
        ))
    elif code_branch != threads_branch:
        # Check for potential branch rename
        is_rename, suggested_branch, similarity = _detect_branch_rename(
            code_repo_obj, threads_repo_obj, code_branch, threads_branch
        )
        
        if is_rename and suggested_branch:
            recovery_msg = (
                f"Possible branch rename detected (similarity: {similarity:.0%}). "
                f"Suggested branch: '{suggested_branch}'. "
                f"Run: watercooler_v1_sync_branch_state with operation='checkout' and branch='{suggested_branch}'"
            )
            warnings.append(
                f"Branch name mismatch may be due to rename: '{code_branch}' vs '{threads_branch}' "
                f"(suggested: '{suggested_branch}')"
            )
        else:
            recovery_msg = (
                f"Run: watercooler_v1_sync_branch_state with operation='checkout' to sync branches"
            )
        
        mismatches.append(BranchMismatch(
            type="branch_name_mismatch",
            code=code_branch,
            threads=threads_branch,
            severity="error",
            recovery=recovery_msg
        ))

    # Determine validity
    has_errors = any(m.severity == "error" for m in mismatches)
    valid = not has_errors if strict else len(mismatches) == 0

    return BranchPairingResult(
        valid=valid,
        code_branch=code_branch,
        threads_branch=threads_branch,
        mismatches=mismatches,
        warnings=warnings,
    )


class _AsyncSyncCoordinator:
    """Background worker that batches git push operations."""

    def __init__(
        self,
        manager: "GitSyncManager",
        *,
        batch_window: float,
        max_delay: float,
        max_batch_size: int,
        max_sync_retries: int,
        max_backoff: float,
        log_enabled: bool,
        sync_interval: float,
        stale_threshold: float,
    ) -> None:
        self._manager = manager
        self._batch_window = batch_window
        self._max_delay = max_delay
        self._max_batch_size = max_batch_size
        self._max_sync_retries = max_sync_retries
        self._max_backoff = max_backoff
        self._log_enabled = log_enabled
        self._sync_interval = max(1.0, sync_interval)
        self._stale_threshold = max(1.0, stale_threshold)

        self._lock = threading.RLock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()

        self._pending: list[_PendingCommit] = []
        self._next_sequence = 1
        self._last_flushed_sequence = 0
        self._priority_flush = False
        self._retry_at: Optional[float] = None
        self._current_backoff = self._batch_window
        self._last_error: Optional[str] = None
        self._last_error_sequence: int = 0
        self._last_pull: float = 0.0
        self._next_pull_due: float = time.time()
        self._is_syncing: bool = False

        self._queue_dir = manager.local_path.parent / ".watercooler-pending-sync"
        self._queue_file = self._queue_dir / "queue.jsonl"
        self._log_path = self._queue_dir / "async-sync.log"

        self._load_queue()
        if not self._pending:
            # Ensure we still wake for the first scheduled pull.
            self._wake_event.set()

        self._worker = threading.Thread(
            target=self._worker_loop,
            name=f"watercooler-async-sync-{id(self)}",
            daemon=True,
        )
        self._worker.start()
        atexit.register(self.shutdown)

        # Kick worker if we already had pending items from disk.
        if self._pending:
            self._wake_event.set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue_commit(
        self,
        *,
        commit_message: str,
        topic: Optional[str],
        entry_id: Optional[str],
        priority_flush: bool,
    ) -> None:
        timestamp = _now_iso()
        created_ts = time.time()

        with self._lock:
            sequence = self._next_sequence
            self._next_sequence += 1
            commit = _PendingCommit(
                sequence=sequence,
                entry_id=entry_id,
                topic=topic,
                commit_message=commit_message,
                timestamp=timestamp,
                created_ts=created_ts,
            )
            self._pending.append(commit)
            self._append_to_queue_locked(commit)
            if priority_flush:
                self._priority_flush = True
                # Reset retry timer – priority flush should try immediately.
                self._retry_at = None

        self._wake_event.set()

    def flush_now(self, timeout: float = 60.0) -> None:
        """Block until all commits currently queued are pushed."""
        target_sequence: Optional[int]
        with self._lock:
            if not self._pending:
                self._last_error = None
                self._priority_flush = False
                return
            target_sequence = self._pending[-1].sequence
            self._priority_flush = True
            self._retry_at = None

        self._wake_event.set()
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._last_error and self._last_error_sequence >= (target_sequence or 0):
                    error = self._last_error
                    # Keep error so subsequent callers can see it
                    raise GitPushError(error)
                if self._last_flushed_sequence >= (target_sequence or 0):
                    return
            time.sleep(0.05)

        with self._lock:
            error = self._last_error or "timeout waiting for async sync flush"
        raise GitPushError(error)

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self._wake_event.set()
        try:
            if self._pending:
                self.flush_now(timeout=self._max_delay)
        except GitPushError:
            # Best-effort during shutdown
            pass
        if self._worker.is_alive():
            try:
                self._worker.join(timeout=2.0)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            timeout = self._time_until_next_action()
            self._wake_event.wait(timeout=timeout)
            self._wake_event.clear()
            try:
                self._process_once()
            except Exception as exc:  # pragma: no cover - defensive logging
                self._log(f"worker error: {exc}")

    def _time_until_next_action(self) -> float:
        now = time.time()
        with self._lock:
            if self._stop_event.is_set():
                return 0.1
            if self._priority_flush:
                return 0.05
            if self._retry_at is not None and now < self._retry_at:
                wait = self._retry_at - now
                return max(0.05, min(wait, 1.0))
            if self._pending:
                oldest = self._pending[0]
                if len(self._pending) >= self._max_batch_size:
                    return 0.05
                age = now - oldest.created_ts
                flush_due = min(
                    oldest.created_ts + self._batch_window,
                    oldest.created_ts + self._max_delay,
                )
                wait = flush_due - now
                if wait <= 0:
                    return 0.05
                return max(0.05, min(wait, 1.0))
            wait = self._next_pull_due - now
            if wait <= 0:
                return 0.05
            return max(0.05, min(wait, 1.0))

    def _process_once(self) -> None:
        now = time.time()
        with self._lock:
            if self._retry_at is not None and now < self._retry_at:
                return
            pending_count = len(self._pending)
            priority = self._priority_flush
            target_sequence = self._pending[-1].sequence if pending_count else None
            oldest_created = self._pending[0].created_ts if pending_count else None
            due_pull = now >= self._next_pull_due

        if priority or self._should_flush(now, pending_count, oldest_created):
            self._execute_flush(target_sequence)
            return

        if due_pull:
            self._execute_pull()

    def _should_flush(self, now: float, pending_count: int, oldest_created: Optional[float]) -> bool:
        if pending_count == 0:
            return False
        with self._lock:
            if self._priority_flush:
                return True
        if pending_count >= self._max_batch_size:
            return True
        if oldest_created is None:
            return False
        age = now - oldest_created
        if age >= self._max_delay:
            return True
        if age >= self._batch_window:
            return True
        return False

    def _execute_flush(self, target_sequence: Optional[int]) -> None:
        if target_sequence is None:
            with self._lock:
                self._priority_flush = False
            return

        success = self._perform_sync()

        with self._lock:
            if success:
                self._pending = [commit for commit in self._pending if commit.sequence > target_sequence]
                self._rewrite_queue_locked()
                self._last_flushed_sequence = max(self._last_flushed_sequence, target_sequence)
                self._priority_flush = False
                self._retry_at = None
                self._current_backoff = self._batch_window
                self._last_error = None
                self._last_error_sequence = 0
            else:
                now = time.time()
                self._current_backoff = min(self._current_backoff * 2, self._max_backoff)
                self._retry_at = now + self._current_backoff
                self._last_error = (
                    self._manager._last_push_error
                    or self._manager._last_pull_error
                    or "async sync failed"
                )
                self._last_error_sequence = target_sequence

    def _execute_pull(self) -> None:
        if self._perform_pull():
            return
        with self._lock:
            now = time.time()
            self._current_backoff = min(self._current_backoff * 2, self._max_backoff)
            self._retry_at = now + self._current_backoff
            self._last_error = (
                self._manager._last_pull_error
                or "async pull failed"
            )
            self._last_error_sequence = 0

    def _perform_sync(self) -> bool:
        pull_time = time.time()
        self._set_syncing(True)
        try:
            if not self._manager.pull():
                return False
            self._record_pull_success(pull_time)
            if not self._manager.push_pending(max_retries=self._max_sync_retries):
                return False
            return True
        finally:
            self._set_syncing(False)

    def _perform_pull(self) -> bool:
        pull_time = time.time()
        self._set_syncing(True)
        try:
            if not self._manager.pull():
                return False
            self._record_pull_success(pull_time)
            return True
        finally:
            self._set_syncing(False)

    def _record_pull_success(self, pull_time: float) -> None:
        with self._lock:
            self._last_pull = pull_time
            self._next_pull_due = pull_time + self._sync_interval
            self._retry_at = None
            self._current_backoff = self._batch_window
            if self._last_error_sequence == 0:
                self._last_error = None

    def _set_syncing(self, value: bool) -> None:
        with self._lock:
            self._is_syncing = value

    def status(self) -> dict:
        now = time.time()
        with self._lock:
            pending = len(self._pending)
            pending_topics = sorted({commit.topic for commit in self._pending if commit.topic})
            priority = self._priority_flush
            oldest_ts = self._pending[0].timestamp if pending else None
            retry_at = self._retry_at
            last_error = self._last_error
            last_pull = self._last_pull
            next_pull_due = self._next_pull_due
            is_syncing = self._is_syncing
        retry_in = None
        if retry_at is not None:
            remaining = retry_at - now
            retry_in = remaining if remaining > 0 else 0.0
        last_pull_age = None
        stale = False
        if last_pull > 0:
            last_pull_age = now - last_pull
            stale = last_pull_age > self._stale_threshold
        next_pull_eta = max(0.0, next_pull_due - now)
        return {
            "mode": "async",
            "pending": pending,
            "pending_topics": pending_topics,
            "priority": priority,
            "oldest": oldest_ts,
            "retry_at": _iso_from_epoch(retry_at),
            "retry_in_seconds": retry_in,
            "last_error": last_error,
            "batch_window": self._batch_window,
            "max_delay": self._max_delay,
            "max_batch_size": self._max_batch_size,
            "sync_interval": self._sync_interval,
            "stale_threshold": self._stale_threshold,
            "last_pull": _iso_from_epoch(last_pull) if last_pull > 0 else None,
            "last_pull_age_seconds": last_pull_age,
            "stale": stale,
            "next_pull_eta_seconds": next_pull_eta,
            "is_syncing": is_syncing,
        }

    # ------------------------------------------------------------------
    # Queue persistence
    # ------------------------------------------------------------------

    def _load_queue(self) -> None:
        if not self._queue_file.exists():
            return
        try:
            with self._queue_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    checksum = payload.pop("checksum", "")
                    if checksum and checksum != _checksum_payload(payload):
                        self._log("skipping corrupt queue line (checksum mismatch)")
                        continue
                    commit = _PendingCommit.from_payload(payload)
                    self._pending.append(commit)
                    self._next_sequence = max(self._next_sequence, commit.sequence + 1)
            self._pending.sort(key=lambda item: item.sequence)
            if self._pending:
                self._last_flushed_sequence = self._pending[0].sequence - 1
                # Ensure queued commits flush promptly after restart.
                self._next_pull_due = time.time()
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._log(f"failed to load queue: {exc}")
            try:
                backup = self._queue_file.with_suffix(".corrupt")
                self._queue_file.rename(backup)
            except Exception:
                pass
            self._pending = []
            self._next_sequence = 1

    def _append_to_queue_locked(self, commit: _PendingCommit) -> None:
        payload = commit.to_payload()
        payload["checksum"] = _checksum_payload(payload)
        try:
            self._queue_dir.mkdir(parents=True, exist_ok=True)
            with self._queue_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:  # pragma: no cover - defensive logging
            self._log(f"failed to append queue entry: {exc}")

    def _rewrite_queue_locked(self) -> None:
        if not self._pending:
            try:
                if self._queue_file.exists():
                    self._queue_file.unlink()
            except Exception:
                pass
            return

        payloads = []
        for commit in sorted(self._pending, key=lambda item: item.sequence):
            payload = commit.to_payload()
            payload["checksum"] = _checksum_payload(payload)
            payloads.append(payload)

        tmp = self._queue_file.with_suffix(".tmp")
        try:
            self._queue_dir.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as fh:
                for payload in payloads:
                    fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            tmp.replace(self._queue_file)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._log(f"failed to rewrite queue: {exc}")
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log(self, message: str) -> None:
        if not self._log_enabled:
            return
        try:
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._queue_dir.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{timestamp} {message}\n")
        except Exception:
            pass
