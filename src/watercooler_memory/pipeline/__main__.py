#!/usr/bin/env python3
"""CLI for watercooler pipeline management.

Usage:
    python -m watercooler_memory.pipeline run --threads /path/to/threads
    python -m watercooler_memory.pipeline run --threads /path/to/threads --test
    python -m watercooler_memory.pipeline run --threads /path/to/threads --stage export
    python -m watercooler_memory.pipeline status
    python -m watercooler_memory.pipeline status --run-id abc123
    python -m watercooler_memory.pipeline list
"""

import argparse
import sys
from pathlib import Path

from .config import load_config_from_env
from .state import Stage, list_runs, get_state_path, PipelineState
from .runner import PipelineRunner


def cmd_run(args: argparse.Namespace) -> int:
    """Run pipeline."""
    # Validate paths
    threads_dir = Path(args.threads)
    if not threads_dir.exists():
        print(f"Error: Threads directory not found: {threads_dir}", file=sys.stderr)
        return 1

    work_dir = Path(args.work_dir) if args.work_dir else None
    leanrag_dir = Path(args.leanrag_dir) if args.leanrag_dir else None

    # Create config
    config = load_config_from_env(
        threads_dir=threads_dir,
        work_dir=work_dir,
        leanrag_dir=leanrag_dir,
        test_mode=args.test,
    )

    # Override test limit if specified
    if args.test_limit:
        config.test_limit = args.test_limit

    # Create runner
    runner = PipelineRunner(
        config,
        run_id=args.run_id,
        verbose=args.verbose,
    )

    print(f"Pipeline run: {runner.run_id}")
    print(f"Work directory: {config.work_dir}")
    if args.test:
        print(f"Test mode: {config.test_limit} documents")
    print()

    # Determine what to run
    if args.stage:
        try:
            stage = Stage(args.stage)
        except ValueError:
            print(f"Error: Unknown stage '{args.stage}'", file=sys.stderr)
            print(f"Valid stages: {', '.join(s.value for s in Stage.ordered())}", file=sys.stderr)
            return 1

        success = runner.run_stage(stage, force=args.force)
    else:
        from_stage = Stage(args.from_stage) if args.from_stage else None
        to_stage = Stage(args.to_stage) if args.to_stage else None
        success = runner.run_all(from_stage=from_stage, to_stage=to_stage)

    return 0 if success else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show pipeline status."""
    work_dir = Path(args.work_dir) if args.work_dir else Path("./pipeline_work")

    if not work_dir.exists():
        print(f"Work directory not found: {work_dir}", file=sys.stderr)
        return 1

    # Get run ID
    run_id = args.run_id
    if not run_id:
        # Use most recent run
        runs = list_runs(work_dir)
        if not runs:
            print("No pipeline runs found.", file=sys.stderr)
            return 1
        run_id = runs[0]

    # Load state
    state_path = get_state_path(work_dir, run_id)
    if not state_path.exists():
        print(f"Run not found: {run_id}", file=sys.stderr)
        return 1

    state = PipelineState.load(state_path)

    # Create minimal config for runner
    config = load_config_from_env(
        threads_dir=Path(state.threads_dir),
        work_dir=work_dir,
    )

    runner = PipelineRunner(config, run_id=run_id)
    runner.print_status()

    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List pipeline runs."""
    work_dir = Path(args.work_dir) if args.work_dir else Path("./pipeline_work")

    if not work_dir.exists():
        print(f"Work directory not found: {work_dir}", file=sys.stderr)
        return 1

    runs = list_runs(work_dir)
    if not runs:
        print("No pipeline runs found.")
        return 0

    print(f"Pipeline runs in {work_dir}:\n")

    for run_id in runs:
        state_path = get_state_path(work_dir, run_id)
        state = PipelineState.load(state_path)

        # Get status summary
        complete = state.is_complete()
        current = state.current_stage()

        if complete:
            status = "✅ complete"
        elif current:
            status = f"🔄 {current.value}"
        else:
            status = "⏳ pending"

        test_marker = " [test]" if state.test_mode else ""

        print(f"  {run_id}{test_marker}: {status}")
        print(f"    Created: {state.created_at}")
        print(f"    Threads: {state.threads_dir}")
        print()

    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Clean pipeline outputs."""
    work_dir = Path(args.work_dir) if args.work_dir else Path("./pipeline_work")

    if not work_dir.exists():
        print(f"Work directory not found: {work_dir}")
        return 0

    if args.run_id:
        # Clean specific run
        state_path = get_state_path(work_dir, args.run_id)
        if state_path.exists():
            state_path.unlink()
            print(f"Removed run: {args.run_id}")
        else:
            print(f"Run not found: {args.run_id}")
    elif args.all:
        # Clean all runs
        import shutil

        confirm = input(f"Delete all pipeline data in {work_dir}? [y/N] ")
        if confirm.lower() == "y":
            shutil.rmtree(work_dir)
            print(f"Removed: {work_dir}")
        else:
            print("Cancelled.")
    else:
        print("Specify --run-id or --all")
        return 1

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Watercooler → LeanRAG pipeline management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline in test mode (5 documents)
  python -m watercooler_memory.pipeline run --threads /path/to/threads --test

  # Run only export stage
  python -m watercooler_memory.pipeline run --threads /path/to/threads --stage export

  # Run from extract stage onwards
  python -m watercooler_memory.pipeline run --threads /path/to/threads --from extract

  # Check status of most recent run
  python -m watercooler_memory.pipeline status

  # List all runs
  python -m watercooler_memory.pipeline list
        """,
    )

    # Global options
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--work-dir", type=str, help="Work directory (default: ./pipeline_work)")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run pipeline")
    run_parser.add_argument("--threads", "-t", required=True, help="Path to threads directory")
    run_parser.add_argument("--work-dir", "-w", type=str, help="Work directory (default: ./pipeline_work)")
    run_parser.add_argument("--leanrag-dir", help="Path to LeanRAG repository (default: $LEANRAG_DIR)")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    run_parser.add_argument("--run-id", help="Run ID (auto-generated if not provided)")
    run_parser.add_argument("--test", action="store_true", help="Test mode with limited data")
    run_parser.add_argument("--test-limit", type=int, help="Number of documents in test mode (default: 5)")
    run_parser.add_argument("--stage", help="Run only this stage")
    run_parser.add_argument("--from", dest="from_stage", help="Start from this stage")
    run_parser.add_argument("--to", dest="to_stage", help="Stop after this stage")
    run_parser.add_argument("--force", action="store_true", help="Force re-run of completed stages")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show pipeline status")
    status_parser.add_argument("--work-dir", "-w", type=str, help="Work directory (default: ./pipeline_work)")
    status_parser.add_argument("--run-id", help="Run ID (default: most recent)")

    # List command
    list_parser = subparsers.add_parser("list", help="List pipeline runs")
    list_parser.add_argument("--work-dir", "-w", type=str, help="Work directory (default: ./pipeline_work)")

    # Clean command
    clean_parser = subparsers.add_parser("clean", help="Clean pipeline outputs")
    clean_parser.add_argument("--work-dir", "-w", type=str, help="Work directory (default: ./pipeline_work)")
    clean_parser.add_argument("--run-id", help="Clean specific run")
    clean_parser.add_argument("--all", action="store_true", help="Clean all runs")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "clean":
        return cmd_clean(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
