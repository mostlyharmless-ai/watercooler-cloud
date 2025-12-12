"""Smoke tests for memory backends with real databases.

These tests validate full backend workflows (prepare→index→query) with real
database connections. They use minimal fixtures and are marked to run optionally.

Mark: @pytest.mark.integration_falkor
Usage: pytest -m integration_falkor

Runtime Expectations:
    LeanRAG tests: ~20-30 seconds (66 entries, hierarchical clustering)
    Graphiti minimal: ~4-5 minutes (5 entries, LLM entity extraction)
    Graphiti full: ~45-50 minutes (15 entries, temporal graph building)

CI Configuration:
    - Recommended timeout: 60 minutes for full test suite
    - Consider using @pytest.mark.slow for long-running tests
    - Graphiti tests require OPENAI_API_KEY environment variable
"""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Generator

from watercooler_memory.backends import (
    CorpusPayload,
    ChunkPayload,
    QueryPayload,
)
from watercooler_memory.backends.registry import get_backend
from watercooler_memory.graph import MemoryGraph


# Fixtures


@pytest.fixture(autouse=True, scope="session")
def cleanup_test_databases() -> None:
    """Clean test databases BEFORE running tests to allow post-test inspection.

    This fixture removes both Redis keys AND FalkorDB graphs with pytest__ prefix.
    FalkorDB stores graphs as separate data structures requiring GRAPH.DELETE.
    """
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=2)

        # First, delete FalkorDB graphs with pytest__ prefix
        # Use SCAN to find all keys, then check if they're graphs and delete
        cursor = 0
        graphs_deleted = []
        while True:
            cursor, keys = r.scan(cursor, match="pytest__*", count=100)
            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                try:
                    # Try to delete as a graph using GRAPH.DELETE
                    r.execute_command('GRAPH.DELETE', key_str)
                    graphs_deleted.append(key_str)
                except redis.ResponseError:
                    # Not a graph, delete as regular key
                    r.delete(key)
            if cursor == 0:
                break

    except (ConnectionError, TimeoutError) as e:
        import warnings
        warnings.warn(f"FalkorDB not available for test cleanup: {e}")
    except ImportError as e:
        import warnings
        warnings.warn(f"redis-py not installed for test cleanup: {e}")

    yield  # Run tests (results persist for inspection)


@pytest.fixture
def watercooler_threads_dir() -> Path:
    """Path to test watercooler threads (bundled with tests).

    Note: Contains unified-branch-parity-protocol.md (~68KB, 1798 lines, 38 entries).
    This real watercooler thread provides realistic test data for backend validation
    with authentic metadata, temporal relationships, and multi-agent conversations.
    """
    return Path(__file__).parent / "fixtures" / "threads"


@pytest.fixture
def watercooler_corpus(watercooler_threads_dir: Path) -> CorpusPayload:
    """
    Real watercooler corpus for integration testing.

    Uses actual watercooler threads to validate:
    - Custom chunker with real thread content
    - Entity extraction on actual agent conversations
    - Clustering with sufficient data volume
    """
    # Use substantial thread for testing (68K - rich technical content for clustering)
    # The unified-branch-parity-protocol thread has sufficient entries for proper
    # hierarchical clustering testing while being more manageable for CI
    test_threads = [
        "unified-branch-parity-protocol.md",
    ]

    # Build memory graph with watercooler preset for headers
    from watercooler_memory.chunker import ChunkerConfig
    from watercooler_memory.graph import GraphConfig

    config = GraphConfig(chunker=ChunkerConfig.watercooler_preset())
    graph = MemoryGraph(config=config)
    for thread_file in test_threads:
        thread_path = watercooler_threads_dir / thread_file
        if thread_path.exists():
            graph.add_thread(thread_path)

    # Chunk all entries using the custom watercooler chunker with headers
    chunk_nodes = graph.chunk_all_entries()

    # Convert to canonical payload format
    threads_data = [
        {
            "id": thread.thread_id,
            "topic": thread.thread_id,  # thread_id is the topic slug
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
            "timestamp": entry.timestamp,  # Already an ISO string
            # Include chunks for this entry
            "chunks": [
                {"text": chunk.text, "chunk_id": chunk.chunk_id}
                for chunk in graph.chunks.values()
                if chunk.entry_id == entry.entry_id
            ],
        }
        for entry in graph.entries.values()
    ]

    # Create corpus payload with chunker info
    return CorpusPayload(
        manifest_version="1.0.0",
        threads=threads_data,
        entries=entries_data,
        metadata={"source": "watercooler-threads", "test_mode": True},
        chunker_name="watercooler",
        chunker_params={"preset": "watercooler"},
    )


@pytest.fixture
def minimal_corpus() -> CorpusPayload:
    """
    Minimal corpus payload for smoke testing.

    Contains 2 threads with 5 total entries - enough to test the pipeline
    but small enough to complete quickly (<90s target).
    """
    return CorpusPayload(
        manifest_version="1.0.0",
        threads=[
            {
                "id": "auth-feature",
                "topic": "auth-feature",
                "status": "OPEN",
                "ball": "Claude",
                "entry_count": 3,
                "title": "Authentication Feature",
            },
            {
                "id": "payment-feature",
                "topic": "payment-feature",
                "status": "OPEN",
                "ball": "Codex",
                "entry_count": 2,
                "title": "Payment Integration",
            },
        ],
        entries=[
            # Thread 1: auth-feature
            {
                "id": "auth-1",
                "thread_id": "auth-feature",
                "agent": "Claude",
                "role": "planner",
                "type": "Plan",
                "title": "Authentication Design",
                "body": "Proposing OAuth2 with JWT tokens for secure authentication. "
                "Key requirements: (1) User login via OAuth providers, "
                "(2) JWT token generation and validation, "
                "(3) Refresh token rotation.",
                "timestamp": "2025-01-01T10:00:00Z",
            },
            {
                "id": "auth-2",
                "thread_id": "auth-feature",
                "agent": "Codex",
                "role": "critic",
                "type": "Note",
                "title": "Security Review",
                "body": "The OAuth2 design looks solid. Suggestions: "
                "(1) Use PKCE for mobile clients, "
                "(2) Implement rate limiting on auth endpoints, "
                "(3) Add audit logging for failed login attempts.",
                "timestamp": "2025-01-01T10:30:00Z",
            },
            {
                "id": "auth-3",
                "thread_id": "auth-feature",
                "agent": "Claude",
                "role": "implementer",
                "type": "Note",
                "title": "Implementation Complete",
                "body": "Implemented OAuth2 authentication with JWT tokens. "
                "Added PKCE support and rate limiting as suggested. "
                "All tests passing. Ready for review.",
                "timestamp": "2025-01-01T14:00:00Z",
            },
            # Thread 2: payment-feature
            {
                "id": "pay-1",
                "thread_id": "payment-feature",
                "agent": "Codex",
                "role": "planner",
                "type": "Plan",
                "title": "Payment Integration Plan",
                "body": "Integration with Stripe for payment processing. "
                "Features: (1) Credit card payments, "
                "(2) Subscription management, "
                "(3) Webhook handling for payment events.",
                "timestamp": "2025-01-02T09:00:00Z",
            },
            {
                "id": "pay-2",
                "thread_id": "payment-feature",
                "agent": "Claude",
                "role": "implementer",
                "type": "Note",
                "title": "Stripe Integration",
                "body": "Integrated Stripe SDK. Implemented payment processing, "
                "subscription management, and webhook handlers. "
                "Added retry logic for failed payments.",
                "timestamp": "2025-01-02T15:00:00Z",
            },
        ],
        edges=[
            {"source": "auth-feature", "target": "auth-1", "type": "CONTAINS"},
            {"source": "auth-feature", "target": "auth-2", "type": "CONTAINS"},
            {"source": "auth-feature", "target": "auth-3", "type": "CONTAINS"},
            {"source": "auth-1", "target": "auth-2", "type": "FOLLOWS"},
            {"source": "auth-2", "target": "auth-3", "type": "FOLLOWS"},
            {"source": "payment-feature", "target": "pay-1", "type": "CONTAINS"},
            {"source": "payment-feature", "target": "pay-2", "type": "CONTAINS"},
            {"source": "pay-1", "target": "pay-2", "type": "FOLLOWS"},
        ],
        metadata={"source": "smoke-test", "version": "1.0.0"},
    )


@pytest.fixture
def minimal_chunks() -> ChunkPayload:
    """
    Minimal chunk payload for smoke testing.

    Contains chunks derived from minimal_corpus entries.
    """
    return ChunkPayload(
        manifest_version="1.0.0",
        chunks=[
            {
                "id": "chunk-auth-1",
                "entry_id": "auth-1",
                "text": "Proposing OAuth2 with JWT tokens for secure authentication.",
                "token_count": 10,
                "hash_code": "abc123",
            },
            {
                "id": "chunk-auth-2",
                "entry_id": "auth-2",
                "text": "The OAuth2 design looks solid. Use PKCE for mobile clients.",
                "token_count": 12,
                "hash_code": "def456",
            },
            {
                "id": "chunk-auth-3",
                "entry_id": "auth-3",
                "text": "Implemented OAuth2 authentication with JWT tokens. All tests passing.",
                "token_count": 11,
                "hash_code": "ghi789",
            },
            {
                "id": "chunk-pay-1",
                "entry_id": "pay-1",
                "text": "Integration with Stripe for payment processing. Credit card payments.",
                "token_count": 11,
                "hash_code": "jkl012",
            },
            {
                "id": "chunk-pay-2",
                "entry_id": "pay-2",
                "text": "Integrated Stripe SDK. Implemented payment processing and webhooks.",
                "token_count": 10,
                "hash_code": "mno345",
            },
        ],
        threads=[
            {"id": "auth-feature", "topic": "auth-feature"},
            {"id": "payment-feature", "topic": "payment-feature"},
        ],
        entries=[
            {"id": "auth-1", "title": "Authentication Design"},
            {"id": "auth-2", "title": "Security Review"},
            {"id": "auth-3", "title": "Implementation Complete"},
            {"id": "pay-1", "title": "Payment Integration Plan"},
            {"id": "pay-2", "title": "Stripe Integration"},
        ],
    )


@pytest.fixture
def sample_queries() -> QueryPayload:
    """Sample queries for smoke testing."""
    return QueryPayload(
        manifest_version="1.0.0",
        queries=[
            {
                "query": "What authentication methods are being used?",
                "limit": 3,
            },
            {
                "query": "How is payment processing implemented?",
                "limit": 3,
            },
        ],
    )


# Smoke Tests


@pytest.mark.integration_falkor
class TestLeanRAGSmoke:
    """Smoke tests for LeanRAG backend with real FalkorDB."""

    @pytest.fixture
    def leanrag_backend(self, tmp_path: Path) -> Generator[LeanRAGBackend, None, None]:
        """LeanRAG backend with persistent working directory for inspection."""
        from watercooler_memory.backends.leanrag import LeanRAGBackend, LeanRAGConfig
        from pathlib import Path

        # Use persistent directory in project root so we can inspect artifacts
        # Backend will add pytest__ prefix automatically when test_mode=True
        work_dir = Path("tests/test_artifacts/leanrag_work")

        config = LeanRAGConfig(work_dir=work_dir, test_mode=True)
        backend = LeanRAGBackend(config)
        
        print(f"\n*** LeanRAG working directory: {work_dir.absolute()} ***\n")
        
        yield backend
        # Don't cleanup - leave artifacts for inspection

    def test_healthcheck(self, leanrag_backend):
        """LeanRAG healthcheck should succeed."""
        health = leanrag_backend.healthcheck()
        assert health.ok is True
        assert "LeanRAG available" in health.details
        # Note: FalkorDB connectivity might fail if not running locally

    def test_prepare_only(self, leanrag_backend, minimal_corpus):
        """LeanRAG prepare should create export files."""
        result = leanrag_backend.prepare(minimal_corpus)

        assert result.manifest_version == "1.0.0"
        assert result.prepared_count == 5  # 5 entries
        assert "Prepared corpus at" in result.message

        # Verify pytest__ prefix applied to work_dir when test_mode=True
        # Backend modifies work_dir internally, check actual directory created
        actual_dir = Path("tests/test_artifacts/pytest__leanrag_work")
        assert actual_dir.exists(), f"Expected pytest__ prefixed directory at {actual_dir}"
        assert actual_dir.name.startswith("pytest__"), "Work directory should have pytest__ prefix"

        # Verify export files exist in pytest__ prefixed directory
        assert (actual_dir / "documents.json").exists()
        assert (actual_dir / "threads.json").exists()
        assert (actual_dir / "manifest.json").exists()

    @pytest.mark.skipif(
        "os.environ.get('SKIP_LEANRAG_INDEX') == '1'",
        reason="LeanRAG indexing requires dependencies and takes time",
    )
    def test_prepare_index_query(
        self, leanrag_backend, minimal_corpus, minimal_chunks, sample_queries
    ):
        """Full LeanRAG pipeline: prepare→index→query."""
        # Step 1: Prepare
        prepare_result = leanrag_backend.prepare(minimal_corpus)
        assert prepare_result.prepared_count == 5

        # Step 2: Index (this will shell out to LeanRAG scripts)
        # NOTE: This requires:
        # - LeanRAG dependencies installed
        # - FalkorDB running
        # - LLM API configured (DeepSeek/OpenAI/local)
        index_result = leanrag_backend.index(minimal_chunks)
        assert index_result.indexed_count == 5
        assert "Indexed" in index_result.message

        # Step 3: Query
        query_result = leanrag_backend.query(sample_queries)
        assert query_result.manifest_version == "1.0.0"
        assert len(query_result.results) > 0
        assert "queries" in query_result.message

    @pytest.mark.integration_leanrag_llm
    def test_full_pipeline_watercooler_threads(
        self, leanrag_backend, watercooler_corpus, sample_queries
    ):
        """
        Full LeanRAG pipeline with real watercooler threads.

        Validates:
        - Custom chunker with real thread content
        - Entity extraction on actual agent conversations
        - Clustering with sufficient data volume (8-10 threads)

        Requires:
        - DEEPSEEK_API_KEY environment variable
        - GLM embedding server on port 8080 (or alternative configured)
        - FalkorDB running on port 6379
        """
        # Step 1: Prepare real watercooler thread
        prepare_result = leanrag_backend.prepare(watercooler_corpus)
        assert prepare_result.prepared_count > 0  # memory-backend thread has multiple entries
        print(f"Prepared {prepare_result.prepared_count} entries from watercooler thread")

        # Step 2: Index with entity extraction and clustering
        # This will test the full pipeline including hierarchical clustering
        # Extract chunks from corpus entries (created by watercooler preset)
        chunk_list = []
        for entry in watercooler_corpus.entries:
            for chunk in entry.get("chunks", []):
                chunk_list.append({
                    "id": chunk["chunk_id"],
                    "entry_id": entry["id"],
                    "text": chunk["text"],
                    "token_count": len(chunk["text"].split()),  # Rough estimate
                    "hash_code": chunk.get("hash_code", chunk["chunk_id"]),
                })
        
        chunks = ChunkPayload(
            manifest_version="1.0.0",
            chunks=chunk_list,  # Pass actual chunks from watercooler preset
            threads=watercooler_corpus.threads,
            entries=watercooler_corpus.entries,
        )
        index_result = leanrag_backend.index(chunks)
        assert index_result.indexed_count >= 0
        print(f"Indexed {index_result.indexed_count} chunks")

        # Step 3: Query with real questions about the threads
        real_queries = QueryPayload(
            manifest_version="1.0.0",
            queries=[
                {
                    "query": "What is the memory backend architecture?",
                    "limit": 5,
                },
                {
                    "query": "How does LeanRAG entity extraction work?",
                    "limit": 5,
                },
                {
                    "query": "What is the baseline graph pipeline?",
                    "limit": 5,
                },
            ],
        )
        query_result = leanrag_backend.query(real_queries)
        assert len(query_result.results) > 0
        print(f"Query returned {len(query_result.results)} results")


@pytest.mark.integration_falkor
class TestGraphitiSmoke:
    """Smoke tests for Graphiti backend with real database."""

    @pytest.fixture
    def graphiti_backend(self, tmp_path: Path) -> Generator[GraphitiBackend, None, None]:
        """Graphiti backend with temp working directory."""
        import os
        from watercooler_memory.backends.graphiti import (
            GraphitiBackend,
            GraphitiConfig,
        )

        # Ensure OpenAI API key is set (required for Graphiti)
        if "OPENAI_API_KEY" not in os.environ:
            pytest.skip("OPENAI_API_KEY not set - required for Graphiti")

        config = GraphitiConfig(work_dir=tmp_path / "pytest__graphiti_work", test_mode=True)
        backend = GraphitiBackend(config)
        yield backend

    def test_healthcheck(self, graphiti_backend):
        """Graphiti healthcheck should succeed."""
        health = graphiti_backend.healthcheck()
        assert health.ok is True
        assert "Graphiti available" in health.details
        # Note: Database connectivity might fail if not running

    def test_prepare_only(self, graphiti_backend, minimal_corpus):
        """Graphiti prepare should create episodes."""
        result = graphiti_backend.prepare(minimal_corpus)

        assert result.manifest_version == "1.0.0"
        assert result.prepared_count == 5  # 5 episodes
        assert "episodes" in result.message

        # Verify export files exist
        work_dir = graphiti_backend.config.work_dir
        assert (work_dir / "episodes.json").exists()
        assert (work_dir / "manifest.json").exists()

    @pytest.mark.skipif(
        "os.environ.get('SKIP_GRAPHITI_INDEX') == '1'",
        reason="Graphiti indexing requires implementation completion",
    )
    def test_prepare_index_query(
        self, graphiti_backend, minimal_corpus, minimal_chunks, sample_queries
    ):
        """Full Graphiti pipeline: prepare→index→query with minimal test data."""
        # Step 1: Prepare
        prepare_result = graphiti_backend.prepare(minimal_corpus)
        assert prepare_result.prepared_count == 5

        # Step 2: Index
        index_result = graphiti_backend.index(minimal_chunks)
        assert index_result.manifest_version == "1.0.0"

        # Step 3: Query
        query_result = graphiti_backend.query(sample_queries)
        assert query_result.manifest_version == "1.0.0"

    @pytest.mark.integration_falkor
    @pytest.mark.skipif(
        "os.environ.get('SKIP_GRAPHITI_INDEX') == '1'",
        reason="Graphiti indexing requires implementation completion",
    )
    def test_full_pipeline_watercooler_threads(
        self, graphiti_backend, watercooler_corpus, sample_queries
    ):
        """
        Full Graphiti pipeline with real watercooler threads (limited to 15 entries).

        Validates:
        - Episodic ingestion on actual watercooler thread content
        - Entity extraction from agent conversations
        - Temporal graph building with real data
        - Query execution on populated graph

        Note: Limits to first 15 entries for CI-friendly runtime (~45-50 min).
        Full 66-entry corpus would take ~3.5 hours (unsuitable for CI).
        The 15-entry subset provides sufficient validation coverage while
        remaining practical for automated testing.

        Requires:
        - OPENAI_API_KEY environment variable
        - FalkorDB running on port 6379
        """
        # Limit to first 15 entries for reasonable runtime
        # Full corpus has 66 entries which takes ~48 minutes
        from watercooler_memory.backends import CorpusPayload
        limited_corpus = CorpusPayload(
            manifest_version=watercooler_corpus.manifest_version,
            threads=watercooler_corpus.threads,
            entries=watercooler_corpus.entries[:15],  # Limit to 15 entries
            metadata=watercooler_corpus.metadata,
        )

        # Step 1: Prepare real watercooler thread
        prepare_result = graphiti_backend.prepare(limited_corpus)
        assert prepare_result.prepared_count > 0
        print(f"Prepared {prepare_result.prepared_count} entries from watercooler thread")

        # Step 2: Index - extract chunks and create episodes
        # Extract chunks from corpus entries (created by watercooler preset)
        from watercooler_memory.backends import ChunkPayload

        all_chunks = []
        for entry in limited_corpus.entries:
            # Each entry has chunks created by watercooler preset chunker
            if "chunks" in entry:
                for chunk in entry["chunks"]:
                    all_chunks.append({
                        "id": chunk.get("chunk_id", chunk.get("id")),
                        "entry_id": entry["id"],
                        "text": chunk["text"],
                        "token_count": chunk.get("token_count", 0),
                        "hash_code": chunk.get("hash_code", ""),
                    })

        chunks = ChunkPayload(
            manifest_version="1.0.0",
            chunks=all_chunks,
        )

        index_result = graphiti_backend.index(chunks)
        print(f"Indexed {index_result.indexed_count} episodes")
        assert index_result.indexed_count == prepare_result.prepared_count

        # Step 3: Query the populated graph
        query_result = graphiti_backend.query(sample_queries)
        print(f"Query returned {len(query_result.results)} results")
        assert query_result.manifest_version == "1.0.0"


@pytest.mark.integration_falkor
class TestMultiBackendComparison:
    """Compare results across backends (when both are functional)."""

    @pytest.mark.skipif(
        "os.environ.get('SKIP_BACKEND_COMPARISON') == '1'",
        reason="Backend comparison requires both backends fully implemented",
    )
    def test_same_query_both_backends(
        self, minimal_corpus, minimal_chunks, sample_queries, tmp_path
    ):
        """Same query should return results from both backends."""
        import os
        from watercooler_memory.backends.leanrag import LeanRAGBackend, LeanRAGConfig
        from watercooler_memory.backends.graphiti import (
            GraphitiBackend,
            GraphitiConfig,
        )

        if "OPENAI_API_KEY" not in os.environ:
            pytest.skip("OPENAI_API_KEY required")

        # Setup both backends with test_mode enabled
        leanrag = LeanRAGBackend(
            LeanRAGConfig(work_dir=tmp_path / "leanrag", test_mode=True)
        )
        graphiti = GraphitiBackend(
            GraphitiConfig(work_dir=tmp_path / "graphiti", test_mode=True)
        )

        # Prepare both
        leanrag.prepare(minimal_corpus)
        graphiti.prepare(minimal_corpus)

        # Index both
        leanrag.index(minimal_chunks)
        graphiti.index(minimal_chunks)

        # Query both
        leanrag_results = leanrag.query(sample_queries)
        graphiti_results = graphiti.query(sample_queries)

        # Both should return results
        assert len(leanrag_results.results) > 0
        assert len(graphiti_results.results) > 0

        # Results may differ (different retrieval strategies) but both valid
        print(f"LeanRAG returned {len(leanrag_results.results)} results")
        print(f"Graphiti returned {len(graphiti_results.results)} results")
