"""Null backend implementation for contract tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import (
    Capabilities,
    ChunkPayload,
    CorpusPayload,
    HealthStatus,
    IndexResult,
    MemoryBackend,
    PrepareResult,
    QueryPayload,
    QueryResult,
)


class NullBackend(MemoryBackend):
    """In-memory no-op backend that echoes payloads."""

    def __init__(self, capabilities: Capabilities | None = None) -> None:
        self._capabilities = capabilities or Capabilities(schema_versions=["1.0.0"])
        self._corpus: CorpusPayload | None = None
        self._chunks: ChunkPayload | None = None

    def prepare(self, corpus: CorpusPayload) -> PrepareResult:
        self._corpus = deepcopy(corpus)
        prepared_count = len(corpus.entries)
        return PrepareResult(
            manifest_version=corpus.manifest_version,
            prepared_count=prepared_count,
            message="null backend prepared corpus",
        )

    def index(self, chunks: ChunkPayload) -> IndexResult:
        self._chunks = deepcopy(chunks)
        indexed_count = len(chunks.chunks)
        return IndexResult(
            manifest_version=chunks.manifest_version,
            indexed_count=indexed_count,
            message="null backend indexed chunks",
        )

    def query(self, query: QueryPayload) -> QueryResult:
        results: list[dict[str, Any]] = []
        if self._chunks:
            for chunk in self._chunks.chunks:
                results.append(
                    {
                        "chunk": chunk,
                        "query": query.queries,
                    }
                )
        return QueryResult(
            manifest_version=query.manifest_version,
            results=results,
            message="null backend echo response",
        )

    def healthcheck(self) -> HealthStatus:
        return HealthStatus(ok=True, details="null backend is healthy")

    def get_capabilities(self) -> Capabilities:
        return deepcopy(self._capabilities)

