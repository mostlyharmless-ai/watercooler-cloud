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
