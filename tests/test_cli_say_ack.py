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

