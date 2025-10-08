import os
import json
import logging
import types
import importlib.util
import subprocess
from pathlib import Path
import pytest


def _import_git_sync():
    path = Path("src/watercooler_mcp/git_sync.py").resolve()
    if not path.exists():
        pytest.skip("GitSyncManager not implemented yet")
    spec = importlib.util.spec_from_file_location("watercooler_mcp_git_sync", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def test_git_sync_manager_interface_exists():
    git_sync = _import_git_sync()
    assert hasattr(git_sync, "GitSyncManager")


def test_pull_calls_git_with_env(monkeypatch, tmp_path):
    git_sync = _import_git_sync()
    calls = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((tuple(cmd), kwargs))
        # Simulate successful call
        class R:  # minimal result shim
            returncode = 0
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path,
        ssh_key_path=tmp_path / "key",
    )
    # Trigger pull
    ok = mgr.pull()
    assert ok is True
    # Verify env propagated and --rebase used
    assert any("git" in c[0][0] and "pull" in c[0] for c in calls)
    envs = [kw.get("env") for _, kw in calls if kw.get("env")]
    assert envs, "Expected env propagation to subprocess.run"
    assert any("GIT_SSH_COMMAND" in env for env in envs)


def test_commit_and_push_retry_on_reject(monkeypatch, tmp_path):
    git_sync = _import_git_sync()
    calls = {"push": 0}

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        args = tuple(cmd)
        # Simulate normal success for clone/config/add/commit
        if args[:2] in (("git", "clone"), ("git", "config"), ("git", "add"), ("git", "commit")):
            class R: returncode = 0
            return R()
        if args[:3] == ("git", "diff", "--cached"):
            # Indicate there ARE staged changes (returncode != 0)
            class R: returncode = 1
            return R()
        if args[:2] == ("git", "push"):
            calls["push"] += 1
            if calls["push"] == 1:
                raise subprocess.CalledProcessError(1, cmd)
            class R: returncode = 0
            return R()
        if args[:2] == ("git", "pull"):
            class R: returncode = 0
            return R()
        class R: returncode = 0
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path,
        ssh_key_path=tmp_path / "key",
    )
    # Ensure pull() inside commit_and_push returns True
    pulls = {"n": 0}
    def fake_pull():
        pulls["n"] += 1
        return True
    mgr.pull = fake_pull  # type: ignore[assignment]

    ok = mgr.commit_and_push("msg")
    assert ok is True
    assert calls["push"] == 2
    assert pulls["n"] == 1


def test_commit_and_push_retry_exhausted(monkeypatch, tmp_path):
    git_sync = _import_git_sync()
    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        args = tuple(cmd)
        if args[:2] in (("git", "clone"), ("git", "config"), ("git", "add"), ("git", "commit")):
            class R: returncode = 0
            return R()
        if args[:3] == ("git", "diff", "--cached"):
            class R: returncode = 1
            return R()
        if args[:2] == ("git", "push"):
            raise subprocess.CalledProcessError(1, cmd)
        if args[:2] == ("git", "pull"):
            class R: returncode = 0
            return R()
        class R: returncode = 0
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path,
        ssh_key_path=tmp_path / "key",
    )
    mgr.pull = lambda: True  # type: ignore[assignment]
    ok = mgr.commit_and_push("msg")
    assert ok is False


def test_with_sync_pull_failure_raises(monkeypatch, tmp_path):
    git_sync = _import_git_sync()
    # Avoid real git clone/config
    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        args = tuple(cmd)
        if args[:2] in (("git", "clone"), ("git", "config")):
            class R: returncode = 0
            return R()
        class R: returncode = 0
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path,
        ssh_key_path=tmp_path / "key",
    )
    mgr.pull = lambda: False  # type: ignore[assignment]
    with pytest.raises(git_sync.GitPullError):
        mgr.with_sync(lambda: None, "msg")


def test_with_sync_push_failure_raises(monkeypatch, tmp_path):
    git_sync = _import_git_sync()
    # Avoid real git clone/config
    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        args = tuple(cmd)
        if args[:2] in (("git", "clone"), ("git", "config")):
            class R: returncode = 0
            return R()
        class R: returncode = 0
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path,
        ssh_key_path=tmp_path / "key",
    )
    mgr.pull = lambda: True  # type: ignore[assignment]
    called = {"op": 0}
    def op():
        called["op"] += 1
    mgr.commit_and_push = lambda msg: False  # type: ignore[assignment]
    with pytest.raises(git_sync.GitPushError):
        mgr.with_sync(op, "msg")
    assert called["op"] == 1


def test_with_sync_operation_exception(monkeypatch, tmp_path):
    git_sync = _import_git_sync()
    # Avoid real git clone/config
    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        args = tuple(cmd)
        if args[:2] in (("git", "clone"), ("git", "config")):
            class R: returncode = 0
            return R()
        class R: returncode = 0
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path,
        ssh_key_path=tmp_path / "key",
    )
    mgr.pull = lambda: True  # type: ignore[assignment]
    called = {"commit": 0}
    def fake_commit(msg):
        called["commit"] += 1
        return True
    mgr.commit_and_push = fake_commit  # type: ignore[assignment]

    def op():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        mgr.with_sync(op, "msg")
    # commit_and_push should not be called when op fails
    assert called["commit"] == 0
