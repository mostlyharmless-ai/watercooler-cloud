import os
import shutil
import subprocess
from pathlib import Path

import pytest

from watercooler_mcp.config import resolve_thread_context


def _git_available() -> bool:
    return shutil.which("git") is not None


def test_resolve_thread_context_explicit_dir(tmp_path, monkeypatch):
    explicit_dir = tmp_path / ".watercooler"
    monkeypatch.setenv("WATERCOOLER_DIR", str(explicit_dir))
    monkeypatch.delenv("WATERCOOLER_THREADS_BASE", raising=False)
    monkeypatch.delenv("WATERCOOLER_THREADS_PATTERN", raising=False)
    monkeypatch.delenv("WATERCOOLER_GIT_REPO", raising=False)
    monkeypatch.delenv("WATERCOOLER_CODE_REPO", raising=False)

    context = resolve_thread_context()

    assert context.explicit_dir is True
    assert context.threads_dir == explicit_dir
    assert context.threads_repo_url is None


@pytest.mark.skipif(not _git_available(), reason="git not available in test environment")
def test_resolve_thread_context_git_pattern(tmp_path, monkeypatch):
    repo_dir = tmp_path / "code"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:mostly/test.git"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    # Create initial commit to establish a branch
    (repo_dir / "README.md").write_text("test")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    threads_base = tmp_path / "threads"
    monkeypatch.delenv("WATERCOOLER_DIR", raising=False)
    monkeypatch.setenv("WATERCOOLER_THREADS_BASE", str(threads_base))
    monkeypatch.delenv("WATERCOOLER_GIT_REPO", raising=False)
    monkeypatch.delenv("WATERCOOLER_CODE_REPO", raising=False)

    context = resolve_thread_context(repo_dir)

    expected_dir = (threads_base / "mostly" / "test-threads").resolve()
    assert context.threads_dir == expected_dir
    assert context.threads_repo_url == "git@github.com:mostly/test-threads.git"
    assert context.code_repo == "mostly/test"
    assert context.code_branch in {"master", "main"}
