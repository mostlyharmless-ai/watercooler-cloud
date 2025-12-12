"""Backend contract for pluggable memory systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence, Any, runtime_checkable


class BackendError(Exception):
    """Base exception for backend failures."""


class ConfigError(BackendError):
    """Raised when backend configuration is invalid."""


class TransientError(BackendError):
    """Raised for retryable errors."""


@dataclass
class Capabilities:
    """Describes supported backend features."""

    embeddings: bool = False
    entity_extraction: bool = False
    graph_query: bool = False
    rerank: bool = False
    schema_versions: Sequence[str] = field(default_factory=list)
    supports_falkor: bool = False
    supports_milvus: bool = False
    supports_neo4j: bool = False
    max_tokens: int | None = None


@dataclass
class HealthStatus:
    """Health response from backend."""

    ok: bool
    details: str | None = None


@dataclass
class PrepareResult:
    """Result of prepare step."""

    manifest_version: str
    prepared_count: int = 0
    message: str | None = None


@dataclass
class IndexResult:
    """Result of index step."""

    manifest_version: str
    indexed_count: int = 0
    message: str | None = None


@dataclass
class QueryResult:
    """Result of query step."""

    manifest_version: str
    results: Sequence[Mapping[str, Any]] = field(default_factory=list)
    message: str | None = None


@dataclass
class CorpusPayload:
    """Canonical corpus payload passed to prepare()."""

    manifest_version: str
    threads: Sequence[Mapping[str, Any]]
    entries: Sequence[Mapping[str, Any]]
    edges: Sequence[Mapping[str, Any]] | None = None
    metadata: Mapping[str, Any] | None = None
    chunker_name: str | None = None
    chunker_params: Mapping[str, Any] | None = None


@dataclass
class ChunkPayload:
    """Chunk payload passed to index()."""

    manifest_version: str
    chunks: Sequence[Mapping[str, Any]]
    threads: Sequence[Mapping[str, Any]] | None = None
    entries: Sequence[Mapping[str, Any]] | None = None
    edges: Sequence[Mapping[str, Any]] | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass
class QueryPayload:
    """Query payload passed to query()."""

    manifest_version: str
    queries: Sequence[Mapping[str, Any]]
    metadata: Mapping[str, Any] | None = None


@runtime_checkable
class MemoryBackend(Protocol):
    """Protocol for pluggable memory backends."""

    def prepare(self, corpus: CorpusPayload) -> PrepareResult:
        """Prepare a corpus for indexing.

        This step processes raw watercooler threads and entries for indexing. Different
        backends may perform entity extraction, chunking, or other preprocessing.

        Args:
            corpus: Canonical corpus payload containing threads and entries.

        Returns:
            PrepareResult with count of prepared items and optional message.

        Raises:
            ConfigError: If backend configuration is invalid.
            TransientError: For retryable failures (network timeouts, API limits).
            BackendError: For other backend failures.

        Example:
            >>> from watercooler_memory.backends import get_backend, LeanRAGConfig
            >>> from watercooler_memory.backends import CorpusPayload
            >>> config = LeanRAGConfig(work_dir=Path("./memory"))
            >>> backend = get_backend("leanrag", config)
            >>> corpus = CorpusPayload(
            ...     manifest_version="1.0.0",
            ...     threads=[{"thread_id": "auth", "title": "Auth Feature"}],
            ...     entries=[{
            ...         "id": "entry-001",
            ...         "thread_id": "auth",
            ...         "agent": "Claude",
            ...         "role": "implementer",
            ...         "entry_type": "Note",
            ...         "timestamp": "2025-01-01T12:00:00Z",
            ...         "title": "OAuth Implementation",
            ...         "body": "Implemented OAuth2 with JWT tokens...",
            ...     }],
            ... )
            >>> result = backend.prepare(corpus)
            >>> print(f"Prepared {result.prepared_count} entries")
            Prepared 1 entries
        """

    def index(self, chunks: ChunkPayload) -> IndexResult:
        """Index prepared chunks into the backend's storage.

        This step builds the knowledge graph, vector index, or other backend-specific
        data structures from chunked text. For LeanRAG this runs entity extraction and
        graph building. For Graphiti this is typically a no-op (indexing happens during prepare).

        Args:
            chunks: Chunk payload with text chunks and optional metadata.

        Returns:
            IndexResult with count of indexed chunks and optional message.

        Raises:
            ConfigError: If backend configuration is invalid.
            TransientError: For retryable failures.
            BackendError: For other backend failures.

        Example:
            >>> from watercooler_memory.backends import ChunkPayload
            >>> chunks = ChunkPayload(
            ...     manifest_version="1.0.0",
            ...     chunks=[
            ...         {
            ...             "hash_code": "abc123",
            ...             "text": "OAuth2 implementation complete with JWT support.",
            ...             "metadata": {"thread_id": "auth", "entry_id": "entry-001"},
            ...         }
            ...     ],
            ... )
            >>> result = backend.index(chunks)
            >>> print(f"Indexed {result.indexed_count} chunks")
            Indexed 1 chunks
        """

    def query(self, query: QueryPayload) -> QueryResult:
        """Execute semantic search queries against the backend.

        Returns relevant results based on the backend's search strategy (vector similarity,
        graph traversal, hybrid search, etc.). Results include content, scores, and metadata.

        Args:
            query: Query payload with one or more query strings.

        Returns:
            QueryResult with search results and optional message.

        Raises:
            ConfigError: If backend configuration is invalid.
            TransientError: For retryable failures.
            BackendError: For other backend failures.

        Example:
            >>> from watercooler_memory.backends import QueryPayload
            >>> queries = QueryPayload(
            ...     manifest_version="1.0.0",
            ...     queries=[
            ...         {"query": "What authentication method was implemented?"},
            ...         {"query": "Who implemented OAuth2?"},
            ...     ],
            ... )
            >>> result = backend.query(queries)
            >>> for item in result.results:
            ...     # Each item is a dict with keys: query, content, score, metadata
            ...     print(f"Query: {item['query']}")
            ...     print(f"Content: {item['content'][:100]}...")
            ...     print(f"Score: {item['score']:.2f}")
            ...     print(f"Metadata: {item.get('metadata', {})}")
            Query: What authentication method was implemented?
            Content: Implemented OAuth2 with JWT tokens for secure authentication...
            Score: 0.89
            Metadata: {'thread_id': 'auth', 'entry_id': 'entry-001'}
        """

    def healthcheck(self) -> HealthStatus:
        """Check backend health and dependencies.

        Verifies that the backend can connect to required services (databases, APIs),
        has necessary credentials, and is ready for operations. Always call this before
        running prepare/index/query operations.

        Returns:
            HealthStatus with ok flag and optional details message.

        Example:
            >>> health = backend.healthcheck()
            >>> if not health.ok:
            ...     print(f"Backend not healthy: {health.details}")
            ...     exit(1)
            >>> print("Backend ready")
            Backend ready
        """

    def get_capabilities(self) -> Capabilities:
        """Return supported backend capabilities.

        Query the backend's feature set to determine what operations are supported
        (embeddings, entity extraction, graph queries, etc.).

        Returns:
            Capabilities object describing supported features.

        Example:
            >>> caps = backend.get_capabilities()
            >>> if caps.entity_extraction:
            ...     print("Backend supports entity extraction")
            >>> if caps.supports_falkor:
            ...     print("Using FalkorDB graph database")
            Backend supports entity extraction
            Using FalkorDB graph database
        """


__all__ = [
    "BackendError",
    "Capabilities",
    "ChunkPayload",
    "ConfigError",
    "CorpusPayload",
    "HealthStatus",
    "IndexResult",
    "MemoryBackend",
    "PrepareResult",
    "QueryPayload",
    "QueryResult",
    "TransientError",
    # Registry helpers
    "register_backend",
    "get_backend",
    "list_backends",
    "resolve_backend",
    "auto_register_builtin",
]

# Registry re-exports
from .registry import (  # noqa: E402
    auto_register_builtin,
    get_backend,
    list_backends,
    register_backend,
    resolve_backend,
)
