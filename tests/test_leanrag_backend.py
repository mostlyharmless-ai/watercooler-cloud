"""Unit tests for LeanRAG backend implementation.

Tests cover protocol compliance, normalization, ID modality enforcement,
and error handling for the LeanRAG memory backend.
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from watercooler_memory.backends import (
    LeanRAGBackend,
    LeanRAGConfig,
    UnsupportedOperationError,
    IdNotSupportedError,
    ConfigError,
    BackendError,
)


@pytest.fixture
def mock_config(tmp_path: Path) -> LeanRAGConfig:
    """Create a mock LeanRAG config for testing."""
    work_dir = tmp_path / "test_corpus"
    work_dir.mkdir()

    # Create dummy chunk file to pass validation
    (work_dir / "threads_chunk.json").write_text("{}")

    # Create fake leanrag directory to pass validation
    leanrag_dir = tmp_path / "fake_leanrag"
    leanrag_dir.mkdir()

    return LeanRAGConfig(
        work_dir=work_dir,
        leanrag_path=leanrag_dir,
        embedding_api_base="http://localhost:8000",
        embedding_model="test-model",
    )


@pytest.fixture
def backend(mock_config: LeanRAGConfig, monkeypatch) -> LeanRAGBackend:
    """Create a LeanRAG backend instance for testing."""
    # Patch _validate_config to skip LeanRAG installation checks in tests
    monkeypatch.setattr(LeanRAGBackend, '_validate_config', lambda self: None)
    return LeanRAGBackend(mock_config)


class TestSearchNodes:
    """Tests for search_nodes() method."""

    @patch('sys.path')
    @patch('os.getcwd')
    @patch('os.chdir')
    def test_search_nodes_success(self, mock_chdir, mock_getcwd, mock_syspath, backend):
        """Test successful node search returns normalized results."""
        # Mock LeanRAG adapter module
        mock_adapter = MagicMock()
        mock_adapter.search_vector_search = MagicMock(return_value=[
            ("OAUTH2", "AUTHENTICATION", "OAuth2 authorization framework", "chunk_abc123"),
            ("JWT_TOKENS", "OAUTH2", "JSON Web Tokens for auth", "chunk_def456"),
        ])

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter
        }):
            results = backend.search_nodes(query="authentication", max_results=10)

        assert len(results) == 2

        # Verify first result normalization
        result = results[0]
        assert result["id"] == "OAUTH2"
        assert result["name"] == "OAUTH2"
        assert result["backend"] == "leanrag"
        assert "summary" in result
        assert "metadata" in result
        assert "parent" in result["metadata"]
        assert "extra" in result
        assert "corpus" in result["extra"]

    def test_search_nodes_config_error(self, tmp_path, monkeypatch):
        """Test search_nodes raises ConfigError if work_dir not set."""
        leanrag_dir = tmp_path / "leanrag"
        leanrag_dir.mkdir()

        monkeypatch.setattr(LeanRAGBackend, '_validate_config', lambda self: None)
        config = LeanRAGConfig(leanrag_path=leanrag_dir)
        backend = LeanRAGBackend(config)

        with pytest.raises(ConfigError, match="work_dir must be set"):
            backend.search_nodes("test")

    def test_search_nodes_not_indexed(self, tmp_path, monkeypatch):
        """Test search_nodes raises ConfigError if database not indexed."""
        work_dir = tmp_path / "empty_corpus"
        work_dir.mkdir()
        # Don't create threads_chunk.json

        leanrag_dir = tmp_path / "leanrag"
        leanrag_dir.mkdir()

        monkeypatch.setattr(LeanRAGBackend, '_validate_config', lambda self: None)
        config = LeanRAGConfig(work_dir=work_dir, leanrag_path=leanrag_dir)
        backend = LeanRAGBackend(config)

        with pytest.raises(ConfigError, match="Database not indexed"):
            backend.search_nodes("test")


class TestSearchFacts:
    """Tests for search_facts() method."""

    @patch('sys.path')
    @patch('os.getcwd')
    @patch('os.chdir')
    def test_search_facts_success(self, mock_chdir, mock_getcwd, mock_syspath, backend):
        """Test successful fact search returns normalized results."""
        # Mock entity search
        mock_search_nodes = MagicMock(return_value=[
            {"id": "OAUTH2", "name": "OAUTH2"},
            {"id": "JWT_TOKENS", "name": "JWT_TOKENS"},
        ])

        # Mock LeanRAG adapter
        mock_adapter = MagicMock()
        mock_adapter.search_nodes_link = MagicMock(return_value=(
            "OAUTH2", "JWT_TOKENS", "Uses for authentication", 1.0, 0
        ))

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter
        }):
            with patch.object(backend, 'search_nodes', mock_search_nodes):
                results = backend.search_facts(query="authentication", max_results=5)

        assert len(results) > 0

        # Verify result normalization
        result = results[0]
        assert result["id"] == "OAUTH2||JWT_TOKENS"
        assert result["backend"] == "leanrag"
        assert "source_node_id" in result
        assert "target_node_id" in result
        assert "summary" in result
        assert "metadata" in result
        assert "extra" in result


class TestSearchEpisodes:
    """Tests for search_episodes() method."""

    def test_search_episodes_raises_unsupported(self, backend):
        """Test search_episodes raises UnsupportedOperationError."""
        with pytest.raises(UnsupportedOperationError) as exc_info:
            backend.search_episodes("test query")

        # Verify error message explains why
        assert "provenance" in str(exc_info.value).lower()
        assert "chunks lack" in str(exc_info.value).lower() or "no provenance" in str(exc_info.value).lower()


class TestGetNode:
    """Tests for get_node() method."""

    @patch('sys.path')
    @patch('os.getcwd')
    @patch('os.chdir')
    def test_get_node_success(self, mock_chdir, mock_getcwd, mock_syspath, backend):
        """Test successful node retrieval returns normalized result."""
        # Mock LeanRAG adapter
        mock_adapter = MagicMock()
        mock_adapter.search_nodes = MagicMock(return_value=[
            ("OAUTH2", "OAuth2 framework", "chunk_abc", 5, "AUTHENTICATION", 0)
        ])

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter
        }):
            result = backend.get_node("OAUTH2")

        assert result is not None
        assert result["id"] == "OAUTH2"
        assert result["name"] == "OAUTH2"
        assert result["backend"] == "leanrag"
        assert result["metadata"]["parent"] == "AUTHENTICATION"
        assert result["metadata"]["level"] == 0
        assert result["extra"]["corpus"] is not None

    @patch('sys.path')
    @patch('os.getcwd')
    @patch('os.chdir')
    def test_get_node_not_found(self, mock_chdir, mock_getcwd, mock_syspath, backend):
        """Test get_node returns None if entity not found."""
        # Mock LeanRAG adapter
        mock_adapter = MagicMock()
        mock_adapter.search_nodes = MagicMock(return_value=[])

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter
        }):
            result = backend.get_node("NONEXISTENT")

        assert result is None

    def test_get_node_rejects_uuid(self, backend):
        """Test get_node raises IdNotSupportedError for UUID-style IDs."""
        uuid_like_ids = [
            "01KCVY8C4TYG742H69YN375DB1",  # ULID
            "550e8400-e29b-41d4-a716-446655440000",  # UUID
            "01ARZ3NDEKTSV4RRFFQ69G5FAV",  # ULID variant
        ]

        for uuid_id in uuid_like_ids:
            with pytest.raises(IdNotSupportedError) as exc_info:
                backend.get_node(uuid_id)

            # Verify error message is actionable
            assert "entity names" in str(exc_info.value).lower()
            assert "uuid" in str(exc_info.value).lower()


class TestGetEdge:
    """Tests for get_edge() method."""

    @patch('sys.path')
    @patch('os.getcwd')
    @patch('os.chdir')
    def test_get_edge_success(self, mock_chdir, mock_getcwd, mock_syspath, backend):
        """Test successful edge retrieval returns normalized result."""
        # Mock LeanRAG adapter
        mock_adapter = MagicMock()
        mock_adapter.search_nodes_link = MagicMock(return_value=(
            "OAUTH2", "JWT_TOKENS", "Uses for authentication", 1.0, 0
        ))

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter
        }):
            result = backend.get_edge("OAUTH2||JWT_TOKENS")

        assert result is not None
        assert result["id"] == "OAUTH2||JWT_TOKENS"
        assert result["backend"] == "leanrag"
        assert result["source_node_id"] == "OAUTH2"
        assert result["target_node_id"] == "JWT_TOKENS"
        assert "summary" in result
        assert "metadata" in result
        assert result["extra"]["corpus"] is not None

    @patch('sys.path')
    @patch('os.getcwd')
    @patch('os.chdir')
    def test_get_edge_not_found(self, mock_chdir, mock_getcwd, mock_syspath, backend):
        """Test get_edge returns None if relationship not found."""
        # Mock LeanRAG adapter
        mock_adapter = MagicMock()
        mock_adapter.search_nodes_link = MagicMock(return_value=None)

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter
        }):
            result = backend.get_edge("SOURCE||TARGET")

        assert result is None

    def test_get_edge_rejects_malformed_id(self, backend):
        """Test get_edge raises IdNotSupportedError for malformed IDs."""
        malformed_ids = [
            "OAUTH2",  # Missing ||
            "OAUTH2|JWT",  # Single pipe
            "",  # Empty
            "||",  # No entities
            "01KCVY8C4TYG742H69YN375DB1",  # UUID (no ||)
        ]

        for bad_id in malformed_ids:
            with pytest.raises(IdNotSupportedError) as exc_info:
                backend.get_edge(bad_id)

            # Verify error message is actionable
            assert "SOURCE||TARGET" in str(exc_info.value) or "synthetic" in str(exc_info.value).lower()


class TestGetCapabilities:
    """Tests for get_capabilities() method."""

    def test_capabilities_structure(self, backend):
        """Test capabilities returns correct structure."""
        caps = backend.get_capabilities()

        # Protocol extension flags
        assert caps.supports_nodes is True
        assert caps.supports_facts is True
        assert caps.supports_episodes is False
        assert caps.supports_chunks is False  # Not yet implemented
        assert caps.supports_edges is True

        # ID modality
        assert caps.node_id_type == "name"
        assert caps.edge_id_type == "synthetic"

        # Legacy capabilities
        assert caps.entity_extraction is True
        assert caps.graph_query is True

    def test_capabilities_milvus_conditional(self, tmp_path, monkeypatch):
        """Test Milvus support conditional on embedding_api_base."""
        work_dir = tmp_path / "test"
        work_dir.mkdir()
        (work_dir / "threads_chunk.json").write_text("{}")

        leanrag_dir = tmp_path / "leanrag"
        leanrag_dir.mkdir()

        monkeypatch.setattr(LeanRAGBackend, '_validate_config', lambda self: None)

        # With embedding API
        config_with = LeanRAGConfig(
            work_dir=work_dir,
            leanrag_path=leanrag_dir,
            embedding_api_base="http://localhost:8000"
        )
        backend_with = LeanRAGBackend(config_with)
        assert backend_with.get_capabilities().supports_milvus is True

        # Without embedding API
        config_without = LeanRAGConfig(
            work_dir=work_dir,
            leanrag_path=leanrag_dir,
        )
        backend_without = LeanRAGBackend(config_without)
        assert backend_without.get_capabilities().supports_milvus is False


class TestNormalization:
    """Tests to verify response normalization across all methods."""

    @patch('sys.path')
    @patch('os.getcwd')
    @patch('os.chdir')
    def test_all_responses_include_backend_tag(self, mock_chdir, mock_getcwd, mock_syspath, backend):
        """Test all method responses include backend='leanrag'."""
        # Mock search_nodes
        mock_adapter_search = MagicMock()
        mock_adapter_search.search_vector_search = MagicMock(return_value=[
            ("OAUTH2", "AUTH", "OAuth2", "chunk_abc"),
        ])

        # Mock get_node
        mock_adapter_get = MagicMock()
        mock_adapter_get.search_nodes = MagicMock(return_value=[
            ("OAUTH2", "OAuth2", "chunk_abc", 5, "AUTH", 0)
        ])

        # Mock get_edge
        mock_adapter_edge = MagicMock()
        mock_adapter_edge.search_nodes_link = MagicMock(return_value=(
            "OAUTH2", "JWT", "Uses", 1.0, 0
        ))

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter_search
        }):
            nodes = backend.search_nodes("test")
            assert all(n["backend"] == "leanrag" for n in nodes)

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter_get
        }):
            node = backend.get_node("OAUTH2")
            assert node["backend"] == "leanrag"

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter_edge
        }):
            edge = backend.get_edge("OAUTH2||JWT")
            assert edge["backend"] == "leanrag"

    @patch('sys.path')
    @patch('os.getcwd')
    @patch('os.chdir')
    def test_responses_include_extra_fields(self, mock_chdir, mock_getcwd, mock_syspath, backend):
        """Test responses include backend-specific fields in extra map."""
        # Mock LeanRAG adapter
        mock_adapter = MagicMock()
        mock_adapter.search_nodes = MagicMock(return_value=[
            ("OAUTH2", "OAuth2", "chunk_abc", 5, "AUTH", 0)
        ])

        with patch.dict('sys.modules', {
            'leanrag': MagicMock(),
            'leanrag.database': MagicMock(),
            'leanrag.database.adapter': mock_adapter
        }):
            node = backend.get_node("OAUTH2")

        # Verify extra fields
        assert "extra" in node
        assert "corpus" in node["extra"]

        # Verify metadata fields
        assert "metadata" in node
        assert "parent" in node["metadata"]
        assert "level" in node["metadata"]
        assert "degree" in node["metadata"]
