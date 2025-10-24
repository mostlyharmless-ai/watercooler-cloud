from __future__ import annotations

from pathlib import Path
from typing import Optional

from .fs import write, thread_path, lock_path_for_topic, utcnow_iso, read_body
from .lock import AdvisoryLock
from .header import bump_header
from .metadata import thread_meta, is_closed, last_entry_by
from .agents import _counterpart_of, _canonical_agent, _default_agent_and_role
from .config import load_template, resolve_templates_dir
from .templates import _fill_template


def init_thread(
    topic: str,
    *,
    threads_dir: Path,
    title: Optional[str] = None,
    status: str = "OPEN",
    ball: str = "codex",
    body: str | None = None,
    owner: str | None = None,
    participants: str | None = None,
    templates_dir: Path | None = None,
) -> Path:
    """Initialize a new thread using the topic thread template.

    Args:
        topic: Thread topic identifier
        threads_dir: Directory containing threads
        title: Optional title override
        status: Initial status (default: "OPEN")
        ball: Initial ball owner (default: "codex")
        body: Optional initial body text
        owner: Thread owner (default: "Team")
        participants: Comma-separated list of participants
        templates_dir: Optional templates directory override
    """
    threads_dir.mkdir(parents=True, exist_ok=True)
    tp = thread_path(topic, threads_dir)
    if tp.exists():
        return tp

    lp = lock_path_for_topic(topic, threads_dir)
    with AdvisoryLock(lp, timeout=2, ttl=10, force_break=False):
        if tp.exists():
            return tp

        # Load thread template
        try:
            template = load_template("_TEMPLATE_topic_thread.md", templates_dir)
        except FileNotFoundError:
            # Fallback to simple format if template not found
            hdr_title = title or topic.replace("-", " ").strip()
            now = utcnow_iso()
            content = (
                f"Title: {hdr_title}\n"
                f"Status: {status.upper()}\n"
                f"Ball: {ball}\n"
                f"Updated: {now}\n\n"
                f"# {hdr_title}\n"
            )
            if body:
                content += body
            write(tp, content)
            return tp

        # Fill template
        now = utcnow_iso()
        hdr_title = title or topic.replace("-", " ").strip()
        mapping = {
            "TOPIC": topic,
            "topic": topic,
            "Short title": hdr_title,
            "OWNER": owner or "Team",
            "PARTICIPANTS": participants or "Team, Codex, Claude",
            "NOWUTC": now,
            "UTC": now,
            "BALL": ball,
            "STATUS": status.upper(),  # Always uppercase for consistency
        }
        content = _fill_template(template, mapping)

        # Append body if provided
        if body:
            content = content.rstrip() + "\n\n" + body.rstrip() + "\n"

        write(tp, content)
    return tp


def append_entry(
    topic: str,
    *,
    threads_dir: Path,
    agent: str,
    role: str,
    title: str,
    entry_type: str = "Note",
    body: str,
    status: str | None = None,
    ball: str | None = None,
    templates_dir: Path | None = None,
    registry: dict | None = None,
    user_tag: str | None = None,
) -> Path:
    """Append a structured entry to a thread.

    Args:
        topic: Thread topic
        threads_dir: Directory containing threads
        agent: Agent name (will be canonicalized with user tag)
        role: Agent role (planner, critic, implementer, tester, pm, scribe)
        title: Entry title
        entry_type: Entry type (Note, Plan, Decision, PR, Closure)
        body: Entry body text
        status: Optional status update
        ball: Optional ball update (if None, auto-flips to counterpart)
        templates_dir: Optional templates directory
        registry: Optional agent registry
        user_tag: Optional user tag for agent identification (GitHub username)

    Returns:
        Path to updated thread file
    """
    tp = thread_path(topic, threads_dir)
    
    # Initialize thread if it doesn't exist (before acquiring lock)
    if not tp.exists():
        init_thread(topic, threads_dir=threads_dir)
    
    lp = lock_path_for_topic(topic, threads_dir)
    with AdvisoryLock(lp, timeout=2, ttl=10, force_break=False):
        s = tp.read_text(encoding="utf-8")

        # Load entry template
        try:
            template = load_template("_TEMPLATE_entry_block.md", templates_dir)
        except FileNotFoundError:
            # Fallback to simple format
            now = utcnow_iso()
            canonical = _canonical_agent(agent, registry, user_tag=user_tag)
            who = f" by {canonical}"
            entry = f"\n\n---\n\n- Updated: {now}{who}\n\n{body}\n"
            s = bump_header(s, status=status, ball=ball)
            write(tp, s + entry)
            return tp

        # Fill entry template
        now = utcnow_iso()
        canonical_agent = _canonical_agent(agent, registry, user_tag=user_tag)

        mapping = {
            "UTC": now,
            "AGENT": canonical_agent,
            "TYPE": entry_type,
            "ROLE": role,
            "TITLE": title,
            "BODY": body.rstrip() + "\n",
        }
        filled_entry = _fill_template(template, mapping)

        # If template doesn't have BODY placeholder, append body after template
        if ("{{BODY}}" not in template) and ("<BODY>" not in template) and body.strip():
            filled_entry = filled_entry.rstrip() + "\n\n" + body.rstrip() + "\n"

        # Auto-flip ball if not explicitly provided
        final_ball = ball if ball is not None else _counterpart_of(canonical_agent, registry)

        # Update header
        s = bump_header(s, status=status, ball=final_ball)

        # Append entry
        new_text = s.rstrip() + "\n\n" + filled_entry
        write(tp, new_text)
        return tp


def set_status(topic: str, *, threads_dir: Path, status: str) -> Path:
    tp = thread_path(topic, threads_dir)
    lp = lock_path_for_topic(topic, threads_dir)
    with AdvisoryLock(lp, timeout=2, ttl=10, force_break=False):
        s = tp.read_text(encoding="utf-8") if tp.exists() else ""
        # Normalize status to uppercase for consistency
        s = bump_header(s, status=status.upper())
        write(tp, s)
    return tp


def set_ball(topic: str, *, threads_dir: Path, ball: str) -> Path:
    tp = thread_path(topic, threads_dir)
    lp = lock_path_for_topic(topic, threads_dir)
    with AdvisoryLock(lp, timeout=2, ttl=10, force_break=False):
        if not tp.exists():
            init_thread(topic, threads_dir=threads_dir)
        s = tp.read_text(encoding="utf-8")
        s = bump_header(s, ball=ball)
        write(tp, s)
    return tp


def list_threads(*, threads_dir: Path, open_only: bool | None = None) -> list[tuple[str, str, str, str, Path, bool]]:
    """Return list of (title, status, ball, updated_iso, path, is_new)."""
    out: list[tuple[str, str, str, str, Path, bool]] = []
    if not threads_dir.exists():
        return out
    for p in sorted(threads_dir.glob("*.md")):
        title, status, ball, updated = thread_meta(p)
        if open_only is True and is_closed(status):
            continue
        if open_only is False and not is_closed(status):
            continue
        who = (last_entry_by(p) or "").strip().lower()
        # NEW marker if last entry author differs from current ball owner
        is_new = bool(who and who != (ball or "").strip().lower()) and not is_closed(status)
        out.append((title, status, ball, updated, p, is_new))
    return out


def say(
    topic: str,
    *,
    threads_dir: Path,
    agent: str | None = None,
    role: str | None = None,
    title: str,
    entry_type: str = "Note",
    body: str,
    status: str | None = None,
    ball: str | None = None,
    templates_dir: Path | None = None,
    registry: dict | None = None,
    user_tag: str | None = None,
) -> Path:
    """Quick team note with auto-ball-flip.

    Convenience wrapper for append_entry that defaults agent to Team
    and auto-flips ball to counterpart unless explicitly provided.

    Args:
        topic: Thread topic
        threads_dir: Directory containing threads
        agent: Agent name (defaults to Team via _default_agent_and_role)
        role: Agent role (defaults to role from registry)
        title: Entry title (required)
        entry_type: Entry type (default: "Note")
        body: Entry body text
        status: Optional status update
        ball: Optional ball update (if not provided, auto-flips)
        templates_dir: Optional templates directory
        registry: Optional agent registry
        user_tag: Optional user tag for agent identification (GitHub username)
    """
    # Default agent to Team
    default_agent, default_role = _default_agent_and_role(registry)
    final_agent = agent if agent is not None else default_agent
    final_role = role if role is not None else default_role

    return append_entry(
        topic,
        threads_dir=threads_dir,
        agent=final_agent,
        role=final_role,
        title=title,
        entry_type=entry_type,
        body=body,
        status=status,
        ball=ball,  # append_entry will auto-flip if None
        templates_dir=templates_dir,
        registry=registry,
        user_tag=user_tag,
    )


def ack(
    topic: str,
    *,
    threads_dir: Path,
    agent: str | None = None,
    role: str | None = None,
    title: str | None = None,
    entry_type: str = "Note",
    body: str | None = None,
    status: str | None = None,
    ball: str | None = None,
    templates_dir: Path | None = None,
    registry: dict | None = None,
    user_tag: str | None = None,
) -> Path:
    """Acknowledge without auto-flipping ball.

    Like say() but does NOT auto-flip ball - ball only changes if explicitly provided.
    Default title is "Ack".

    Args:
        topic: Thread topic
        threads_dir: Directory containing threads
        agent: Agent name (defaults to Team)
        role: Agent role (defaults to role from registry)
        title: Entry title (defaults to "Ack")
        entry_type: Entry type (default: "Note")
        body: Entry body text (defaults to "ack")
        status: Optional status update
        ball: Optional ball update (does NOT auto-flip)
        templates_dir: Optional templates directory
        registry: Optional agent registry
        user_tag: Optional user tag for agent identification (GitHub username)
    """
    # Default agent to Team
    default_agent, default_role = _default_agent_and_role(registry)
    final_agent = agent if agent is not None else default_agent
    final_role = role if role is not None else default_role
    final_title = title if title is not None else "Ack"
    final_body = body if body is not None else "ack"

    # If no ball specified, preserve current ball (don't auto-flip)
    final_ball = ball
    if final_ball is None:
        tp = thread_path(topic, threads_dir)
        if tp.exists():
            _, _, current_ball, _ = thread_meta(tp)
            final_ball = current_ball  # Preserve current ball

    return append_entry(
        topic,
        threads_dir=threads_dir,
        agent=final_agent,
        role=final_role,
        title=final_title,
        entry_type=entry_type,
        body=final_body,
        status=status,
        ball=final_ball,  # Explicit ball (no auto-flip)
        templates_dir=templates_dir,
        registry=registry,
        user_tag=user_tag,
    )


def handoff(
    topic: str,
    *,
    threads_dir: Path,
    agent: str | None = None,
    role: str = "pm",
    note: str | None = None,
    registry: dict | None = None,
    templates_dir: Path | None = None,
    user_tag: str | None = None,
) -> Path:
    """Flip the Ball to the counterpart and append a handoff entry.

    Args:
        topic: Thread topic
        threads_dir: Directory containing threads
        agent: Agent performing handoff (defaults to Team)
        role: Agent role (default: "pm" for project management)
        note: Optional custom handoff message
        registry: Optional agent registry
        templates_dir: Optional templates directory
        user_tag: Optional user tag for agent identification (GitHub username)
    """
    tp = thread_path(topic, threads_dir)
    # Determine current counterpart based on registry and existing ball
    title, status, ball, updated = thread_meta(tp)
    target = _counterpart_of(ball, registry)

    # Default agent to Team
    default_agent, default_role = _default_agent_and_role(registry)
    final_agent = agent if agent is not None else default_agent

    # Create handoff message
    text = note or f"handoff to {target}"
    handoff_title = f"Handoff to {target}"

    # Append structured handoff entry with explicit ball
    return append_entry(
        topic,
        threads_dir=threads_dir,
        agent=final_agent,
        role=role,
        title=handoff_title,
        entry_type="Note",
        body=text,
        ball=target,  # Explicitly set target (no auto-flip needed)
        templates_dir=templates_dir,
        registry=registry,
        user_tag=user_tag,
    )


def reindex(*, threads_dir: Path, out_file: Path | None = None, open_only: bool | None = True) -> Path:
    """Write a Markdown index summarizing threads."""
    rows = list_threads(threads_dir=threads_dir, open_only=open_only)
    out_path = out_file or (threads_dir / "index.md")
    lines = ["# Watercooler Index", "", "Updated | Status | Ball | NEW | Title | Path", "---|---|---|---|---|---"]
    for title, status, ball, updated, path, is_new in rows:
        rel = path.relative_to(threads_dir)
        newcol = "NEW" if is_new else ""
        lines.append(f"{updated} | {status} | {ball} | {newcol} | {title} | {rel}")
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


def web_export(*, threads_dir: Path, out_file: Path | None = None, open_only: bool | None = True) -> Path:
    """Export a simple static HTML index summarizing threads."""
    rows = list_threads(threads_dir=threads_dir, open_only=open_only)
    out_path = out_file or (threads_dir / "index.html")
    tbody = []
    for title, status, ball, updated, path, is_new in rows:
        rel = path.relative_to(threads_dir)
        badge = "<strong style=\"color:#b00\">NEW</strong>" if is_new else ""
        tbody.append(
            f"<tr><td>{updated}</td><td>{status}</td><td>{ball}</td><td>{badge}</td><td>{title}</td><td><a href=\"{rel}\">{rel}</a></td></tr>"
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
  <thead><tr><th>Updated</th><th>Status</th><th>Ball</th><th>NEW</th><th>Title</th><th>Path</th></tr></thead>
  <tbody>
    BODY
  </tbody>
</table>
</html>
""".replace("BODY", "\n    ".join(tbody))
    write(out_path, html)
    return out_path


def unlock(topic: str, *, threads_dir: Path, force: bool = False) -> None:
    """Clear advisory lock for a topic (debugging tool).

    Args:
        topic: Thread topic
        threads_dir: Directory containing threads
        force: Remove lock even if it appears active

    This command helps recover from stuck locks during development or debugging.
    Use with caution in production environments.
    """
    import sys
    import time

    lp = lock_path_for_topic(topic, threads_dir)

    print(f"Lock path: {lp}")

    if not lp.exists():
        print("No lock file present.")
        return

    # Read lock metadata
    try:
        txt = lp.read_text(encoding="utf-8").strip()
    except Exception:
        txt = "(unreadable)"

    # Get lock age
    try:
        st = lp.stat()
        age = int(time.time() - st.st_mtime)
    except Exception:
        age = -1

    # Check if stale
    from .lock import AdvisoryLock
    al = AdvisoryLock(lp)
    stale = al._is_stale()

    print(f"Contents: {txt}")
    print(f"Age: {age}s; Stale: {stale}")

    if stale or force:
        try:
            lp.unlink()
            print("Lock removed.")
        except Exception as e:
            sys.exit(f"Failed to remove lock: {e}")
    else:
        sys.exit("Lock appears active; re-run with --force to remove anyway.")
