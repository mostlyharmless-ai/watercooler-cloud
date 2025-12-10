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
        """Prepare a corpus for indexing."""

    def index(self, chunks: ChunkPayload) -> IndexResult:
        """Index prepared chunks."""

    def query(self, query: QueryPayload) -> QueryResult:
        """Execute a query against the backend."""

    def healthcheck(self) -> HealthStatus:
        """Report backend health."""

    def get_capabilities(self) -> Capabilities:
        """Return supported capabilities."""


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
