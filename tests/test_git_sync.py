import os
import json
import logging
import shutil
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

        class R:  # minimal result shim
            returncode = 0
            stdout = ""
            stderr = ""

        if tuple(cmd[:2]) == ("git", "ls-remote"):
            R.stdout = "abc\trefs/heads/main\n"

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
    mgr._last_pull_error = "merge conflict"  # type: ignore[attr-defined]
    with pytest.raises(git_sync.GitPullError):
        mgr.with_sync(lambda: None, "msg")


def test_with_sync_pull_failure_network_error(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

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

    pulls = {"called": 0}
    def fake_pull():
        pulls["called"] += 1
        mgr._last_pull_error = "failed in sandbox: permission denied"  # type: ignore[attr-defined]
        return False

    mgr.pull = fake_pull  # type: ignore[assignment]

    mgr.commit_and_push = lambda msg: True  # type: ignore[assignment]

    with pytest.raises(git_sync.GitPullError) as excinfo:
        mgr.with_sync(lambda: None, "msg")

    assert pulls["called"] == 1
    assert "failed to pull" in str(excinfo.value).lower()


def test_pull_skips_when_remote_missing(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        args = tuple(cmd)
        if args[:2] in (("git", "clone"), ("git", "config")):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""

            return R()

        if args[:2] == ("git", "ls-remote"):
            raise subprocess.CalledProcessError(
                128,
                cmd,
                stderr="fatal: repository 'git@github.com:org/threads.git' not found",
            )

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path,
        ssh_key_path=None,
        enable_provision=False,
        remote_allowed=True,
    )

    assert mgr.pull() is True


def test_pull_skips_when_remote_has_no_refs(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    calls = {"pull": 0, "ls_remote": 0}

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        args = tuple(cmd) if isinstance(cmd, (list, tuple)) else ()

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        if args[:2] == ("git", "clone"):
            target = Path(cmd[-1])  # type: ignore[index]
            (target / ".git").mkdir(parents=True, exist_ok=True)
            return R()

        if args[:2] == ("git", "config"):
            return R()

        if args[:2] == ("git", "ls-remote"):
            calls["ls_remote"] += 1
            return R()

        if args[:2] == ("git", "pull"):
            calls["pull"] += 1
            return R()

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    repo_dir = tmp_path / "threads"

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=repo_dir,
        ssh_key_path=None,
    )

    calls["pull"] = 0

    ok = mgr.pull()

    assert ok is True
    assert calls["ls_remote"] >= 1
    assert calls["pull"] == 0
    assert getattr(mgr, "_remote_empty", False) is True


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


def test_clone_auto_provisions_missing_repo(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    monkeypatch.setenv("WATERCOOLER_THREADS_AUTO_PROVISION", "1")
    monkeypatch.setenv("WATERCOOLER_THREADS_CREATE_CMD", "echo create {slug}")

    call_log = {"clone": 0, "provision": 0, "init": 0}

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "clone":
            call_log["clone"] += 1
            if call_log["clone"] == 1:
                raise subprocess.CalledProcessError(
                    128,
                    cmd,
                    stderr="remote: Repository not found",
                )
            class R:
                returncode = 0
                stdout = ""
                stderr = ""

            return R()

        if kwargs.get("shell"):
            call_log["provision"] += 1

            class R:
                returncode = 0
                stdout = "created"
                stderr = ""

            return R()

        if isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "init":
            call_log["init"] += 1

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:mostlyharmless-ai/watercooler-dashboard-threads.git",
        local_path=tmp_path / "threads",
        ssh_key_path=None,
        threads_slug="mostlyharmless-ai/watercooler-dashboard-threads",
        code_repo="mostlyharmless-ai/watercooler-dashboard",
        enable_provision=True,
    )

    assert isinstance(mgr, git_sync.GitSyncManager)
    assert call_log["clone"] == 2
    assert call_log["provision"] == 1
    assert call_log["init"] == 0


def test_clone_provision_failure_surfaces_error(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    monkeypatch.setenv("WATERCOOLER_THREADS_AUTO_PROVISION", "1")
    monkeypatch.setenv("WATERCOOLER_THREADS_CREATE_CMD", "echo create {slug}")

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "clone":
            raise subprocess.CalledProcessError(
                128,
                cmd,
                stderr="fatal: repository 'git@github.com:org/threads.git' not found",
            )
        if kwargs.get("shell"):
            raise subprocess.CalledProcessError(1, cmd, stderr="boom")

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(git_sync.GitSyncError) as excinfo:
        git_sync.GitSyncManager(
            repo_url="git@github.com:org/threads.git",
            local_path=tmp_path / "threads",
            ssh_key_path=None,
            threads_slug="org/threads",
            code_repo="org/main",
            enable_provision=True,
        )

    assert "auto-provision" in str(excinfo.value).lower()


def test_clone_attempted_even_when_branch_unpublished(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    calls = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(tuple(cmd) if isinstance(cmd, (list, tuple)) else cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path / "threads",
        ssh_key_path=None,
        threads_slug="org/threads",
        code_repo="org/main",
        enable_provision=True,
        remote_allowed=False,
    )

    assert isinstance(mgr, git_sync.GitSyncManager)
    assert any(isinstance(call, tuple) and call[:2] == ("git", "clone") for call in calls)
    assert all(not (isinstance(call, tuple) and call[:2] == ("git", "init")) for call in calls)


def test_commit_skips_push_when_remote_disabled(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    calls = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(cmd, (list, tuple)):
            calls.append(tuple(cmd))

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        if isinstance(cmd, (list, tuple)) and tuple(cmd)[:3] == ("git", "diff", "--cached"):
            R.returncode = 1  # Emulate staged changes

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path / "threads",
        ssh_key_path=None,
        threads_slug="org/threads",
        code_repo="org/main",
        enable_provision=True,
        remote_allowed=False,
    )

    ok = mgr.commit_and_push("msg")

    assert ok is True
    assert all(call[:2] != ("git", "push") for call in calls if isinstance(call, tuple))


def test_bootstrap_local_repo_when_remote_missing(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    calls = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if (
            isinstance(cmd, (list, tuple))
            and len(cmd) >= 2
            and cmd[0] == "git"
            and cmd[1] == "clone"
        ):
            raise subprocess.CalledProcessError(
                128,
                cmd,
                stderr="fatal: repository 'git@github.com:org/threads.git' not found",
            )

        calls.append(tuple(cmd) if isinstance(cmd, (list, tuple)) else cmd)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path / "threads",
        ssh_key_path=None,
        threads_slug="org/threads",
        code_repo="org/main",
        enable_provision=False,
        remote_allowed=False,
    )

    assert isinstance(mgr, git_sync.GitSyncManager)
    assert any(isinstance(call, tuple) and call[:2] == ("git", "init") for call in calls)


def test_pull_reclones_when_repo_removed(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    calls = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        record = tuple(cmd) if isinstance(cmd, (list, tuple)) else cmd
        calls.append(record)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    repo_dir = tmp_path / "threads"

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=repo_dir,
        ssh_key_path=None,
    )

    # Simulate operator removing the local checkout after manager creation
    calls.clear()
    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    assert mgr.pull() is True
    assert any(call[:2] == ("git", "clone") for call in calls if isinstance(call, tuple))


def test_ensure_branch_fetches_remote_branch(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    calls = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        args = tuple(cmd) if isinstance(cmd, (list, tuple)) else cmd
        calls.append(args)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        if isinstance(cmd, (list, tuple)):
            if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
                R.stdout = "main\n"
            if cmd[:4] == ["git", "show-ref", "--verify", f"refs/heads/feature-branch"]:
                R.returncode = 1
            if cmd[:3] == ["git", "ls-remote", "origin"]:
                R.stdout = "abc\torigin/main\n"
            if cmd[:4] == ["git", "ls-remote", "--heads", "origin"]:
                if cmd[4] == "feature-branch":
                    R.stdout = "123\trefs/heads/feature-branch\n"
            if cmd[:4] == ["git", "rev-parse", "--abbrev-ref", "@{u}"]:
                R.returncode = 1
            if cmd[:3] == ["git", "branch", "--set-upstream-to"]:
                R.stderr = ""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path / "threads",
        ssh_key_path=None,
    )

    calls.clear()

    ok = mgr.ensure_branch("feature-branch")

    assert ok is True
    assert any(call[:3] == ("git", "fetch", "origin") and "feature-branch:refs/heads/feature-branch" in call[3] for call in calls if isinstance(call, tuple))
    assert any(call[:3] == ("git", "branch", "--set-upstream-to") for call in calls if isinstance(call, tuple))


def test_commit_and_push_network_failure_aborts(monkeypatch, tmp_path):
    git_sync = _import_git_sync()

    calls = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(cmd, (list, tuple)):
            calls.append(tuple(cmd))
        args = tuple(cmd) if isinstance(cmd, (list, tuple)) else ()

        if args[:2] in (("git", "clone"), ("git", "config"), ("git", "add"), ("git", "commit")):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""

            return R()

        if args[:3] == ("git", "diff", "--cached"):
            class R:
                returncode = 1
                stdout = ""
                stderr = ""

            return R()

        if args[:2] == ("git", "ls-remote"):
            raise subprocess.CalledProcessError(
                128,
                cmd,
                stderr="ssh: Could not resolve hostname github.com\nfatal: Could not read from remote repository.",
            )

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    mgr = git_sync.GitSyncManager(
        repo_url="git@github.com:org/threads.git",
        local_path=tmp_path / "threads",
        ssh_key_path=None,
        threads_slug="org/threads",
        code_repo="org/main",
        enable_provision=True,
        remote_allowed=True,
    )

    ok = mgr.commit_and_push("msg")

    assert ok is False
    assert mgr._last_push_error is not None
    # No push attempts should occur because we bail early on ls-remote failure
    assert all(call[:2] != ("git", "push") for call in calls if isinstance(call, tuple))
