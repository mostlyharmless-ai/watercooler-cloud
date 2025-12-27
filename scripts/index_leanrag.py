#!/usr/bin/env python3
"""Index watercooler threads into LeanRAG backend.

Usage:
    python3 scripts/index_leanrag.py --thread-list /path/to/threads-to-index.txt
    python3 scripts/index_leanrag.py --threads graphiti-mcp-integration memory-backend
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from watercooler_memory.backends.leanrag import LeanRAGBackend, LeanRAGConfig
from watercooler_memory.backends import CorpusPayload, ChunkPayload
from watercooler_memory.graph import MemoryGraph
from watercooler_memory.chunker import ChunkerConfig
from watercooler_memory.graph import GraphConfig


def load_thread_list(list_file: Path) -> list[str]:
    """Load thread filenames from list file."""
    threads = []
    with open(list_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                # Ensure .md extension
                if not line.endswith(".md"):
                    line = f"{line}.md"
                threads.append(line)
    return threads


def build_corpus(threads_dir: Path, thread_files: list[str]) -> CorpusPayload:
    """Build corpus from watercooler threads."""
    print(f"Building corpus from {len(thread_files)} threads...")

    # Build memory graph with watercooler preset for headers
    config = GraphConfig(chunker=ChunkerConfig.watercooler_preset())
    graph = MemoryGraph(config=config)

    for thread_file in thread_files:
        thread_path = threads_dir / thread_file
        if thread_path.exists():
            print(f"  Loading {thread_file}...")
            graph.add_thread(thread_path)
        else:
            print(f"  Warning: {thread_file} not found, skipping")

    # Chunk all entries using the custom watercooler chunker with headers
    print("Chunking entries...")
    chunk_nodes = graph.chunk_all_entries()
    print(f"Created {len(chunk_nodes)} chunks from {len(graph.entries)} entries")

    # Convert to canonical payload format
    threads_data = [
        {
            "id": thread.thread_id,
            "topic": thread.thread_id,
            "status": thread.status,
            "ball": thread.ball,
            "entry_count": len([e for e in graph.entries.values() if e.thread_id == thread.thread_id]),
            "title": thread.title,
        }
        for thread in graph.threads.values()
    ]

    entries_data = [
        {
            "id": entry.entry_id,
            "thread_id": entry.thread_id,
            "agent": entry.agent,
            "role": entry.role,
            "type": entry.entry_type,
            "title": entry.title,
            "body": entry.body,
            "timestamp": entry.timestamp,
            # Include chunks for this entry
            "chunks": [
                {"text": chunk.text, "chunk_id": chunk.chunk_id, "token_count": len(chunk.text.split())}
                for chunk in chunk_nodes
                if chunk.entry_id == entry.entry_id
            ],
        }
        for entry in graph.entries.values()
    ]

    return CorpusPayload(
        manifest_version="1.0.0",
        threads=threads_data,
        entries=entries_data,
        edges=[],
        metadata={"source": "index_leanrag.py"},
    )


def build_chunks(corpus: CorpusPayload) -> ChunkPayload:
    """Extract chunks from corpus entries."""
    all_chunks = []
    for entry in corpus.entries:
        if "chunks" in entry:
            for chunk in entry["chunks"]:
                all_chunks.append({
                    "id": chunk.get("chunk_id", chunk.get("id")),
                    "entry_id": entry["id"],
                    "text": chunk["text"],
                    "token_count": chunk.get("token_count", len(chunk["text"].split())),
                    "hash_code": chunk.get("hash_code", ""),
                })

    return ChunkPayload(
        manifest_version="1.0.0",
        chunks=all_chunks,
    )


def main():
    parser = argparse.ArgumentParser(description="Index watercooler threads into LeanRAG")
    parser.add_argument("--threads-dir", default="/Volumes/aria/projects/watercooler-cloud-threads",
                        help="Path to threads directory")
    parser.add_argument("--thread-list", help="Path to file with thread list (one per line)")
    parser.add_argument("--threads", nargs="+", help="List of thread topics (without .md)")
    parser.add_argument("--work-dir", help="Work directory for LeanRAG (default: ~/.watercooler/leanrag)")
    parser.add_argument("--leanrag-dir", help="Path to LeanRAG repository (default: $LEANRAG_DIR or ./external/LeanRAG)")

    args = parser.parse_args()

    # Check for DeepSeek API key (or other LLM)
    if "DEEPSEEK_API_KEY" not in os.environ:
        print("Error: DEEPSEEK_API_KEY environment variable not set", file=sys.stderr)
        print("Export your DeepSeek API key: export DEEPSEEK_API_KEY=sk-...", file=sys.stderr)
        return 1

    # Determine thread list
    if args.thread_list:
        thread_list_path = Path(args.thread_list)
        if not thread_list_path.exists():
            print(f"Error: Thread list file not found: {thread_list_path}", file=sys.stderr)
            return 1
        thread_files = load_thread_list(thread_list_path)
    elif args.threads:
        thread_files = [f"{t}.md" if not t.endswith(".md") else t for t in args.threads]
    else:
        print("Error: Specify either --thread-list or --threads", file=sys.stderr)
        parser.print_help()
        return 1

    threads_dir = Path(args.threads_dir)
    if not threads_dir.exists():
        print(f"Error: Threads directory not found: {threads_dir}", file=sys.stderr)
        return 1

    # Determine LeanRAG directory
    if args.leanrag_dir:
        leanrag_dir = Path(args.leanrag_dir)
    elif "LEANRAG_DIR" in os.environ:
        leanrag_dir = Path(os.environ["LEANRAG_DIR"])
    else:
        leanrag_dir = Path(__file__).parent.parent / "external" / "LeanRAG"

    if not leanrag_dir.exists():
        print(f"Error: LeanRAG directory not found: {leanrag_dir}", file=sys.stderr)
        print("Specify with --leanrag-dir or set LEANRAG_DIR environment variable", file=sys.stderr)
        return 1

    # Set up LeanRAG backend
    work_dir = Path(args.work_dir) if args.work_dir else Path.home() / ".watercooler" / "leanrag"
    work_dir.mkdir(parents=True, exist_ok=True)

    config = LeanRAGConfig(work_dir=work_dir, leanrag_path=leanrag_dir)
    backend = LeanRAGBackend(config)

    # Check health
    print("Checking LeanRAG backend health...")
    health = backend.healthcheck()
    if not health.ok:
        print(f"Error: Backend health check failed: {health.details}", file=sys.stderr)
        print("\nMake sure FalkorDB is running: docker run -d -p 6379:6379 falkordb/falkordb:latest", file=sys.stderr)
        return 1
    print(f"✓ Backend healthy: {health.details}")

    # Build corpus from threads
    corpus = build_corpus(threads_dir, thread_files)
    print(f"\n✓ Built corpus: {len(corpus.threads)} threads, {len(corpus.entries)} entries")

    # Step 1: Prepare (entity extraction)
    print("\nStep 1: Preparing (entity/relation extraction)...")
    print("  This step uses LLM to extract entities and relationships from chunks.")
    print("  With 3 threads, expect ~5-15 minutes depending on chunk count.")
    prepare_result = backend.prepare(corpus)
    print(f"✓ Prepared {prepare_result.prepared_count} chunks")

    # Step 2: Build chunks
    print("\nStep 2: Building chunks...")
    chunks = build_chunks(corpus)
    print(f"✓ Built {len(chunks.chunks)} chunks")

    # Step 3: Index (build hierarchical graph)
    print("\nStep 3: Building hierarchical knowledge graph...")
    print("  This step performs clustering and builds the graph in FalkorDB.")
    index_result = backend.index(chunks)
    print(f"✓ Indexed {index_result.indexed_count} chunks into LeanRAG graph")

    print(f"\n✅ Indexing complete! Work directory: {work_dir}")
    print("\nYou can now query via Phase 2 backend:")
    print('  backend.search_nodes(query="your question", max_results=10)')
    print('  backend.search_facts(query="your question", max_results=10)')

    return 0


if __name__ == "__main__":
    sys.exit(main())
