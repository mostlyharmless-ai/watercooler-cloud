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
from typing import Callable, Optional, TypeVar
import sys
import hashlib

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
            result = subprocess.run(
                cmd,
                cwd=cwd_str,
                env=self._env,
                capture_output=True,
                text=True,
                timeout=timeout,
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
        """Clone the watercooler repository.

        Raises:
            GitSyncError: If clone fails
        """
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

            cmd = ["git", "clone", self.repo_url, str(self.local_path)]
            self._run(cmd, cwd=self.local_path.parent, check=True)
        except subprocess.CalledProcessError as e:
            if self._should_attempt_provision(e):
                self._handle_provisioning_clone(e)
                return
            message = self._format_process_error(
                e, prefix=f"Failed to clone {self.repo_url}"
            )
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

    def _should_attempt_provision(self, error: subprocess.CalledProcessError) -> bool:
        if not self._provision_enabled or not self._remote_allowed:
            return False
        text = " ".join(
            part.strip().lower()
            for part in (error.stderr or "", error.stdout or "")
            if part
        )
        if not text:
            return False
        if "repository not found" in text:
            return True
        return "repository" in text and "not found" in text

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

        # After provisioning, retry clone. If the remote is still empty, fall
        # back to bootstrapping a local repo so the first write can push.
        try:
            cmd = ["git", "clone", self.repo_url, str(self.local_path)]
            self._run(cmd, cwd=self.local_path.parent, check=True)
            return
        except subprocess.CalledProcessError as retry_error:
            combined = self._format_process_error(retry_error)
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

    def _bootstrap_local_repo(self) -> None:
        parent = self.local_path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        if not self.local_path.exists():
            self.local_path.mkdir(parents=True, exist_ok=True)

        self._run(["git", "init"], cwd=self.local_path, check=True)

        remotes = self._run(["git", "remote"], cwd=self.local_path, check=True)
        current = {item.strip() for item in remotes.stdout.splitlines()}
        if "origin" not in current:
            self._run(["git", "remote", "add", "origin", self.repo_url], cwd=self.local_path, check=True)

    def set_remote_allowed(self, allowed: bool) -> None:
        """Toggle whether remote interactions are permitted."""
        self._remote_allowed = bool(allowed)

    def _ensure_remote_repo_exists(self) -> bool:
        """Ensure the remote repository exists before network operations.

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
            result = self._run(
                ["git", "ls-remote", "origin"],
                cwd=self.local_path,
                check=True,
                timeout=30.0,
            )
            output = (getattr(result, "stdout", "") or "").strip()
            self._remote_empty = not bool(output)
            return True
        except TimeoutExpired as timeout_exc:
            self._remote_empty = False
            self._last_remote_error = (
                f"git ls-remote timed out after {timeout_exc.timeout}s"
            )
            return False
        except subprocess.CalledProcessError as error:
            self._remote_empty = False
            message = self._format_process_error(error)
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
                    retry = self._run(
                        ["git", "ls-remote", "origin"],
                        cwd=self.local_path,
                        check=True,
                        timeout=30.0,
                    )
                    output = (getattr(retry, "stdout", "") or "").strip()
                    self._remote_empty = not bool(output)
                    return True
                except ProvisioningError as provision_error:
                    self._last_provision_output = str(provision_error)
                    self._last_remote_error = self._last_provision_output
                    return False
                except subprocess.CalledProcessError as retry_error:
                    retry_message = self._format_process_error(retry_error)
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
        """Configure git user for commits.

        Raises:
            GitSyncError: If configuration fails
        """
        try:
            self._run(["git", "config", "user.name", self.author_name], cwd=self.local_path, check=True)
            self._run(["git", "config", "user.email", self.author_email], cwd=self.local_path, check=True)
        except subprocess.CalledProcessError as e:
            raise GitSyncError(f"Failed to configure git: {e.stderr}") from e

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

        try:
            self._run(["git", "pull", "--rebase", "--autostash"], cwd=self.local_path, check=True)
            return True
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "") + "\n" + (e.stdout or "")
            lowered = stderr.lower()
            if "couldn't find remote ref" in lowered or "could not find remote ref" in lowered:
                return True
            if "does not match any" in lowered:
                return True
            if "no tracking information for the current branch" in lowered:
                return True
            network_tokens = (
                "could not read from remote repository",
                "could not resolve hostname",
                "permission denied",
                "network is unreachable",
                "failed to connect to",
                "failed in sandbox",
            )
            if any(token in lowered for token in network_tokens):
                self._last_pull_error = (
                    stderr.strip()
                    or lowered.strip()
                    or "network failure contacting remote threads repository"
                )
                self._last_remote_error = self._last_pull_error
                return False
            self._last_pull_error = stderr.strip() or lowered.strip()
            self._last_remote_error = self._last_pull_error
            # Rebase conflict or other pull failure
            # Abort any in-progress rebase
            self._run(["git", "rebase", "--abort"], cwd=self.local_path, check=False)
            return False

    def commit_local(self, message: str) -> bool:
        """Commit staged changes locally without pushing.

        Returns True if a commit was created, False if there were no staged changes.
        Raises GitSyncError if git commit fails.
        """
        try:
            # Stage all changes within local_path
            self._run(["git", "add", "-A"], cwd=self.local_path, check=True)

            # Check if there are changes to commit
            result = self._run(["git", "diff", "--cached", "--quiet"], cwd=self.local_path, check=False)
            if result.returncode == 0:
                # No changes to commit
                return False

            # Commit changes
            self._run(["git", "commit", "-m", message], cwd=self.local_path, check=True)
        except subprocess.CalledProcessError as e:
            raise GitSyncError(f"Failed to commit: {e.stderr}") from e
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

        for attempt in range(max_retries):
            try:
                self._run(["git", "push"], cwd=self.local_path, check=True)
                return True

            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or "") + "\n" + (e.stdout or "")
                lowered = stderr.lower()
                network_tokens = (
                    "could not read from remote repository",
                    "could not resolve hostname",
                    "permission denied",
                    "network is unreachable",
                    "failed to connect to",
                    "failed in sandbox",
                )
                if any(token in lowered for token in network_tokens):
                    self._last_push_error = (
                        stderr.strip()
                        or lowered.strip()
                        or "network failure contacting remote threads repository"
                    )
                    return False
                # Handle missing upstream / no configured push destination / empty ref
                if (
                    "has no upstream branch" in stderr
                    or "No configured push destination" in stderr
                    or "does not match any" in stderr  # e.g., src refspec does not match any
                ):
                    try:
                        self._run(["git", "push", "-u", "origin", "HEAD"], cwd=self.local_path, check=True)
                        return True
                    except subprocess.CalledProcessError as push_error:
                        upstream_stderr = (push_error.stderr or "") + "\n" + (push_error.stdout or "")
                        self._last_push_error = (
                            upstream_stderr.strip()
                            or lowered.strip()
                            or "failed to set upstream for threads branch"
                        )
                        if attempt >= max_retries - 1:
                            return False
                        continue

                if attempt < max_retries - 1:
                    # Push rejected - pull and retry
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
                self._last_push_error = stderr.strip() or lowered.strip() or "failed to push threads updates"
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
        """Ensure the local repo is on the given branch, creating it if needed.

        Also sets upstream to origin/<branch> on first creation.
        Returns True on success, False on failure (non-fatal; caller can proceed).
        """
        try:
            self._ensure_local_repo_ready()

            # What branch are we on now?
            current = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.local_path, check=True).stdout.strip()
            if current == branch:
                return True

            # Does the branch exist locally?
            exists = self._run(["git", "show-ref", "--verify", f"refs/heads/{branch}"], cwd=self.local_path, check=False).returncode == 0

            remote_available = self._remote_allowed and self._ensure_remote_repo_exists()
            remote_has_branch = False

            if remote_available:
                remote_check = self._run(
                    ["git", "ls-remote", "--heads", "origin", branch],
                    cwd=self.local_path,
                    check=False,
                    timeout=30.0,
                )
                remote_has_branch = bool(remote_check.stdout.strip()) and remote_check.returncode == 0

            if exists:
                self._run(["git", "checkout", branch], cwd=self.local_path, check=True)
            else:
                if remote_has_branch:
                    self._run(["git", "fetch", "origin", f"{branch}:refs/heads/{branch}"], cwd=self.local_path, check=True)
                    self._run(["git", "checkout", branch], cwd=self.local_path, check=True)
                else:
                    self._run(["git", "checkout", "-b", branch], cwd=self.local_path, check=True)

            # Ensure upstream is set when remote branch exists
            upstream = self._run(["git", "rev-parse", "--abbrev-ref", "@{u}"], cwd=self.local_path, check=False)
            if upstream.returncode != 0 and remote_has_branch:
                self._run(["git", "branch", "--set-upstream-to", f"origin/{branch}", branch], cwd=self.local_path, check=True)
            elif upstream.returncode != 0 and self._remote_allowed and not remote_has_branch:
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
