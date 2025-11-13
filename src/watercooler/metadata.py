from __future__ import annotations

import re
from pathlib import Path
from .fs import utcnow_iso


STAT_RE = re.compile(r"^Status:\s*(?P<val>.+)$", re.IGNORECASE | re.MULTILINE)
BALL_RE = re.compile(r"^Ball:\s*(?P<val>.+)$", re.IGNORECASE | re.MULTILINE)
UPD_RE = re.compile(r"^Updated:\s*(?P<val>.+)$", re.IGNORECASE | re.MULTILINE)
UPD_BY_RE = re.compile(r"^-\s*Updated:\s*(?P<ts>[^\n]+?)(?:\s+by\s+(?P<who>[^\n]+))?\s*$", re.IGNORECASE | re.MULTILINE)
# Match new Entry format: "Entry: Agent (user) 2025-10-07T19:42:21Z"
ENTRY_RE = re.compile(r"^Entry:\s*(?P<who>[^\d]+?)\s+(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"^#\s*(?P<val>.+)$", re.MULTILINE)
CLOSED_STATES = {"done", "closed", "merged", "resolved", "abandoned", "obsolete"}


def _last_entry_iso(s: str) -> str | None:
    """Extract timestamp from last entry (supports both old and new formats)."""
    # Try new Entry format first
    hits = list(ENTRY_RE.finditer(s))
    if hits:
        return hits[-1].group("ts").strip()
    # Fallback to old Updated format
    m = UPD_RE.search(s)
    return m.group("val").strip() if m else None


def _last_entry_who(s: str) -> str | None:
    """Extract author of the last entry (supports both old and new formats)."""
    # Try new Entry format first
    hits = list(ENTRY_RE.finditer(s))
    if hits:
        return hits[-1].group("who").strip()
    # Fallback to old Updated format
    hits = list(UPD_BY_RE.finditer(s))
    if not hits:
        return None
    who = hits[-1].group("who")
    return who.strip() if who else None


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


def is_closed(status: str) -> bool:
    return _normalize_status(status) in CLOSED_STATES


def last_entry_by(p: Path) -> str | None:
    s = p.read_text(encoding="utf-8") if p.exists() else ""
    return _last_entry_who(s)
