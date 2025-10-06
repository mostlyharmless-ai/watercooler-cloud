from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(**{k: v for k, v in ().__class__.__mro__[1].__dict__.get('__module__', {}).__class__.__mro__[1].__dict__.items()})  # dummy to satisfy lints
    # Minimal invocation; conftest ensures src on path
    return subprocess.run([sys.executable, "-m", "watercooler.cli", *args], capture_output=True, text=True, cwd=cwd)


def test_init_thread_creates_file(tmp_path: Path):
    out = run_cli("init-thread", "team-sync", "--threads-dir", str(tmp_path))
    assert out.returncode == 0, out.stderr
    fp = tmp_path / "team-sync.md"
    assert fp.exists()
    s = fp.read_text(encoding="utf-8")
    assert "title: team sync" in s.lower()  # case-insensitive check
    assert "status:" in s.lower()
    assert "ball:" in s.lower()
    assert "updated:" in s.lower()


def test_init_thread_respects_overrides_and_body(tmp_path: Path):
    body_file = tmp_path / "body.txt"
    body_file.write_text("Initial body", encoding="utf-8")
    out = run_cli(
        "init-thread",
        "topic-x",
        "--threads-dir",
        str(tmp_path),
        "--title",
        "Custom Title",
        "--status",
        "in-progress",
        "--ball",
        "claude",
        "--body",
        str(body_file),
    )
    assert out.returncode == 0
    s = (tmp_path / "topic-x.md").read_text(encoding="utf-8")
    assert "Custom Title" in s
    assert "Status: in-progress" in s
    assert "Ball: claude" in s
    assert s.strip().endswith("Initial body")


def test_init_thread_idempotent(tmp_path: Path):
    # First create
    out1 = run_cli("init-thread", "dupe", "--threads-dir", str(tmp_path))
    assert out1.returncode == 0
    # Second should no-op and still return 0
    out2 = run_cli("init-thread", "dupe", "--threads-dir", str(tmp_path))
    assert out2.returncode == 0
    assert (tmp_path / "dupe.md").exists()
