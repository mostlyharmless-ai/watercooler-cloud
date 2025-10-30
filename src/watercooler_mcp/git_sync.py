"""Git-based synchronization for cloud-hosted watercooler MCP servers.

This module provides GitSyncManager for syncing .watercooler threads via git,
enabling multi-user collaboration with automatic conflict resolution.

Architecture:
- Pull before reads (get latest from remote)
- Commit + push after writes (propagate changes)
- Retry logic handles concurrent modifications
- Append-only operations minimize conflicts

Usage:
    sync = GitSyncManager(
        repo_url="git@github.com:org/watercooler-threads.git",
        local_path=Path("/path/to/.watercooler"),
        ssh_key_path=Path("/path/to/key")
    )

    # Sync before and after an operation
    sync.with_sync(
        operation=lambda: append_entry(...),
        commit_message="Agent: Added entry (topic)"
    )
"""

import os
import time
import re
import subprocess
from pathlib import Path
from typing import Callable, TypeVar

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

        # Prepare git environment once (propagated to all git operations)
        self._env = os.environ.copy()
        if self.ssh_key_path:
            self._env["GIT_SSH_COMMAND"] = f"ssh -i {self.ssh_key_path} -o IdentitiesOnly=yes"

        self._setup()

    def _setup(self):
        """Ensure repository is cloned and configured."""
        self._initialise_repository()
        self._configure_git()

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
            subprocess.run(cmd, env=self._env, check=True, capture_output=True, text=True)
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
            subprocess.run(
                cmd,
                env=self._env,
                check=True,
                capture_output=True,
                text=True,
            )
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

        subprocess.run(
            ["git", "init"],
            cwd=self.local_path,
            env=self._env,
            check=True,
            capture_output=True,
            text=True,
        )

        remotes = subprocess.run(
            ["git", "remote"],
            cwd=self.local_path,
            env=self._env,
            check=True,
            capture_output=True,
            text=True,
        )
        current = {item.strip() for item in remotes.stdout.splitlines()}
        if "origin" not in current:
            subprocess.run(
                ["git", "remote", "add", "origin", self.repo_url],
                cwd=self.local_path,
                env=self._env,
                check=True,
                capture_output=True,
                text=True,
            )

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
            result = subprocess.run(
                ["git", "ls-remote", "origin"],
                cwd=self.local_path,
                env=self._env,
                check=True,
                capture_output=True,
                text=True,
            )
            output = (getattr(result, "stdout", "") or "").strip()
            self._remote_empty = not bool(output)
            return True
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
                    retry = subprocess.run(
                        ["git", "ls-remote", "origin"],
                        cwd=self.local_path,
                        env=self._env,
                        check=True,
                        capture_output=True,
                        text=True,
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
            subprocess.run(
                ["git", "config", "user.name", self.author_name],
                cwd=self.local_path,
                env=self._env,
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", self.author_email],
                cwd=self.local_path,
                env=self._env,
                check=True,
                capture_output=True
            )
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
            subprocess.run(
                ["git", "pull", "--rebase", "--autostash"],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._env,
                check=True
            )
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
            subprocess.run(
                ["git", "rebase", "--abort"],
                cwd=self.local_path,
                env=self._env,
                capture_output=True
            )
            return False

    def commit_and_push(self, message: str, max_retries: int = 3) -> bool:
        """Commit changes and push to remote with retry logic.

        Args:
            message: Git commit message
            max_retries: Maximum number of push retries (default: 3)

        Returns:
            True if commit and push succeeded, False otherwise

        Retry Logic:
            If push is rejected (someone else pushed first):
            1. Pull latest changes
            2. Retry push
            3. Repeat up to max_retries times

        Note:
            Only stages changes within local_path. For dedicated threads repos,
            this is the entire repo. For co-located setups, restricts to
            the .watercooler directory.
        """
        try:
            # Stage all changes within local_path
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.local_path,
                env=self._env,
                check=True,
                capture_output=True
            )

            # Check if there are changes to commit
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=self.local_path,
                env=self._env
            )
            if result.returncode == 0:
                # No changes to commit
                return True

            # Commit changes
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.local_path,
                env=self._env,
                check=True,
                capture_output=True
            )

        except subprocess.CalledProcessError as e:
            raise GitSyncError(f"Failed to commit: {e.stderr}") from e

        # Push with retry logic
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
                subprocess.run(
                    ["git", "push"],
                    cwd=self.local_path,
                    env=self._env,
                    check=True,
                    capture_output=True,
                    text=True
                )
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
                        subprocess.run(
                            ["git", "push", "-u", "origin", "HEAD"],
                            cwd=self.local_path,
                            env=self._env,
                            check=True,
                            capture_output=True,
                            text=True,
                        )
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

    def ensure_branch(self, branch: str) -> bool:
        """Ensure the local repo is on the given branch, creating it if needed.

        Also sets upstream to origin/<branch> on first creation.
        Returns True on success, False on failure (non-fatal; caller can proceed).
        """
        try:
            self._ensure_local_repo_ready()

            # What branch are we on now?
            current = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.local_path,
                env=self._env,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            if current == branch:
                return True

            # Does the branch exist locally?
            exists = subprocess.run(
                ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
                cwd=self.local_path,
                env=self._env,
                capture_output=True,
            ).returncode == 0

            remote_available = self._remote_allowed and self._ensure_remote_repo_exists()
            remote_has_branch = False

            if remote_available:
                remote_check = subprocess.run(
                    ["git", "ls-remote", "--heads", "origin", branch],
                    cwd=self.local_path,
                    env=self._env,
                    capture_output=True,
                    text=True,
                )
                remote_has_branch = bool(remote_check.stdout.strip()) and remote_check.returncode == 0

            if exists:
                subprocess.run(["git", "checkout", branch], cwd=self.local_path, env=self._env, check=True, capture_output=True)
            else:
                if remote_has_branch:
                    subprocess.run(
                        ["git", "fetch", "origin", f"{branch}:refs/heads/{branch}"],
                        cwd=self.local_path,
                        env=self._env,
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "checkout", branch],
                        cwd=self.local_path,
                        env=self._env,
                        check=True,
                        capture_output=True,
                    )
                else:
                    subprocess.run(["git", "checkout", "-b", branch], cwd=self.local_path, env=self._env, check=True, capture_output=True)

            # Ensure upstream is set when remote branch exists
            upstream = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "@{u}"],
                cwd=self.local_path,
                env=self._env,
                capture_output=True,
                text=True,
            )
            if upstream.returncode != 0 and remote_has_branch:
                subprocess.run(
                    ["git", "branch", "--set-upstream-to", f"origin/{branch}", branch],
                    cwd=self.local_path,
                    env=self._env,
                    capture_output=True,
                )
            elif upstream.returncode != 0 and self._remote_allowed and not remote_has_branch:
                # Remote unavailable or branch missing - leave as-is (local-only)
                pass
            return True
        except Exception:
            return False

    def with_sync(self, operation: Callable[[], T], commit_message: str) -> T:
        """Execute operation with git sync before and after.

        This is the primary interface for cloud-synced operations. It:
        1. Pulls latest changes from remote
        2. Executes the provided operation
        3. Commits and pushes changes

        Args:
            operation: Callable that performs the actual work (e.g., append entry)
            commit_message: Git commit message for the changes

        Returns:
            The return value of the operation

        Raises:
            GitPullError: If initial pull fails
            GitPushError: If commit/push fails after operation
            Any exception raised by the operation itself

        Example:
            def append_operation():
                thread.append_entry(title="...", body="...")

            sync.with_sync(
                append_operation,
                "Agent: Added planning entry (feature-x)"
            )
        """
        # Pull latest before operation
        if not self.pull():
            detail = self._last_pull_error or "unknown error"
            raise GitPullError(
                f"Failed to pull latest changes before operation: {detail}"
            )

        # Execute operation
        result = operation()

        # Commit and push after operation
        if not self.commit_and_push(commit_message):
            detail = self._last_push_error or "unknown push error"
            raise GitPushError(f"Failed to push changes: {detail}")

        return result
