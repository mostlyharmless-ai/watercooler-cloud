"""Memory graph module for watercooler threads.

This module provides tools for building a memory graph from watercooler threads,
enabling semantic search, entity extraction, and integration with LeanRAG.

The graph uses a hierarchical structure:
  Thread → Entry → Chunk

With hyperedges for membership and temporal edges for sequencing.

Usage:
    from watercooler.memory_graph import MemoryGraph, GraphConfig

    graph = MemoryGraph()
    graph.build(threads_dir)
    graph.save(output_path)

CLI:
    watercooler memory build --threads-dir .watercooler
    watercooler memory export --format leanrag -o ./export
    watercooler memory stats
"""

from watercooler.memory_graph.schema import (
    ThreadNode,
    EntryNode,
    ChunkNode,
    EntityNode,
    Edge,
    Hyperedge,
    EdgeType,
    HyperedgeType,
)
from watercooler.memory_graph.graph import MemoryGraph, GraphConfig
from watercooler.memory_graph.parser import parse_thread_to_nodes, parse_threads_directory
from watercooler.memory_graph.chunker import chunk_text, chunk_entry, ChunkerConfig
from watercooler.memory_graph.leanrag_export import export_to_leanrag
from watercooler.memory_graph.cache import (
    SummaryCache,
    EmbeddingCache,
    ThreadSummaryCache,
    cache_stats,
    clear_cache,
)

__all__ = [
    # Schema
    "ThreadNode",
    "EntryNode",
    "ChunkNode",
    "EntityNode",
    "Edge",
    "Hyperedge",
    "EdgeType",
    "HyperedgeType",
    # Graph
    "MemoryGraph",
    "GraphConfig",
    # Parser
    "parse_thread_to_nodes",
    "parse_threads_directory",
    # Chunker
    "chunk_text",
    "chunk_entry",
    "ChunkerConfig",
    # Export
    "export_to_leanrag",
    # Cache
    "SummaryCache",
    "EmbeddingCache",
    "ThreadSummaryCache",
    "cache_stats",
    "clear_cache",
]
