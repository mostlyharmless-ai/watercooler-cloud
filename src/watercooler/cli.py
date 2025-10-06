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

    p_web = sub.add_parser("web-export", help="Generate HTML index")
    p_web.add_argument("--threads-dir", default="watercooler")
    p_web.add_argument("--out", help="Optional output file path")

    p_say = sub.add_parser("say", help="Quick team note")
    p_say.add_argument("topic")
    p_say.add_argument("--threads-dir")
    p_say.add_argument("--author")
    p_say.add_argument("--body", required=True)

    p_ack = sub.add_parser("ack", help="Acknowledge without ball flip")
    p_ack.add_argument("topic")
    p_ack.add_argument("--threads-dir")
    p_ack.add_argument("--author")
    p_ack.add_argument("--note", help="Optional note text")

    p_list = sub.add_parser("list", help="List threads")
    p_list.add_argument("--threads-dir")

    p_reindex = sub.add_parser("reindex", help="Rebuild index")
    p_reindex.add_argument("--threads-dir")
    p_reindex.add_argument("--out", help="Optional output file path")

    p_search = sub.add_parser("search", help="Search threads")
    p_search.add_argument("query")
    p_search.add_argument("--threads-dir")

    p_append = sub.add_parser("append-entry", help="Append an entry")
    p_append.add_argument("topic")
    p_append.add_argument("--threads-dir")
    p_append.add_argument("--author")
    p_append.add_argument("--body", required=True)
    p_append.add_argument("--bump-status")
    p_append.add_argument("--bump-ball")

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
        from .config import resolve_threads_dir
        from .commands import init_thread

        body = read_body(args.body)
        out = init_thread(
            args.topic,
            threads_dir=resolve_threads_dir(args.threads_dir),
            title=args.title,
            status=args.status,
            ball=args.ball,
            body=body,
        )
        print(str(out))
        sys.exit(0)

    if args.cmd == "append-entry":
        from pathlib import Path
        from .fs import read_body
        from .config import resolve_threads_dir
        from .commands import append_entry

        body = read_body(args.body)
        out = append_entry(
            args.topic,
            threads_dir=resolve_threads_dir(args.threads_dir),
            author=args.author,
            body=body,
            bump_status=args.bump_status,
            bump_ball=args.bump_ball,
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

        rows = list_threads(threads_dir=resolve_threads_dir(args.threads_dir))
        for title, status, ball, updated, path in rows:
            print(f"{updated}\t{status}\t{ball}\t{title}\t{path}")
        sys.exit(0)

    if args.cmd == "reindex":
        from pathlib import Path
        from .commands import reindex
        from .config import resolve_threads_dir

        out = reindex(threads_dir=resolve_threads_dir(args.threads_dir), out_file=Path(args.out) if args.out else None)
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

    if args.cmd == "web-export":
        from pathlib import Path
        from .commands import web_export

        out = web_export(threads_dir=Path(args.threads_dir), out_file=Path(args.out) if args.out else None)
        print(str(out))
        sys.exit(0)

    if args.cmd == "say":
        from pathlib import Path
        from .fs import read_body
        from .config import resolve_threads_dir
        from .commands import say

        body = read_body(args.body)
        out = say(args.topic, threads_dir=resolve_threads_dir(args.threads_dir), author=args.author, body=body)
        print(str(out))
        sys.exit(0)

    if args.cmd == "ack":
        from pathlib import Path
        from .commands import ack
        from .config import resolve_threads_dir

        out = ack(args.topic, threads_dir=resolve_threads_dir(args.threads_dir), author=args.author, note=args.note)
        print(str(out))
        sys.exit(0)

    # default: other commands not yet implemented in L1
    print(f"watercooler {args.cmd}: not yet implemented (L1 stub)")
    sys.exit(0)


if __name__ == "__main__":
    main()
