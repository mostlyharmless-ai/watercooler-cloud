#!/usr/bin/env python3
"""Watercooler CLI - command-line interface for thread management."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="watercooler",
        description="File-based collaboration for agentic coding",
    )

    sub = ap.add_subparsers(dest="cmd")

    # Command stubs
    p_init = sub.add_parser("init-thread", help="Initialize a new thread")
    p_init.add_argument("topic", help="Thread topic identifier")
    p_init.add_argument("--title", help="Optional title override")
    p_init.add_argument("--status", default="open", help="Initial status (default: open)")
    p_init.add_argument("--ball", default="codex", help="Initial ball owner (default: codex)")
    p_init.add_argument("--threads-dir", help="Threads directory (default: ./watercooler or $WATERCOOLER_DIR)")
    p_init.add_argument("--body", help="Optional initial body text or @file path")
    p_init.add_argument("--owner", help="Thread owner (default: Team)")
    p_init.add_argument("--participants", help="Comma-separated list of participants")
    p_init.add_argument("--templates-dir", help="Templates directory override")

    p_web = sub.add_parser("web-export", help="Generate HTML index")
    p_web.add_argument("--threads-dir", default="watercooler")
    p_web.add_argument("--out", help="Optional output file path")
    p_web.add_argument("--open-only", action="store_true")
    p_web.add_argument("--closed", action="store_true")

    p_say = sub.add_parser("say", help="Quick team note with auto-ball-flip")
    p_say.add_argument("topic")
    p_say.add_argument("--threads-dir")
    p_say.add_argument("--agent", help="Agent name (defaults to Team)")
    p_say.add_argument("--role", help="Agent role (planner, critic, implementer, tester, pm, scribe)")
    p_say.add_argument("--title", required=True, help="Entry title")
    p_say.add_argument("--type", dest="entry_type", default="Note", help="Entry type (Note, Plan, Decision, PR, Closure)")
    p_say.add_argument("--body", required=True, help="Entry body text or @file path")
    p_say.add_argument("--status", help="Optional status update")
    p_say.add_argument("--ball", help="Optional ball update (auto-flips if not provided)")
    p_say.add_argument("--templates-dir", help="Templates directory override")
    p_say.add_argument("--agents-file", help="Agent registry JSON file")

    p_ack = sub.add_parser("ack", help="Acknowledge without ball flip")
    p_ack.add_argument("topic")
    p_ack.add_argument("--threads-dir")
    p_ack.add_argument("--agent", help="Agent name (defaults to Team)")
    p_ack.add_argument("--role", help="Agent role (planner, critic, implementer, tester, pm, scribe)")
    p_ack.add_argument("--title", help="Entry title (default: Ack)")
    p_ack.add_argument("--type", dest="entry_type", default="Note", help="Entry type (Note, Plan, Decision, PR, Closure)")
    p_ack.add_argument("--body", help="Entry body text or @file path (default: ack)")
    p_ack.add_argument("--status", help="Optional status update")
    p_ack.add_argument("--ball", help="Optional ball update (does NOT auto-flip)")
    p_ack.add_argument("--templates-dir", help="Templates directory override")
    p_ack.add_argument("--agents-file", help="Agent registry JSON file")

    p_handoff = sub.add_parser("handoff", help="Flip ball to counterpart and append handoff entry")
    p_handoff.add_argument("topic")
    p_handoff.add_argument("--threads-dir")
    p_handoff.add_argument("--agent", help="Agent performing handoff (defaults to Team)")
    p_handoff.add_argument("--role", default="pm", help="Agent role (default: pm)")
    p_handoff.add_argument("--note", help="Optional custom handoff message")
    p_handoff.add_argument("--templates-dir", help="Templates directory override")
    p_handoff.add_argument("--agents-file", help="Agent registry JSON file")

    p_list = sub.add_parser("list", help="List threads")
    p_list.add_argument("--threads-dir")
    p_list.add_argument("--open-only", action="store_true", help="Show only open threads")
    p_list.add_argument("--closed", action="store_true", help="Show only closed threads")

    p_reindex = sub.add_parser("reindex", help="Rebuild index")
    p_reindex.add_argument("--threads-dir")
    p_reindex.add_argument("--out", help="Optional output file path")
    p_reindex.add_argument("--open-only", action="store_true")
    p_reindex.add_argument("--closed", action="store_true")

    p_search = sub.add_parser("search", help="Search threads")
    p_search.add_argument("query")
    p_search.add_argument("--threads-dir")

    p_unlock = sub.add_parser("unlock", help="Clear advisory lock (debugging)")
    p_unlock.add_argument("topic")
    p_unlock.add_argument("--threads-dir")
    p_unlock.add_argument("--force", action="store_true", help="Remove lock even if active")

    p_append = sub.add_parser("append-entry", help="Append a structured entry")
    p_append.add_argument("topic")
    p_append.add_argument("--threads-dir")
    p_append.add_argument("--agent", required=True, help="Agent name")
    p_append.add_argument("--role", required=True, help="Agent role (planner, critic, implementer, tester, pm, scribe)")
    p_append.add_argument("--title", required=True, help="Entry title")
    p_append.add_argument("--type", dest="entry_type", default="Note", help="Entry type (Note, Plan, Decision, PR, Closure)")
    p_append.add_argument("--body", required=True, help="Entry body text or @file path")
    p_append.add_argument("--status", help="Optional status update")
    p_append.add_argument("--ball", help="Optional ball update (auto-flips if not provided)")
    p_append.add_argument("--templates-dir", help="Templates directory override")
    p_append.add_argument("--agents-file", help="Agent registry JSON file")

    p_set_status = sub.add_parser("set-status", help="Update thread status")
    p_set_status.add_argument("topic")
    p_set_status.add_argument("status")
    p_set_status.add_argument("--threads-dir")

    p_set_ball = sub.add_parser("set-ball", help="Update ball ownership")
    p_set_ball.add_argument("topic")
    p_set_ball.add_argument("ball")
    p_set_ball.add_argument("--threads-dir")

    args = ap.parse_args(argv)

    if not args.cmd:
        ap.print_help()
        sys.exit(0)

    if args.cmd == "init-thread":
        from pathlib import Path
        from .fs import read_body
        from .config import resolve_threads_dir, resolve_templates_dir
        from .commands import init_thread

        body = read_body(args.body)
        out = init_thread(
            args.topic,
            threads_dir=resolve_threads_dir(args.threads_dir),
            title=args.title,
            status=args.status,
            ball=args.ball,
            body=body,
            owner=args.owner,
            participants=args.participants,
            templates_dir=resolve_templates_dir(args.templates_dir) if args.templates_dir else None,
        )
        print(str(out))
        sys.exit(0)

    if args.cmd == "append-entry":
        from pathlib import Path
        from .fs import read_body
        from .config import resolve_threads_dir, resolve_templates_dir
        from .commands import append_entry
        from .agents import _load_agents_registry

        body = read_body(args.body)
        registry = _load_agents_registry(args.agents_file) if hasattr(args, 'agents_file') and args.agents_file else None
        out = append_entry(
            args.topic,
            threads_dir=resolve_threads_dir(args.threads_dir),
            agent=args.agent,
            role=args.role,
            title=args.title,
            entry_type=args.entry_type,
            body=body,
            status=args.status,
            ball=args.ball,
            templates_dir=resolve_templates_dir(args.templates_dir) if args.templates_dir else None,
            registry=registry,
        )
        print(str(out))
        sys.exit(0)

    if args.cmd == "set-status":
        from pathlib import Path
        from .commands import set_status
        from .config import resolve_threads_dir

        out = set_status(args.topic, threads_dir=resolve_threads_dir(args.threads_dir), status=args.status)
        print(str(out))
        sys.exit(0)

    if args.cmd == "set-ball":
        from pathlib import Path
        from .commands import set_ball
        from .config import resolve_threads_dir

        out = set_ball(args.topic, threads_dir=resolve_threads_dir(args.threads_dir), ball=args.ball)
        print(str(out))
        sys.exit(0)

    if args.cmd == "list":
        from pathlib import Path
        from .commands import list_threads
        from .config import resolve_threads_dir

        oo: bool | None = None
        if args.open_only and args.closed:
            oo = None
        elif args.open_only:
            oo = True
        elif args.closed:
            oo = False
        rows = list_threads(threads_dir=resolve_threads_dir(args.threads_dir), open_only=oo)
        for title, status, ball, updated, path, is_new in rows:
            newcol = "NEW" if is_new else ""
            print(f"{updated}\t{status}\t{ball}\t{newcol}\t{title}\t{path}")
        sys.exit(0)

    if args.cmd == "reindex":
        from pathlib import Path
        from .commands import reindex
        from .config import resolve_threads_dir

        oo: bool | None = True
        if args.open_only and args.closed:
            oo = None
        elif args.closed:
            oo = False
        elif args.open_only:
            oo = True
        out = reindex(threads_dir=resolve_threads_dir(args.threads_dir), out_file=Path(args.out) if args.out else None, open_only=oo)
        print(str(out))
        sys.exit(0)

    if args.cmd == "search":
        from pathlib import Path
        from .commands import search
        from .config import resolve_threads_dir

        hits = search(threads_dir=resolve_threads_dir(args.threads_dir), query=args.query)
        for p, ln, line in hits:
            print(f"{p}:{ln}: {line}")
        sys.exit(0)

    if args.cmd == "unlock":
        from pathlib import Path
        from .commands import unlock
        from .config import resolve_threads_dir

        unlock(
            args.topic,
            threads_dir=resolve_threads_dir(args.threads_dir),
            force=args.force
        )
        sys.exit(0)

    if args.cmd == "web-export":
        from pathlib import Path
        from .commands import web_export
        from .config import resolve_threads_dir

        oo: bool | None = True
        if args.open_only and args.closed:
            oo = None
        elif args.closed:
            oo = False
        elif args.open_only:
            oo = True
        out = web_export(threads_dir=resolve_threads_dir(args.threads_dir), out_file=Path(args.out) if args.out else None, open_only=oo)
        print(str(out))
        sys.exit(0)

    if args.cmd == "say":
        from pathlib import Path
        from .fs import read_body
        from .config import resolve_threads_dir, resolve_templates_dir
        from .commands import say
        from .agents import _load_agents_registry

        body = read_body(args.body)
        registry = _load_agents_registry(args.agents_file) if hasattr(args, 'agents_file') and args.agents_file else None
        out = say(
            args.topic,
            threads_dir=resolve_threads_dir(args.threads_dir),
            agent=args.agent,
            role=args.role,
            title=args.title,
            entry_type=args.entry_type,
            body=body,
            status=args.status,
            ball=args.ball,
            templates_dir=resolve_templates_dir(args.templates_dir) if args.templates_dir else None,
            registry=registry,
        )
        print(str(out))
        sys.exit(0)

    if args.cmd == "ack":
        from pathlib import Path
        from .fs import read_body
        from .commands import ack
        from .config import resolve_threads_dir, resolve_templates_dir
        from .agents import _load_agents_registry

        body = read_body(args.body) if args.body else None
        registry = _load_agents_registry(args.agents_file) if hasattr(args, 'agents_file') and args.agents_file else None
        out = ack(
            args.topic,
            threads_dir=resolve_threads_dir(args.threads_dir),
            agent=args.agent,
            role=args.role,
            title=args.title,
            entry_type=args.entry_type,
            body=body,
            status=args.status,
            ball=args.ball,
            templates_dir=resolve_templates_dir(args.templates_dir) if args.templates_dir else None,
            registry=registry,
        )
        print(str(out))
        sys.exit(0)

    if args.cmd == "handoff":
        from pathlib import Path
        from .commands import handoff
        from .config import resolve_threads_dir, resolve_templates_dir
        from .agents import _load_agents_registry

        registry = _load_agents_registry(args.agents_file) if hasattr(args, 'agents_file') and args.agents_file else None
        out = handoff(
            args.topic,
            threads_dir=resolve_threads_dir(args.threads_dir),
            agent=args.agent,
            role=args.role,
            note=args.note,
            registry=registry,
            templates_dir=resolve_templates_dir(args.templates_dir) if args.templates_dir else None,
        )
        print(str(out))
        sys.exit(0)

    # default: other commands not yet implemented in L1
    print(f"watercooler {args.cmd}: not yet implemented (L1 stub)")
    sys.exit(0)


if __name__ == "__main__":
    main()
