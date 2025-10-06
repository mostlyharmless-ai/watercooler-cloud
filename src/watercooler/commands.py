from __future__ import annotations

from pathlib import Path
from typing import Optional

from .fs import write, thread_path, lock_path_for_topic, utcnow_iso
from .lock import AdvisoryLock
from .header import bump_header
from .metadata import thread_meta
from .agents import _counterpart_of, _canonical_agent


def init_thread(
    topic: str,
    *,
    threads_dir: Path,
    title: Optional[str] = None,
    status: str = "open",
    ball: str = "codex",
    body: str | None = None,
) -> Path:
    threads_dir.mkdir(parents=True, exist_ok=True)
    tp = thread_path(topic, threads_dir)
    if tp.exists():
        return tp

    lp = lock_path_for_topic(topic, threads_dir)
    with AdvisoryLock(lp, timeout=2, ttl=10, force_break=False):
        if tp.exists():
            return tp
        hdr_title = title or topic.replace("-", " ").strip()
        now = utcnow_iso()
        header = (
            f"Title: {hdr_title}\n"
            f"Status: {status}\n"
            f"Ball: {ball}\n"
            f"Updated: {now}\n\n"
            f"# {hdr_title}\n"
        )
        content = header + (body or "")
        write(tp, content)
    return tp


def append_entry(
    topic: str,
    *,
    threads_dir: Path,
    author: str | None = None,
    body: str,
    bump_status: str | None = None,
    bump_ball: str | None = None,
) -> Path:
    tp = thread_path(topic, threads_dir)
    lp = lock_path_for_topic(topic, threads_dir)
    with AdvisoryLock(lp, timeout=2, ttl=10, force_break=False):
        if not tp.exists():
            # Initialize minimal header if missing
            init_thread(topic, threads_dir=threads_dir)
        s = tp.read_text(encoding="utf-8")
        # Optionally update header values
        if bump_status or bump_ball:
            s = bump_header(s, status=bump_status, ball=bump_ball)
        # Always update Updated header
        s = bump_header(s, status=None, ball=None)
        now = utcnow_iso()
        who = f" by {author}" if author else ""
        entry = f"\n\n---\n\n- Updated: {now}{who}\n\n{body}\n"
        write(tp, s + entry)
    return tp


def set_status(topic: str, *, threads_dir: Path, status: str) -> Path:
    tp = thread_path(topic, threads_dir)
    lp = lock_path_for_topic(topic, threads_dir)
    with AdvisoryLock(lp, timeout=2, ttl=10, force_break=False):
        s = tp.read_text(encoding="utf-8") if tp.exists() else ""
        s = bump_header(s, status=status)
        write(tp, s)
    return tp


def set_ball(topic: str, *, threads_dir: Path, ball: str) -> Path:
    tp = thread_path(topic, threads_dir)
    lp = lock_path_for_topic(topic, threads_dir)
    with AdvisoryLock(lp, timeout=2, ttl=10, force_break=False):
        s = tp.read_text(encoding="utf-8") if tp.exists() else ""
        s = bump_header(s, ball=ball)
        write(tp, s)
    return tp


def list_threads(*, threads_dir: Path) -> list[tuple[str, str, str, str, Path]]:
    """Return list of (title, status, ball, updated_iso, path) for threads."""
    out: list[tuple[str, str, str, str, Path]] = []
    if not threads_dir.exists():
        return out
    for p in sorted(threads_dir.glob("*.md")):
        title, status, ball, updated = thread_meta(p)
        out.append((title, status, ball, updated, p))
    return out


def say(
    topic: str,
    *,
    threads_dir: Path,
    author: str | None = None,
    body: str,
) -> Path:
    # Convenience wrapper: append without header bumps
    return append_entry(topic, threads_dir=threads_dir, author=author, body=body)


def ack(
    topic: str,
    *,
    threads_dir: Path,
    author: str | None = None,
    note: str | None = None,
    registry: dict | None = None,
) -> Path:
    # Acknowledge without flipping ball; add a terse note
    text = note or "ack"
    return append_entry(topic, threads_dir=threads_dir, author=author, body=text)


def reindex(*, threads_dir: Path, out_file: Path | None = None) -> Path:
    """Write a Markdown index summarizing threads."""
    rows = list_threads(threads_dir=threads_dir)
    out_path = out_file or (threads_dir / "index.md")
    lines = ["# Watercooler Index", "", "Updated | Status | Ball | Title | Path", "---|---|---|---|---"]
    for title, status, ball, updated, path in rows:
        rel = path.relative_to(threads_dir)
        lines.append(f"{updated} | {status} | {ball} | {title} | {rel}")
    write(out_path, "\n".join(lines) + "\n")
    return out_path


def search(*, threads_dir: Path, query: str) -> list[tuple[Path, int, str]]:
    """Naive case-insensitive search; returns (path, line_no, line)."""
    q = query.lower()
    hits: list[tuple[Path, int, str]] = []
    for p in sorted(threads_dir.glob("*.md")):
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
                if q in line.lower():
                    hits.append((p, i, line))
        except Exception:
            continue
    return hits


def web_export(*, threads_dir: Path, out_file: Path | None = None) -> Path:
    """Export a simple static HTML index summarizing threads."""
    rows = list_threads(threads_dir=threads_dir)
    out_path = out_file or (threads_dir / "index.html")
    tbody = []
    for title, status, ball, updated, path in rows:
        rel = path.relative_to(threads_dir)
        tbody.append(
            f"<tr><td>{updated}</td><td>{status}</td><td>{ball}</td><td>{title}</td><td><a href=\"{rel}\">{rel}</a></td></tr>"
        )
    html = """
<!doctype html>
<html lang="en">
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Watercooler Index</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Calibri,sans-serif;margin:2rem}
  table{border-collapse:collapse;width:100%}
  th,td{border:1px solid #ddd;padding:.5rem;text-align:left}
  th{background:#f5f5f5}
  tr:nth-child(even){background:#fafafa}
  code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
</style>
<h1>Watercooler Index</h1>
<table>
  <thead><tr><th>Updated</th><th>Status</th><th>Ball</th><th>Title</th><th>Path</th></tr></thead>
  <tbody>
    BODY
  </tbody>
</table>
</html>
""".replace("BODY", "\n    ".join(tbody))
    write(out_path, html)
    return out_path
