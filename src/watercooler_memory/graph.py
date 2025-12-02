"""Memory graph for watercooler threads.

The MemoryGraph class ties together parsing, chunking, embedding, and
summarization to build a searchable graph from watercooler threads.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .schema import (
    ThreadNode,
    EntryNode,
    ChunkNode,
    Edge,
    Hyperedge,
    EdgeType,
)
from .parser import parse_thread_to_nodes, parse_threads_directory
from .chunker import chunk_entries, ChunkerConfig
from .embeddings import embed_texts, EmbeddingConfig, is_httpx_available
from .summarizer import (
    summarize_entry,
    summarize_thread,
    SummarizerConfig,
    is_summarizer_available,
)


@dataclass
class GraphConfig:
    """Configuration for memory graph building."""

    # Chunking
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)

    # Embeddings
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig.from_env)

    # Summarization
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig.from_env)

    # Processing options
    generate_summaries: bool = True
    generate_embeddings: bool = True
    skip_empty_entries: bool = True


class MemoryGraph:
    """In-memory graph of watercooler threads.

    Provides methods to build, query, and export the graph.

    Attributes:
        threads: Dict of thread_id → ThreadNode
        entries: Dict of entry_id → EntryNode
        chunks: Dict of chunk_id → ChunkNode
        edges: List of all edges
        hyperedges: List of all hyperedges
    """

    def __init__(self, config: Optional[GraphConfig] = None):
        """Initialize empty graph.

        Args:
            config: Graph configuration.
        """
        self.config = config or GraphConfig()

        self.threads: dict[str, ThreadNode] = {}
        self.entries: dict[str, EntryNode] = {}
        self.chunks: dict[str, ChunkNode] = {}
        self.edges: list[Edge] = []
        self.hyperedges: list[Hyperedge] = []

    def add_thread(
        self,
        thread_path: Path,
        branch_context: Optional[str] = None,
    ) -> ThreadNode:
        """Add a thread to the graph.

        Args:
            thread_path: Path to thread markdown file.
            branch_context: Optional git branch name.

        Returns:
            The created ThreadNode.
        """
        thread, entries, edges, hyperedges = parse_thread_to_nodes(
            thread_path, branch_context
        )

        # Store thread
        self.threads[thread.thread_id] = thread

        # Store entries
        for entry in entries:
            if self.config.skip_empty_entries and not entry.body.strip():
                continue
            self.entries[entry.entry_id] = entry

        # Store edges and hyperedges
        self.edges.extend(edges)
        self.hyperedges.extend(hyperedges)

        return thread

    def add_threads_directory(
        self,
        threads_dir: Path,
        branch_context: Optional[str] = None,
    ) -> list[ThreadNode]:
        """Add all threads from a directory.

        Args:
            threads_dir: Path to threads directory.
            branch_context: Optional git branch name.

        Returns:
            List of created ThreadNodes.
        """
        threads, entries, edges, hyperedges = parse_threads_directory(
            threads_dir, branch_context
        )

        for thread in threads:
            self.threads[thread.thread_id] = thread

        for entry in entries:
            if self.config.skip_empty_entries and not entry.body.strip():
                continue
            self.entries[entry.entry_id] = entry

        self.edges.extend(edges)
        self.hyperedges.extend(hyperedges)

        return threads

    def chunk_all_entries(self) -> list[ChunkNode]:
        """Chunk all entries in the graph.

        Returns:
            List of created ChunkNodes.
        """
        entries = list(self.entries.values())
        chunks, entry_to_chunks = chunk_entries(entries, self.config.chunker)

        # Store chunks
        for chunk in chunks:
            self.chunks[chunk.chunk_id] = chunk

        # Update entry references
        for entry_id, chunk_ids in entry_to_chunks.items():
            if entry_id in self.entries:
                entry = self.entries[entry_id]
                # Create new entry with updated chunk_ids
                self.entries[entry_id] = EntryNode(
                    entry_id=entry.entry_id,
                    thread_id=entry.thread_id,
                    index=entry.index,
                    agent=entry.agent,
                    role=entry.role,
                    entry_type=entry.entry_type,
                    title=entry.title,
                    timestamp=entry.timestamp,
                    body=entry.body,
                    chunk_ids=chunk_ids,
                    summary=entry.summary,
                    embedding=entry.embedding,
                    sequence_index=entry.sequence_index,
                    preceding_entry_id=entry.preceding_entry_id,
                    following_entry_id=entry.following_entry_id,
                    ingestion_time=entry.ingestion_time,
                )

        # Add CONTAINS edges for chunks
        for chunk in chunks:
            self.edges.append(
                Edge.contains(
                    parent_id=f"entry:{chunk.entry_id}",
                    child_id=f"chunk:{chunk.chunk_id}",
                    event_time=chunk.event_time,
                )
            )

        return chunks

    def generate_summaries(self, progress_callback=None) -> None:
        """Generate summaries for all entries and threads.

        Summaries are cached to disk - if a previous run was interrupted,
        cached summaries will be reused.

        Args:
            progress_callback: Optional callable(current, total, message) for progress reporting.
        """
        if not is_summarizer_available():
            raise ImportError(
                "httpx is required for summarization. "
                "Install with: pip install 'watercooler-cloud[graph]'"
            )

        total_entries = len(self.entries)

        # Summarize entries
        for i, (entry_id, entry) in enumerate(self.entries.items()):
            if progress_callback:
                progress_callback(i + 1, total_entries, f"Summarizing entry {i + 1}/{total_entries}")

            if entry.summary:
                continue  # Already summarized

            summary = summarize_entry(
                body=entry.body,
                agent=entry.agent,
                role=entry.role,
                entry_type=entry.entry_type,
                title=entry.title,
                config=self.config.summarizer,
                entry_id=entry_id,  # For caching
            )

            # Update entry with summary
            self.entries[entry_id] = EntryNode(
                entry_id=entry.entry_id,
                thread_id=entry.thread_id,
                index=entry.index,
                agent=entry.agent,
                role=entry.role,
                entry_type=entry.entry_type,
                title=entry.title,
                timestamp=entry.timestamp,
                body=entry.body,
                chunk_ids=entry.chunk_ids,
                summary=summary,
                embedding=entry.embedding,
                sequence_index=entry.sequence_index,
                preceding_entry_id=entry.preceding_entry_id,
                following_entry_id=entry.following_entry_id,
                ingestion_time=entry.ingestion_time,
            )

        # Summarize threads
        for thread_id, thread in self.threads.items():
            if thread.summary:
                continue

            # Get entry summaries for this thread
            entry_summaries = [
                self.entries[eid].summary
                for eid in thread.entry_ids
                if eid in self.entries and self.entries[eid].summary
            ]

            summary = summarize_thread(
                title=thread.title,
                status=thread.status,
                entry_summaries=entry_summaries,
                config=self.config.summarizer,
                thread_id=thread_id,  # For caching
            )

            # Update thread with summary
            self.threads[thread_id] = ThreadNode(
                thread_id=thread.thread_id,
                title=thread.title,
                status=thread.status,
                ball=thread.ball,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                entry_ids=thread.entry_ids,
                summary=summary,
                embedding=thread.embedding,
                branch_context=thread.branch_context,
                initial_commit=thread.initial_commit,
                ingestion_time=thread.ingestion_time,
            )

    def generate_embeddings(self) -> None:
        """Generate embeddings for all nodes with summaries."""
        if not is_httpx_available():
            raise ImportError(
                "httpx is required for embeddings. "
                "Install with: pip install 'watercooler-cloud[graph]'"
            )

        # Collect texts to embed
        texts_to_embed: list[tuple[str, str, str]] = []  # (node_type, node_id, text)

        # Thread summaries
        for thread_id, thread in self.threads.items():
            if thread.summary and not thread.embedding:
                texts_to_embed.append(("thread", thread_id, thread.summary))

        # Entry summaries
        for entry_id, entry in self.entries.items():
            if entry.summary and not entry.embedding:
                texts_to_embed.append(("entry", entry_id, entry.summary))

        # Chunk texts
        for chunk_id, chunk in self.chunks.items():
            if chunk.text and not chunk.embedding:
                texts_to_embed.append(("chunk", chunk_id, chunk.text))

        if not texts_to_embed:
            return

        # Batch embed
        texts = [t[2] for t in texts_to_embed]
        embeddings = embed_texts(texts, self.config.embedding)

        # Update nodes with embeddings
        for (node_type, node_id, _), embedding in zip(texts_to_embed, embeddings):
            if node_type == "thread":
                thread = self.threads[node_id]
                self.threads[node_id] = ThreadNode(
                    thread_id=thread.thread_id,
                    title=thread.title,
                    status=thread.status,
                    ball=thread.ball,
                    created_at=thread.created_at,
                    updated_at=thread.updated_at,
                    entry_ids=thread.entry_ids,
                    summary=thread.summary,
                    embedding=embedding,
                    branch_context=thread.branch_context,
                    initial_commit=thread.initial_commit,
                    ingestion_time=thread.ingestion_time,
                )
            elif node_type == "entry":
                entry = self.entries[node_id]
                self.entries[node_id] = EntryNode(
                    entry_id=entry.entry_id,
                    thread_id=entry.thread_id,
                    index=entry.index,
                    agent=entry.agent,
                    role=entry.role,
                    entry_type=entry.entry_type,
                    title=entry.title,
                    timestamp=entry.timestamp,
                    body=entry.body,
                    chunk_ids=entry.chunk_ids,
                    summary=entry.summary,
                    embedding=embedding,
                    sequence_index=entry.sequence_index,
                    preceding_entry_id=entry.preceding_entry_id,
                    following_entry_id=entry.following_entry_id,
                    ingestion_time=entry.ingestion_time,
                )
            elif node_type == "chunk":
                chunk = self.chunks[node_id]
                self.chunks[node_id] = ChunkNode(
                    chunk_id=chunk.chunk_id,
                    entry_id=chunk.entry_id,
                    thread_id=chunk.thread_id,
                    index=chunk.index,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    embedding=embedding,
                    event_time=chunk.event_time,
                    ingestion_time=chunk.ingestion_time,
                )

    def build(
        self,
        threads_dir: Path,
        branch_context: Optional[str] = None,
        progress_callback=None,
    ) -> None:
        """Build complete graph from threads directory.

        This is the main entry point for building a graph. It:
        1. Parses all threads
        2. Chunks all entries
        3. Generates summaries (if configured)
        4. Generates embeddings (if configured)

        Args:
            threads_dir: Path to threads directory.
            branch_context: Optional git branch name.
            progress_callback: Optional callable(current, total, message) for progress reporting.
        """
        # Parse threads
        if progress_callback:
            progress_callback(0, 0, "Parsing threads...")
        self.add_threads_directory(threads_dir, branch_context)

        # Chunk entries
        if progress_callback:
            progress_callback(0, 0, f"Chunking {len(self.entries)} entries...")
        self.chunk_all_entries()

        # Generate summaries
        if self.config.generate_summaries and is_summarizer_available():
            if progress_callback:
                progress_callback(0, 0, "Generating summaries...")
            self.generate_summaries(progress_callback)

        # Generate embeddings
        if self.config.generate_embeddings and is_httpx_available():
            if progress_callback:
                progress_callback(0, 0, "Generating embeddings...")
            self.generate_embeddings()

    def stats(self) -> dict:
        """Return graph statistics."""
        return {
            "threads": len(self.threads),
            "entries": len(self.entries),
            "chunks": len(self.chunks),
            "edges": len(self.edges),
            "hyperedges": len(self.hyperedges),
            "entries_with_summaries": sum(
                1 for e in self.entries.values() if e.summary
            ),
            "entries_with_embeddings": sum(
                1 for e in self.entries.values() if e.embedding
            ),
            "chunks_with_embeddings": sum(
                1 for c in self.chunks.values() if c.embedding
            ),
        }

    def to_dict(self) -> dict:
        """Convert graph to dictionary for serialization."""
        return {
            "threads": {tid: asdict(t) for tid, t in self.threads.items()},
            "entries": {eid: asdict(e) for eid, e in self.entries.items()},
            "chunks": {cid: asdict(c) for cid, c in self.chunks.items()},
            "edges": [asdict(e) for e in self.edges],
            "hyperedges": [asdict(h) for h in self.hyperedges],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert graph to JSON string."""
        data = self.to_dict()

        # Convert edge_type enums to strings
        for edge in data["edges"]:
            if isinstance(edge.get("edge_type"), EdgeType):
                edge["edge_type"] = edge["edge_type"].value

        return json.dumps(data, indent=indent, default=str)

    def save(self, path: Path) -> None:
        """Save graph to JSON file."""
        path.write_text(self.to_json())

    @classmethod
    def load(cls, path: Path, config: Optional[GraphConfig] = None) -> MemoryGraph:
        """Load graph from JSON file."""
        data = json.loads(path.read_text())
        graph = cls(config)

        # Reconstruct nodes (simplified - embeddings are lists, not numpy arrays)
        for tid, t in data.get("threads", {}).items():
            graph.threads[tid] = ThreadNode(**t)

        for eid, e in data.get("entries", {}).items():
            graph.entries[eid] = EntryNode(**e)

        for cid, c in data.get("chunks", {}).items():
            graph.chunks[cid] = ChunkNode(**c)

        for e in data.get("edges", []):
            e["edge_type"] = EdgeType(e["edge_type"])
            graph.edges.append(Edge(**e))

        for h in data.get("hyperedges", []):
            from .schema import HyperedgeType

            h["hyperedge_type"] = HyperedgeType(h["hyperedge_type"])
            graph.hyperedges.append(Hyperedge(**h))

        return graph
