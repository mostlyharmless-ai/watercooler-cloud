#!/usr/bin/env python3
"""Watercooler CLI - command-line interface for thread management."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace

# Fail fast on unsupported interpreter version
if sys.version_info < (3, 10):
    print(f"Watercooler CLI requires Python 3.10+; found {sys.version.split()[0]}", file=sys.stderr)
    sys.exit(1)


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
    p_web.add_argument("--threads-dir")
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

    p_check_branches = sub.add_parser("check-branches", help="Comprehensive audit of branch pairing")
    p_check_branches.add_argument("--code-root", help="Path to code repository (default: current directory)")
    p_check_branches.add_argument("--include-merged", action="store_true", help="Include fully merged branches")

    p_check_branch = sub.add_parser("check-branch", help="Validate branch pairing for specific branch")
    p_check_branch.add_argument("branch", help="Branch name to check")
    p_check_branch.add_argument("--code-root", help="Path to code repository (default: current directory)")

    p_merge_branch = sub.add_parser("merge-branch", help="Merge threads branch to main")
    p_merge_branch.add_argument("branch", help="Branch name to merge")
    p_merge_branch.add_argument("--code-root", help="Path to code repository (default: current directory)")
    p_merge_branch.add_argument("--force", action="store_true", help="Skip safety checks")

    p_archive_branch = sub.add_parser("archive-branch", help="Close OPEN threads, merge to main, then delete branch")
    p_archive_branch.add_argument("branch", help="Branch name to archive")
    p_archive_branch.add_argument("--code-root", help="Path to code repository (default: current directory)")
    p_archive_branch.add_argument("--abandon", action="store_true", help="Set OPEN threads to ABANDONED status")
    p_archive_branch.add_argument("--force", action="store_true", help="Skip confirmation prompts")

    p_install_hooks = sub.add_parser("install-hooks", help="Install git hooks for branch pairing validation")
    p_install_hooks.add_argument("--code-root", help="Path to code repository (default: current directory)")
    p_install_hooks.add_argument("--hooks-dir", help="Git hooks directory (default: .git/hooks)")
    p_install_hooks.add_argument("--force", action="store_true", help="Overwrite existing hooks")

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

    p_sync = sub.add_parser("sync", help="Inspect or flush async git sync queue")
    p_sync.add_argument("--code-path", help="Code repository root (default: current directory)")
    p_sync.add_argument("--threads-dir", help="Threads directory override")
    p_sync.add_argument("--status", action="store_true", help="Show pending queue status without flushing")
    p_sync.add_argument("--now", action="store_true", help="Force an immediate push of pending commits")

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

    if args.cmd == "sync":
        from pathlib import Path
        from .config import resolve_threads_dir
        from watercooler_mcp.config import (
            resolve_thread_context,
            get_git_sync_manager_from_context,
        )
        from watercooler_mcp.git_sync import GitPushError

        code_root = Path(args.code_path).resolve() if args.code_path else Path.cwd()
        ctx = resolve_thread_context(code_root)
        if args.threads_dir:
            threads_override = resolve_threads_dir(args.threads_dir)
            ctx = replace(ctx, threads_dir=threads_override, explicit_dir=True)

        sync = get_git_sync_manager_from_context(ctx)
        if not sync:
            print("No git-enabled threads repository resolved for this context.", file=sys.stderr)
            sys.exit(1)

        status = sync.get_async_status()

        def _print_status(info: dict) -> None:
            if info.get("mode") != "async":
                print("Async sync disabled; repository uses synchronous git writes.")
                return
            print("Async sync status:")
            print(f"- Pending entries: {info.get('pending', 0)}")
            topics = info.get("pending_topics") or []
            if topics:
                print(f"- Pending topics: {', '.join(topics)}")
            last_pull = info.get("last_pull")
            if last_pull:
                age = info.get("last_pull_age_seconds")
                age_str = f"{age:.1f}s ago" if age is not None else "recently"
                stale = " (stale)" if info.get("stale") else ""
                print(f"- Last pull: {last_pull} ({age_str}){stale}")
            else:
                print("- Last pull: never")
            next_eta = info.get("next_pull_eta_seconds")
            if next_eta is not None:
                print(f"- Next background pull in: {next_eta:.1f}s")
            if info.get("is_syncing"):
                print("- Sync in progress")
            if info.get("priority"):
                print("- Priority flush requested")
            if info.get("retry_at"):
                retry_line = f"- Next retry attempt at: {info['retry_at']}"
                retry_in = info.get("retry_in_seconds")
                if retry_in is not None:
                    retry_line += f" (in {retry_in:.1f}s)"
                print(retry_line)
            if info.get("last_error"):
                print(f"- Last error: {info['last_error']}")

        if status.get("mode") != "async":
            print("Async sync disabled; repository uses synchronous git writes.")
            sys.exit(0)

        if args.status:
            _print_status(status)
            if not args.now:
                sys.exit(0)

        try:
            sync.flush_async()
            print("✅ Pending entries synced.")
        except GitPushError as exc:
            print(f"❌ Sync failed: {exc}", file=sys.stderr)
            sys.exit(1)

        if args.status:
            _print_status(sync.get_async_status())
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

    if args.cmd == "check-branches":
        from pathlib import Path
        from .commands import check_branches

        code_root = Path(args.code_root).resolve() if args.code_root else None
        result = check_branches(code_root=code_root, include_merged=args.include_merged)
        print(result)
        sys.exit(0)

    if args.cmd == "check-branch":
        from pathlib import Path
        from .commands import check_branch

        code_root = Path(args.code_root).resolve() if args.code_root else None
        result = check_branch(args.branch, code_root=code_root)
        print(result)
        sys.exit(0)

    if args.cmd == "merge-branch":
        from pathlib import Path
        from .commands import merge_branch

        code_root = Path(args.code_root).resolve() if args.code_root else None
        result = merge_branch(args.branch, code_root=code_root, force=args.force)
        print(result)
        sys.exit(0)

    if args.cmd == "archive-branch":
        from pathlib import Path
        from .commands import archive_branch

        code_root = Path(args.code_root).resolve() if args.code_root else None
        result = archive_branch(args.branch, code_root=code_root, abandon=args.abandon, force=args.force)
        print(result)
        sys.exit(0)

    if args.cmd == "install-hooks":
        from pathlib import Path
        from .commands import install_hooks

        code_root = Path(args.code_root).resolve() if args.code_root else None
        hooks_dir = Path(args.hooks_dir).resolve() if args.hooks_dir else None
        result = install_hooks(code_root=code_root, hooks_dir=hooks_dir, force=args.force)
        print(result)
        sys.exit(0)

    # default: other commands not yet implemented in L1
    print(f"watercooler {args.cmd}: not yet implemented (L1 stub)")
    sys.exit(0)


if __name__ == "__main__":
    main()
