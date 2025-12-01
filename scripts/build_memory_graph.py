#!/usr/bin/env python3
"""Build memory graph from watercooler threads.

Usage:
    ./scripts/build_memory_graph.py /path/to/threads-repo
    ./scripts/build_memory_graph.py /path/to/threads-repo --export-leanrag ./output
    ./scripts/build_memory_graph.py /path/to/threads-repo --no-summaries --no-embeddings

Environment variables:
    EMBEDDING_API_BASE  - bge-m3 API endpoint (default: http://localhost:8000/v1)
    DEEPSEEK_API_KEY    - DeepSeek API key for summaries
    LLM_API_BASE        - LLM API endpoint (default: https://api.deepseek.com/v1)
"""

import argparse
import sys
from pathlib import Path

# Add src to path for local dev
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from watercooler.memory_graph import MemoryGraph, GraphConfig
from watercooler.memory_graph.leanrag_export import export_to_leanrag


def main():
    parser = argparse.ArgumentParser(
        description="Build memory graph from watercooler threads"
    )
    parser.add_argument(
        "threads_dir",
        type=Path,
        help="Path to threads directory or repo root (will look for .watercooler/)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output path for graph JSON",
    )
    parser.add_argument(
        "--export-leanrag",
        type=Path,
        help="Export to LeanRAG format at this directory",
    )
    parser.add_argument(
        "--no-summaries",
        action="store_true",
        help="Skip summary generation (no LLM calls)",
    )
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Skip embedding generation (no embedding API calls)",
    )
    parser.add_argument(
        "--branch",
        help="Git branch context",
    )
    args = parser.parse_args()

    # Resolve threads directory
    threads_dir = args.threads_dir
    if not threads_dir.exists():
        print(f"❌ Path not found: {threads_dir}", file=sys.stderr)
        sys.exit(1)

    # Check for .watercooler subdirectory
    if (threads_dir / ".watercooler").is_dir():
        threads_dir = threads_dir / ".watercooler"
    elif not any(threads_dir.glob("*.md")):
        print(f"❌ No .md files found in {threads_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 Threads directory: {threads_dir}")

    # Configure
    config = GraphConfig(
        generate_summaries=not args.no_summaries,
        generate_embeddings=not args.no_embeddings,
    )

    # Progress callback
    def progress(current, total, message):
        if total > 0:
            print(f"   {message} ({current}/{total})", flush=True)
        else:
            print(f"   {message}", flush=True)

    # Build graph
    print("🔨 Building memory graph...")
    graph = MemoryGraph(config)

    try:
        graph.build(threads_dir, branch_context=args.branch, progress_callback=progress)
    except ImportError as e:
        print(f"⚠️  Missing optional dependency: {e}", file=sys.stderr)
        print("   Continuing with partial build...", file=sys.stderr)
    except Exception as e:
        print(f"❌ Build error: {e}", file=sys.stderr)
        sys.exit(1)

    # Stats
    stats = graph.stats()
    print(f"✅ Built graph:")
    print(f"   Threads:  {stats['threads']}")
    print(f"   Entries:  {stats['entries']}")
    print(f"   Chunks:   {stats['chunks']}")
    print(f"   Edges:    {stats['edges']}")

    if stats['entries_with_summaries']:
        print(f"   Summaries: {stats['entries_with_summaries']}")
    if stats['chunks_with_embeddings']:
        print(f"   Embeddings: {stats['chunks_with_embeddings']}")

    # Save graph JSON
    if args.output:
        graph.save(args.output)
        print(f"💾 Saved graph: {args.output}")

    # Export to LeanRAG
    if args.export_leanrag:
        manifest = export_to_leanrag(
            graph,
            args.export_leanrag,
            include_embeddings=not args.no_embeddings,
        )
        print(f"📤 Exported LeanRAG format: {args.export_leanrag}")
        print(f"   Documents: {manifest['statistics']['documents']}")
        print(f"   Chunks: {manifest['statistics']['chunks']}")


if __name__ == "__main__":
    main()
