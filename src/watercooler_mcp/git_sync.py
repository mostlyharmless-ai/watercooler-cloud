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
import subprocess
from pathlib import Path
from typing import Callable, TypeVar

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
        author_email: str = "mcp@watercooler.dev"
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

        # Prepare git environment once (propagated to all git operations)
        self._env = os.environ.copy()
        if self.ssh_key_path:
            self._env["GIT_SSH_COMMAND"] = f"ssh -i {self.ssh_key_path} -o IdentitiesOnly=yes"

        self._setup()

    def _setup(self):
        """Ensure repository is cloned and configured."""
        if not (self.local_path / ".git").exists():
            self._clone()
        self._configure_git()

    def _clone(self):
        """Clone the watercooler repository.

        Raises:
            GitSyncError: If clone fails
        """
        try:
            cmd = ["git", "clone", self.repo_url, str(self.local_path)]
            subprocess.run(cmd, env=self._env, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise GitSyncError(f"Failed to clone {self.repo_url}: {e.stderr}") from e

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
        try:
            result = subprocess.run(
                ["git", "pull", "--rebase", "--autostash"],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                env=self._env,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
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
                if attempt < max_retries - 1:
                    # Push rejected - pull and retry
                    if not self.pull():
                        # Pull failed (rebase conflict)
                        return False
                    continue
                # Max retries exceeded
                return False

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
            raise GitPullError("Failed to pull latest changes before operation")

        # Execute operation
        result = operation()

        # Commit and push after operation
        if not self.commit_and_push(commit_message):
            raise GitPushError(f"Failed to push changes: {commit_message}")

        return result
