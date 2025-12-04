"""Baseline graph module for free-tier knowledge graphs.

This module provides a lightweight knowledge graph built from threads
using locally-hosted LLMs (Ollama, llama.cpp) - no API costs required.

Key components:
- summarizer: LLM-based summarization with extractive fallback
- parser: Thread parsing and entity extraction
- export: JSONL export for graph storage
"""

from .summarizer import (
    summarize_entry,
    summarize_thread,
    extractive_summary,
    SummarizerConfig,
    create_summarizer_config,
)

from .parser import (
    ParsedEntry,
    ParsedThread,
    parse_thread_file,
    iter_threads,
    parse_all_threads,
    get_thread_stats,
)

from .export import (
    export_thread_graph,
    export_all_threads,
    load_nodes,
    load_edges,
    load_graph,
)

__all__ = [
    # Summarizer
    "summarize_entry",
    "summarize_thread",
    "extractive_summary",
    "SummarizerConfig",
    "create_summarizer_config",
    # Parser
    "ParsedEntry",
    "ParsedThread",
    "parse_thread_file",
    "iter_threads",
    "parse_all_threads",
    "get_thread_stats",
    # Export
    "export_thread_graph",
    "export_all_threads",
    "load_nodes",
    "load_edges",
    "load_graph",
]
