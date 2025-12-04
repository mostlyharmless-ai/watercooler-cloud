"""Memory graph for watercooler threads.

The MemoryGraph class ties together parsing, chunking, and summarization
to build a baseline graph from watercooler threads.

For full semantic search with entity extraction, export to LeanRAG format.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
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

    # Summarization
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig.from_env)

    # Processing options
    generate_summaries: bool = True
    skip_empty_entries: bool = True


class MemoryGraph:
    """In-memory graph of watercooler threads.

    Provides methods to build, query, and export the graph.

    The baseline graph includes:
    - Thread and entry metadata
    - Chunked entry bodies
    - LLM-generated summaries (using local models)

    For full semantic search with entity extraction and embeddings,
    export to LeanRAG format using export_to_leanrag().

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
                self.entries[entry_id] = replace(
                    self.entries[entry_id], chunk_ids=chunk_ids
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

        Note:
            This method makes one LLM API call per entry (N+1 pattern). For large
            graphs, this can be slow. Mitigations:
            - Disk caching: previously generated summaries are reused automatically
            - Skip short entries: entries <200 chars return body as-is
            - Use checkpoint_path in build() to save intermediate progress
            True batch summarization would require fundamentally different prompts
            and may sacrifice summary quality.

        Args:
            progress_callback: Optional callable(current, total, message) for progress reporting.
        """
        if not is_summarizer_available():
            raise ImportError(
                "httpx is required for summarization. "
                "Install with: pip install 'watercooler-cloud[memory]'"
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
            self.entries[entry_id] = replace(entry, summary=summary)

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
            self.threads[thread_id] = replace(thread, summary=summary)

    def build(
        self,
        threads_dir: Path,
        branch_context: Optional[str] = None,
        progress_callback=None,
        timeout: Optional[float] = None,
        checkpoint_path: Optional[Path] = None,
    ) -> None:
        """Build complete graph from threads directory.

        This is the main entry point for building a graph. It:
        1. Parses all threads
        2. Chunks all entries
        3. Generates summaries (if configured)

        For entity extraction and semantic search, export to LeanRAG format
        after building.

        Args:
            threads_dir: Path to threads directory.
            branch_context: Optional git branch name.
            progress_callback: Optional callable(current, total, message) for progress reporting.
            timeout: Optional timeout in seconds. Raises TimeoutError if exceeded.
            checkpoint_path: Optional path to save intermediate state after each step.
                This allows recovery if the build fails partway through.

        Raises:
            TimeoutError: If timeout is exceeded during build.
        """
        import time

        start_time = time.monotonic()

        def check_timeout():
            if timeout and (time.monotonic() - start_time) > timeout:
                raise TimeoutError(
                    f"Graph build exceeded timeout of {timeout}s"
                )

        def checkpoint(stage: str):
            """Save intermediate state if checkpoint_path is set."""
            if checkpoint_path:
                self.save(checkpoint_path)
                if progress_callback:
                    progress_callback(0, 0, f"Checkpoint saved after {stage}")

        # Parse threads
        if progress_callback:
            progress_callback(0, 0, "Parsing threads...")
        self.add_threads_directory(threads_dir, branch_context)
        check_timeout()
        checkpoint("parsing")

        # Chunk entries
        if progress_callback:
            progress_callback(0, 0, f"Chunking {len(self.entries)} entries...")
        self.chunk_all_entries()
        check_timeout()
        checkpoint("chunking")

        # Generate summaries
        if self.config.generate_summaries and is_summarizer_available():
            if progress_callback:
                progress_callback(0, 0, "Generating summaries...")
            self.generate_summaries(progress_callback)
            check_timeout()
            checkpoint("summarization")

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
        """Save graph to JSON file.

        Uses atomic write (temp file + rename) to prevent corruption
        if the process is interrupted mid-write.
        """
        temp_path = path.with_suffix(".tmp")
        try:
            temp_path.write_text(self.to_json())
            temp_path.replace(path)  # Atomic on POSIX
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise

    @classmethod
    def load(cls, path: Path, config: Optional[GraphConfig] = None) -> MemoryGraph:
        """Load graph from JSON file.

        Note:
            This loads the entire graph into memory. For very large graphs
            (>100k entries), consider:
            - Using the JSONL export format with LeanRAG for streaming access
            - Filtering threads during build() to create smaller focused graphs
            - Using a database backend for production search workloads

        Args:
            path: Path to the JSON file to load.
            config: Optional graph configuration.

        Returns:
            Loaded MemoryGraph instance.

        Raises:
            ValueError: If edge or hyperedge types are invalid.
        """
        data = json.loads(path.read_text())
        graph = cls(config)

        # Reconstruct nodes
        for tid, t in data.get("threads", {}).items():
            graph.threads[tid] = ThreadNode(**t)

        for eid, e in data.get("entries", {}).items():
            graph.entries[eid] = EntryNode(**e)

        for cid, c in data.get("chunks", {}).items():
            graph.chunks[cid] = ChunkNode(**c)

        for i, e in enumerate(data.get("edges", [])):
            try:
                e["edge_type"] = EdgeType(e["edge_type"])
            except ValueError as err:
                raise ValueError(
                    f"Invalid edge type '{e.get('edge_type')}' at edge {i}: {err}"
                ) from err
            graph.edges.append(Edge(**e))

        for i, h in enumerate(data.get("hyperedges", [])):
            from .schema import HyperedgeType

            try:
                h["hyperedge_type"] = HyperedgeType(h["hyperedge_type"])
            except ValueError as err:
                raise ValueError(
                    f"Invalid hyperedge type '{h.get('hyperedge_type')}' at hyperedge {i}: {err}"
                ) from err
            graph.hyperedges.append(Hyperedge(**h))

        return graph
