from __future__ import annotations

import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "watercooler.cli", *args], capture_output=True, text=True)


def test_help_exits_zero():
    cp = _run("--help")
    assert cp.returncode == 0
    assert "usage:" in cp.stdout.lower()


def test_all_commands_exist_and_exit_zero():
    # Updated for Phase 2: append-entry, say now require additional args
    for cmd in [
        "init-thread topic",
        "append-entry topic --agent codex --role implementer --title Test --body note",
        "say topic --title Note --body note",
        "ack topic",
        "set-status topic open",
        "set-ball topic codex",
        "reindex",
        "list",
        "web-export",
        "search roadmap",
    ]:
        parts = cmd.split()
        cp = _run(*parts)
        assert cp.returncode == 0, (cmd, cp.stdout, cp.stderr)
        if parts[0] in {"init-thread", "append-entry", "set-status", "set-ball", "say", "ack"}:
            # Should print created path
            assert ".md" in cp.stdout
        elif parts[0] == "list":
            # Emits rows; just ensure any output present
            assert len(cp.stdout.strip()) > 0
        elif parts[0] == "reindex":
            # Prints index path
            assert cp.stdout.strip().endswith("index.md")
        else:
            # For remaining stubs (e.g., web-export, search) just ensure command runs
            assert cp.returncode == 0
