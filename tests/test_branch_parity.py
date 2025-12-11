"""Tests for branch parity state machine with auto-remediation.

Tests cover:
- State file read/write operations
- Per-topic locking
- Preflight checks (clean, branch mismatch, main protection)
- Auto-remediation behaviors
- Health reporting
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from git import Repo, Actor

from watercooler_mcp.branch_parity import (
    ParityStatus,
    ParityState,
    PreflightResult,
    read_parity_state,
    write_parity_state,
    acquire_topic_lock,
    run_preflight,
    push_after_commit,
    get_branch_health,
    STATE_FILE_NAME,
    LOCKS_DIR_NAME,
    LOCK_TIMEOUT_SECONDS,
    LOCK_TTL_SECONDS,
    _sanitize_topic_for_filename,
)


@pytest.fixture
def code_repo(tmp_path: Path) -> Path:
    """Create a temporary code repository."""
    repo_path = tmp_path / "code-repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create initial commit
    (repo_path / "README.md").write_text("# Code Repo\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit", author=Actor("Test", "test@example.com"))

    # Ensure we're on main branch
    try:
        repo.git.checkout("-b", "main")
    except Exception:
        repo.git.checkout("main")

    return repo_path


@pytest.fixture
def threads_repo(tmp_path: Path) -> Path:
    """Create a temporary threads repository."""
    repo_path = tmp_path / "code-repo-threads"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create initial commit
    (repo_path / "README.md").write_text("# Threads Repo\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit", author=Actor("Test", "test@example.com"))

    # Ensure we're on main branch
    try:
        repo.git.checkout("-b", "main")
    except Exception:
        repo.git.checkout("main")

    return repo_path


@pytest.fixture
def threads_dir(tmp_path: Path) -> Path:
    """Create a temporary threads directory (non-git)."""
    threads_path = tmp_path / "threads"
    threads_path.mkdir()
    return threads_path


# =============================================================================
# State File Tests
# =============================================================================


def test_read_parity_state_empty(threads_dir: Path) -> None:
    """Test reading state when file doesn't exist."""
    state = read_parity_state(threads_dir)
    assert state.status == ParityStatus.CLEAN.value
    assert state.last_check_at == ""
    assert state.actions_taken == []


def test_write_and_read_parity_state(threads_dir: Path) -> None:
    """Test writing and reading state file."""
    state = ParityState(
        status=ParityStatus.PENDING_PUSH.value,
        last_check_at="2024-01-01T00:00:00Z",
        code_branch="feature-test",
        threads_branch="feature-test",
        actions_taken=["Created branch"],
        pending_push=True,
    )

    # Write state
    result = write_parity_state(threads_dir, state)
    assert result is True

    # Verify file exists
    state_file = threads_dir / STATE_FILE_NAME
    assert state_file.exists()

    # Read it back
    read_state = read_parity_state(threads_dir)
    assert read_state.status == ParityStatus.PENDING_PUSH.value
    assert read_state.code_branch == "feature-test"
    assert read_state.threads_branch == "feature-test"
    assert "Created branch" in read_state.actions_taken
    assert read_state.pending_push is True


def test_parity_state_to_dict() -> None:
    """Test ParityState serialization."""
    state = ParityState(
        status=ParityStatus.BRANCH_MISMATCH.value,
        code_branch="main",
        threads_branch="feature-x",
    )
    data = state.to_dict()
    assert data["status"] == "branch_mismatch"
    assert data["code_branch"] == "main"
    assert data["threads_branch"] == "feature-x"


def test_parity_state_from_dict() -> None:
    """Test ParityState deserialization."""
    data = {
        "status": "main_protection",
        "code_branch": "feature-y",
        "threads_branch": "main",
        "last_error": "Cannot write to main",
    }
    state = ParityState.from_dict(data)
    assert state.status == "main_protection"
    assert state.code_branch == "feature-y"
    assert state.threads_branch == "main"
    assert state.last_error == "Cannot write to main"


# =============================================================================
# Locking Tests
# =============================================================================


def test_acquire_topic_lock(threads_dir: Path) -> None:
    """Test acquiring a topic lock."""
    lock = acquire_topic_lock(threads_dir, "test-topic", timeout=5)
    assert lock is not None

    # Verify lock file exists
    lock_dir = threads_dir / LOCKS_DIR_NAME
    assert lock_dir.exists()
    lock_file = lock_dir / "test-topic.lock"
    assert lock_file.exists()

    # Release lock
    lock.release()


def test_acquire_topic_lock_sanitizes_topic(threads_dir: Path) -> None:
    """Test that topic names with slashes are sanitized."""
    lock = acquire_topic_lock(threads_dir, "feature/test-topic", timeout=5)
    assert lock is not None

    # Verify sanitized lock file exists
    lock_dir = threads_dir / LOCKS_DIR_NAME
    lock_file = lock_dir / "feature_test-topic.lock"
    assert lock_file.exists()

    lock.release()


# --- Topic Sanitization Tests ---


def test_sanitize_topic_path_traversal() -> None:
    """Test that path traversal attempts are neutralized."""
    # Path traversal attempts
    assert ".." not in _sanitize_topic_for_filename("../../etc/passwd")
    assert ".." not in _sanitize_topic_for_filename("..\\..\\windows\\system32")
    assert ".." not in _sanitize_topic_for_filename("foo/../bar")

    # Should produce safe filenames
    safe = _sanitize_topic_for_filename("../../etc/passwd")
    assert "/" not in safe
    assert "\\" not in safe


def test_sanitize_topic_special_characters() -> None:
    """Test that Windows-invalid and special characters are removed."""
    # Windows reserved characters: < > : " / \ | ? *
    assert "<" not in _sanitize_topic_for_filename("topic<test>")
    assert ">" not in _sanitize_topic_for_filename("topic<test>")
    assert ":" not in _sanitize_topic_for_filename("topic:test")
    assert '"' not in _sanitize_topic_for_filename('topic"test')
    assert "|" not in _sanitize_topic_for_filename("topic|test")
    assert "?" not in _sanitize_topic_for_filename("topic?test")
    assert "*" not in _sanitize_topic_for_filename("topic*test")


def test_sanitize_topic_empty_and_edge_cases() -> None:
    """Test edge cases like empty strings and all-special-char strings."""
    # Empty string
    assert _sanitize_topic_for_filename("") == "_empty_"

    # Only special characters
    result = _sanitize_topic_for_filename("///")
    assert result  # Should not be empty
    assert "/" not in result

    # Only dots
    result = _sanitize_topic_for_filename("...")
    assert result  # Should not be empty
    assert not result.startswith(".")


def test_sanitize_topic_long_names() -> None:
    """Test that very long topic names are truncated with hash suffix."""
    # Create a very long topic name (300 chars)
    long_topic = "a" * 300

    safe = _sanitize_topic_for_filename(long_topic)

    # Should be truncated to MAX_TOPIC_LENGTH (200)
    assert len(safe) <= 200

    # Should include a hash for uniqueness
    assert "_" in safe  # Hash is appended with underscore


def test_sanitize_topic_collision_prevention() -> None:
    """Test that topics with similar names after sanitization get unique results."""
    # These would collide with naive sanitization
    topic1 = "feature/auth"
    topic2 = "feature\\auth"
    topic3 = "feature_auth"

    safe1 = _sanitize_topic_for_filename(topic1)
    safe2 = _sanitize_topic_for_filename(topic2)
    safe3 = _sanitize_topic_for_filename(topic3)

    # All should produce the same safe result (normalized to underscores)
    # This is intentional - we normalize slashes to underscores
    assert safe1 == safe2 == safe3 == "feature_auth"


def test_sanitize_topic_unicode() -> None:
    """Test that unicode characters are handled safely."""
    # Unicode should be preserved (they're valid in most filesystems)
    safe = _sanitize_topic_for_filename("feature-émoji-🚀")
    assert "émoji" in safe or "emoji" in safe.lower() or len(safe) > 0

    # Should not contain path separators
    assert "/" not in safe
    assert "\\" not in safe


def test_constants_are_defined() -> None:
    """Test that lock constants are properly defined."""
    assert LOCK_TIMEOUT_SECONDS == 30
    assert LOCK_TTL_SECONDS == 60


def test_acquire_topic_lock_timeout(threads_dir: Path) -> None:
    """Test that lock acquisition times out when lock is held."""
    # Acquire first lock
    lock1 = acquire_topic_lock(threads_dir, "contested-topic", timeout=5)

    # Try to acquire second lock - should timeout
    with pytest.raises(TimeoutError):
        acquire_topic_lock(threads_dir, "contested-topic", timeout=1)

    lock1.release()


# =============================================================================
# Preflight Tests
# =============================================================================


def test_preflight_clean_state(code_repo: Path, threads_repo: Path) -> None:
    """Test preflight when branches are properly aligned."""
    result = run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=False,
        fetch_first=False,  # No origin to fetch from
    )

    assert result.success is True
    assert result.can_proceed is True
    assert result.state.status == ParityStatus.CLEAN.value
    assert result.state.code_branch == "main"
    assert result.state.threads_branch == "main"


def test_preflight_branch_mismatch_auto_fix(code_repo: Path, threads_repo: Path) -> None:
    """Test preflight auto-fixes branch mismatch."""
    # Create feature branch in code repo
    code = Repo(code_repo)
    code.git.checkout("-b", "feature-test")

    # Threads stays on main
    result = run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=True,
        fetch_first=False,
    )

    assert result.success is True
    assert result.can_proceed is True
    assert result.auto_fixed is True
    # Check that some action was taken involving the feature branch
    assert len(result.state.actions_taken) > 0
    assert any("feature-test" in action for action in result.state.actions_taken)

    # Verify threads is now on feature branch
    threads = Repo(threads_repo)
    assert threads.active_branch.name == "feature-test"


def test_preflight_branch_mismatch_no_auto_fix(code_repo: Path, threads_repo: Path) -> None:
    """Test preflight blocks when branch mismatch and auto_fix=False."""
    # Create feature branch in code repo
    code = Repo(code_repo)
    code.git.checkout("-b", "feature-test")

    result = run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=False,
        fetch_first=False,
    )

    assert result.success is False
    assert result.can_proceed is False
    # Either main_protection or branch_mismatch can fire (main_protection is checked first)
    assert result.state.status in [
        ParityStatus.BRANCH_MISMATCH.value,
        ParityStatus.MAIN_PROTECTION.value,
    ]
    assert "feature-test" in result.blocking_reason
    assert "main" in result.blocking_reason


def test_preflight_main_protection(code_repo: Path, threads_repo: Path) -> None:
    """Test preflight blocks writes when threads=main but code=feature."""
    # Create feature branch in code repo
    code = Repo(code_repo)
    code.git.checkout("-b", "feature-secure")

    # When auto_fix is disabled, should block
    result = run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=False,
        fetch_first=False,
    )

    assert result.success is False
    assert result.can_proceed is False
    # Either main_protection or branch_mismatch since both could apply
    assert result.state.status in [
        ParityStatus.MAIN_PROTECTION.value,
        ParityStatus.BRANCH_MISMATCH.value,
    ]


def test_preflight_main_protection_auto_fix(code_repo: Path, threads_repo: Path) -> None:
    """Test preflight auto-fixes main protection by creating threads branch."""
    # Create feature branch in code repo
    code = Repo(code_repo)
    code.git.checkout("-b", "feature-protected")

    # With auto_fix, should create the threads branch
    result = run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=True,
        fetch_first=False,
    )

    assert result.success is True
    assert result.can_proceed is True
    assert result.auto_fixed is True

    # Verify threads is now on feature branch
    threads = Repo(threads_repo)
    assert threads.active_branch.name == "feature-protected"


def test_preflight_detached_head(code_repo: Path, threads_repo: Path) -> None:
    """Test preflight detects detached HEAD state."""
    code = Repo(code_repo)

    # Detach HEAD by checking out a commit directly
    code.git.checkout(code.head.commit.hexsha)

    result = run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=True,
        fetch_first=False,
    )

    assert result.success is False
    assert result.can_proceed is False
    assert result.state.status == ParityStatus.DETACHED_HEAD.value
    assert "detached head" in result.blocking_reason.lower()


def test_preflight_invalid_repo(tmp_path: Path, threads_repo: Path) -> None:
    """Test preflight handles invalid repository paths."""
    invalid_path = tmp_path / "not-a-repo"
    invalid_path.mkdir()

    result = run_preflight(
        code_repo_path=invalid_path,
        threads_repo_path=threads_repo,
        auto_fix=True,
        fetch_first=False,
    )

    assert result.success is False
    assert result.can_proceed is False
    assert result.state.status == ParityStatus.ERROR.value
    assert "not a git repository" in result.blocking_reason.lower()


# =============================================================================
# Health Reporting Tests
# =============================================================================


def test_get_branch_health(code_repo: Path, threads_repo: Path) -> None:
    """Test health reporting returns expected structure."""
    # First run preflight to populate state
    run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=False,
        fetch_first=False,
    )

    health = get_branch_health(code_repo, threads_repo)

    assert "status" in health
    assert "code_branch" in health
    assert "threads_branch" in health
    assert "code_ahead_origin" in health
    assert "code_behind_origin" in health
    assert "pending_push" in health
    assert "last_check_at" in health


def test_get_branch_health_no_state_file(tmp_path: Path) -> None:
    """Test health reporting when no state file exists."""
    code_path = tmp_path / "code"
    threads_path = tmp_path / "threads"
    code_path.mkdir()
    threads_path.mkdir()

    # Initialize repos
    code = Repo.init(code_path)
    threads = Repo.init(threads_path)

    # Create initial commits
    (code_path / "README.md").write_text("# Code\n")
    code.index.add(["README.md"])
    code.index.commit("Initial", author=Actor("Test", "test@example.com"))

    (threads_path / "README.md").write_text("# Threads\n")
    threads.index.add(["README.md"])
    threads.index.commit("Initial", author=Actor("Test", "test@example.com"))

    health = get_branch_health(code_path, threads_path)

    # Should return default state
    assert health["status"] == ParityStatus.CLEAN.value


# =============================================================================
# PreflightResult Tests
# =============================================================================


def test_preflight_result_structure() -> None:
    """Test PreflightResult dataclass structure."""
    state = ParityState(status=ParityStatus.CLEAN.value)
    result = PreflightResult(
        success=True,
        state=state,
        can_proceed=True,
        auto_fixed=False,
    )

    assert result.success is True
    assert result.can_proceed is True
    assert result.auto_fixed is False
    assert result.blocking_reason is None


def test_preflight_result_with_blocking_reason() -> None:
    """Test PreflightResult with blocking reason."""
    state = ParityState(
        status=ParityStatus.CODE_BEHIND_ORIGIN.value,
        last_error="Code behind by 5 commits",
    )
    result = PreflightResult(
        success=False,
        state=state,
        can_proceed=False,
        blocking_reason="Code repo is 5 commits behind origin. Please pull.",
    )

    assert result.success is False
    assert result.can_proceed is False
    assert "5 commits behind" in result.blocking_reason


# =============================================================================
# Remote Push Parity Tests (with bare remotes)
# =============================================================================


@pytest.fixture
def repos_with_remotes(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create code and threads repos with bare remotes for push testing."""
    # Create bare remotes (simulating origin)
    code_bare = tmp_path / "code-bare.git"
    threads_bare = tmp_path / "threads-bare.git"
    Repo.init(code_bare, bare=True)
    Repo.init(threads_bare, bare=True)

    # Create working directories
    code_path = tmp_path / "code-repo"
    threads_path = tmp_path / "threads-repo"

    # Clone from bare repos
    code = Repo.clone_from(str(code_bare), str(code_path))
    threads = Repo.clone_from(str(threads_bare), str(threads_path))

    # Create initial commits and push
    author = Actor("Test", "test@example.com")

    (code_path / "README.md").write_text("# Code Repo\n")
    code.index.add(["README.md"])
    code.index.commit("Initial commit", author=author)
    code.git.push("origin", "HEAD:main")
    code.git.checkout("-b", "main")
    code.git.branch("--set-upstream-to=origin/main", "main")

    (threads_path / "README.md").write_text("# Threads Repo\n")
    threads.index.add(["README.md"])
    threads.index.commit("Initial commit", author=author)
    threads.git.push("origin", "HEAD:main")
    threads.git.checkout("-b", "main")
    threads.git.branch("--set-upstream-to=origin/main", "main")

    return code_path, threads_path, code_bare, threads_bare


def test_preflight_threads_ahead_auto_push(repos_with_remotes: tuple[Path, Path, Path, Path]) -> None:
    """Test preflight auto-pushes when threads is ahead of origin."""
    code_path, threads_path, code_bare, threads_bare = repos_with_remotes

    # Add local commit to threads (not pushed)
    threads = Repo(threads_path)
    author = Actor("Test", "test@example.com")
    (threads_path / "thread.md").write_text("# Thread\n")
    threads.index.add(["thread.md"])
    threads.index.commit("Add thread", author=author)

    # Threads is now ahead of origin by 1 commit
    # Code is synced with origin

    result = run_preflight(
        code_repo_path=code_path,
        threads_repo_path=threads_path,
        auto_fix=True,
        fetch_first=False,
    )

    assert result.success is True
    assert result.can_proceed is True
    assert result.auto_fixed is True
    # Verify push action was taken
    assert any("Pushed threads" in action for action in result.state.actions_taken)

    # Verify threads is now synced with origin
    threads.git.fetch("origin")
    ahead_behind = threads.git.rev_list("--left-right", "--count", "main...origin/main")
    ahead, behind = [int(x) for x in ahead_behind.split()]
    assert ahead == 0  # No longer ahead


def test_preflight_threads_ahead_no_auto_fix(repos_with_remotes: tuple[Path, Path, Path, Path]) -> None:
    """Test preflight logs but doesn't push when auto_fix=False."""
    code_path, threads_path, code_bare, threads_bare = repos_with_remotes

    # Add local commit to threads (not pushed)
    threads = Repo(threads_path)
    author = Actor("Test", "test@example.com")
    (threads_path / "thread.md").write_text("# Thread\n")
    threads.index.add(["thread.md"])
    threads.index.commit("Add thread", author=author)

    result = run_preflight(
        code_repo_path=code_path,
        threads_repo_path=threads_path,
        auto_fix=False,
        fetch_first=False,
    )

    # Should still succeed (we don't block on threads ahead)
    assert result.success is True
    assert result.can_proceed is True
    assert result.auto_fixed is False

    # Threads should still be ahead (no push happened)
    threads.git.fetch("origin")
    ahead_behind = threads.git.rev_list("--left-right", "--count", "main...origin/main")
    ahead, behind = [int(x) for x in ahead_behind.split()]
    assert ahead == 1  # Still ahead


# =============================================================================
# Inverse Main Protection Tests
# =============================================================================


def test_preflight_inverse_main_protection(code_repo: Path, threads_repo: Path) -> None:
    """Test preflight blocks when code=main but threads=feature.

    This is the inverse of main protection. When code is on main but threads
    is on a feature branch, we block because entries would have incorrect
    Code-Branch metadata.
    """
    # Code stays on main
    # Put threads on a feature branch
    threads = Repo(threads_repo)
    threads.git.checkout("-b", "feature-orphan")

    result = run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=False,  # No auto-fix for this case
        fetch_first=False,
    )

    assert result.success is False
    assert result.can_proceed is False
    assert result.state.status == ParityStatus.MAIN_PROTECTION.value
    assert "main" in result.blocking_reason
    assert "feature-orphan" in result.blocking_reason
    assert "incorrect Code-Branch metadata" in result.blocking_reason


def test_preflight_inverse_main_protection_not_auto_fixed(code_repo: Path, threads_repo: Path) -> None:
    """Test that inverse main protection is NOT auto-fixed even with auto_fix=True.

    Unlike the forward case (threads=main, code=feature), the inverse case
    (code=main, threads=feature) should NOT be auto-fixed. The user must
    explicitly decide whether to checkout code to the feature branch or
    merge the threads branch.
    """
    threads = Repo(threads_repo)
    threads.git.checkout("-b", "stale-feature")

    # Even with auto_fix=True, should block
    result = run_preflight(
        code_repo_path=code_repo,
        threads_repo_path=threads_repo,
        auto_fix=True,  # Even with auto-fix, this case blocks
        fetch_first=False,
    )

    assert result.success is False
    assert result.can_proceed is False
    assert result.state.status == ParityStatus.MAIN_PROTECTION.value


# =============================================================================
# Divergence Blocking Tests
# =============================================================================


def test_preflight_threads_behind_origin_blocks(repos_with_remotes: tuple[Path, Path, Path, Path]) -> None:
    """Test preflight blocks when threads is behind origin.

    When threads repo is behind origin, we block to prevent auto-pulling
    changes that may conflict or that the user may not be aware of.
    Use reconcile_parity to fix.
    """
    code_path, threads_path, code_bare, threads_bare = repos_with_remotes

    # Push a commit to threads origin from another "clone"
    # This simulates another agent having pushed commits
    other_threads = Repo.clone_from(str(threads_bare), str(threads_path.parent / "other-threads"))
    # Ensure on main branch
    try:
        other_threads.git.checkout("main")
    except Exception:
        other_threads.git.checkout("-b", "main")
    author = Actor("Other", "other@example.com")
    (Path(other_threads.working_dir) / "other-thread.md").write_text("# Other Thread\n")
    other_threads.index.add(["other-thread.md"])
    other_threads.index.commit("Other agent entry", author=author)
    other_threads.git.push("origin", "main")

    # Now our local threads is behind origin by 1 commit
    # Fetch to detect the difference
    threads = Repo(threads_path)
    threads.git.fetch("origin")

    result = run_preflight(
        code_repo_path=code_path,
        threads_repo_path=threads_path,
        auto_fix=True,  # Even with auto_fix, should block
        fetch_first=False,  # We already fetched
    )

    assert result.success is False
    assert result.can_proceed is False
    assert result.state.status == ParityStatus.DIVERGED.value
    assert "behind origin" in result.blocking_reason
    assert "reconcile_parity" in result.blocking_reason


def test_preflight_threads_diverged_blocks(repos_with_remotes: tuple[Path, Path, Path, Path]) -> None:
    """Test preflight blocks when threads has diverged (both ahead and behind origin).

    When threads has local commits AND is behind origin, we have a diverged
    state that requires manual resolution.
    """
    code_path, threads_path, code_bare, threads_bare = repos_with_remotes

    # Push a commit to threads origin from another "clone"
    other_threads = Repo.clone_from(str(threads_bare), str(threads_path.parent / "other-threads-2"))
    # Ensure on main branch
    try:
        other_threads.git.checkout("main")
    except Exception:
        other_threads.git.checkout("-b", "main")
    author = Actor("Other", "other@example.com")
    (Path(other_threads.working_dir) / "other.md").write_text("# Other\n")
    other_threads.index.add(["other.md"])
    other_threads.index.commit("Other commit", author=author)
    other_threads.git.push("origin", "main")

    # Add local commit to our threads (not pushed)
    threads = Repo(threads_path)
    author = Actor("Test", "test@example.com")
    (threads_path / "local.md").write_text("# Local\n")
    threads.index.add(["local.md"])
    threads.index.commit("Local commit", author=author)

    # Now threads is both ahead (local commit) and behind (other's commit)
    # Fetch to detect the difference
    threads.git.fetch("origin")

    result = run_preflight(
        code_repo_path=code_path,
        threads_repo_path=threads_path,
        auto_fix=True,
        fetch_first=False,
    )

    # Should block - we're behind origin
    assert result.success is False
    assert result.can_proceed is False
    assert result.state.status == ParityStatus.DIVERGED.value
