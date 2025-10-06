from __future__ import annotations

import re
from pathlib import Path
from .fs import utcnow_iso


STAT_RE = re.compile(r"^Status:\s*(?P<val>.+)$", re.IGNORECASE | re.MULTILINE)
BALL_RE = re.compile(r"^Ball:\s*(?P<val>.+)$", re.IGNORECASE | re.MULTILINE)
UPD_RE = re.compile(r"^Updated:\s*(?P<val>.+)$", re.IGNORECASE | re.MULTILINE)
TITLE_RE = re.compile(r"^#\s*(?P<val>.+)$", re.MULTILINE)
CLOSED_STATES = {"done", "closed", "merged", "resolved"}


def _last_entry_iso(s: str) -> str | None:
    m = UPD_RE.search(s)
    return m.group("val").strip() if m else None


def _normalize_status(status: str) -> str:
    v = status.strip().lower()
    return v


def thread_meta(p: Path) -> tuple[str, str, str, str]:
    s = p.read_text(encoding="utf-8") if p.exists() else ""
    title = TITLE_RE.search(s).group("val").strip() if TITLE_RE.search(s) else p.stem
    status = _normalize_status(STAT_RE.search(s).group("val") if STAT_RE.search(s) else "open")
    ball = (BALL_RE.search(s).group("val").strip() if BALL_RE.search(s) else "unknown")
    last = _last_entry_iso(s) or utcnow_iso()
    return title, status, ball, last
