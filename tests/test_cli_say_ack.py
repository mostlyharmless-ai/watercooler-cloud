from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "watercooler.cli", *args], capture_output=True, text=True, cwd=cwd)


def test_say_and_ack(tmp_path: Path):
    # init
    cp = run_cli("init-thread", "topic3", "--threads-dir", str(tmp_path))
    assert cp.returncode == 0
    # say
    cp = run_cli("say", "topic3", "--threads-dir", str(tmp_path), "--author", "dev", "--body", "Heads-up")
    assert cp.returncode == 0
    s = (tmp_path / "topic3.md").read_text(encoding="utf-8")
    assert "Heads-up" in s
    # ack
    cp = run_cli("ack", "topic3", "--threads-dir", str(tmp_path), "--author", "dev")
    assert cp.returncode == 0
    s = (tmp_path / "topic3.md").read_text(encoding="utf-8")
    assert "ack" in s.lower()


def test_handoff(tmp_path: Path):
    # init with ball=codex
    cp = run_cli("init-thread", "topic4", "--threads-dir", str(tmp_path), "--ball", "codex")
    assert cp.returncode == 0
    s = (tmp_path / "topic4.md").read_text(encoding="utf-8")
    assert "Ball: codex" in s
    # handoff flips ball to counterpart (claude by default)
    cp = run_cli("handoff", "topic4", "--threads-dir", str(tmp_path), "--author", "codex", "--note", "your turn")
    assert cp.returncode == 0
    s = (tmp_path / "topic4.md").read_text(encoding="utf-8")
    assert "Ball: claude" in s
    assert "your turn" in s

