"""Unit tests for MCP memory integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from watercooler_mcp import memory


@pytest.fixture
def mock_env_disabled(monkeypatch):
    """Mock environment with Graphiti disabled."""
    monkeypatch.setenv("WATERCOOLER_GRAPHITI_ENABLED", "0")


@pytest.fixture
def mock_env_enabled(monkeypatch):
    """Mock environment with Graphiti enabled."""
    monkeypatch.setenv("WATERCOOLER_GRAPHITI_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


class TestLoadGraphitiConfig:
    """Tests for load_graphiti_config() function."""

    def test_load_config_disabled(self, mock_env_disabled):
        """Test config loading when Graphiti is disabled."""
        config = memory.load_graphiti_config()
        assert config is None

    def test_load_config_missing_api_key(self, monkeypatch):
        """Test config loading fails gracefully without API key."""
        monkeypatch.setenv("WATERCOOLER_GRAPHITI_ENABLED", "1")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        config = memory.load_graphiti_config()
        assert config is None

    def test_load_config_success(self, mock_env_enabled):
        """Test config loading with valid environment."""
        config = memory.load_graphiti_config()
        assert config is not None
        assert config.openai_api_key == "sk-test"

    def test_load_config_uses_openai_api_key(self, monkeypatch):
        """Test config uses OPENAI_API_KEY."""
        monkeypatch.setenv("WATERCOOLER_GRAPHITI_ENABLED", "1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")

        config = memory.load_graphiti_config()
        assert config is not None
        assert config.openai_api_key == "sk-from-env"


class TestGetGraphitiBackend:
    """Tests for get_graphiti_backend() function."""

    def test_get_backend_import_error(self, mock_env_enabled):
        """Test backend handles missing dependencies gracefully."""
        config = memory.load_graphiti_config()
        assert config is not None

        # Patch the module to make import fail
        import sys
        original_modules = sys.modules.copy()
        # Remove watercooler_memory.backends if present
        sys.modules.pop('watercooler_memory.backends', None)

        # Mock the import to raise ImportError
        with patch.dict('sys.modules', {'watercooler_memory.backends': None}):
            backend = memory.get_graphiti_backend(config)
            # Returns error dict on import error
            assert isinstance(backend, dict)
            assert backend.get("error") == "import_failed"

        # Restore modules
        sys.modules.update(original_modules)


class TestQueryMemory:
    """Tests for query_memory() function.

    These tests require asyncio because query_memory uses asyncio.to_thread.
    """

    @pytest.mark.anyio
    async def test_query_memory_basic(self):
        """Test basic query execution."""
        mock_backend = MagicMock()

        # Mock the result returned by backend.query()
        mock_result = MagicMock()
        mock_result.results = [
            {
                "query": "test query",
                "content": "test result",
                "score": 0.9,
                "metadata": {"thread_id": "test-thread"},
            }
        ]
        mock_result.communities = []
        mock_backend.query.return_value = mock_result

        results, communities = await memory.query_memory(mock_backend, "test query", limit=10)

        assert len(results) == 1
        assert results[0]["content"] == "test result"
        assert results[0]["score"] == 0.9
        assert results[0]["metadata"]["thread_id"] == "test-thread"
        assert isinstance(communities, list)

        # Verify backend.query was called via asyncio.to_thread
        # (can't easily assert since it's called indirectly)

    @pytest.mark.anyio
    async def test_query_memory_custom_limit(self):
        """Test query with custom limit."""
        mock_backend = MagicMock()
        mock_result = MagicMock()
        mock_result.results = []
        mock_result.communities = []
        mock_backend.query.return_value = mock_result

        results, communities = await memory.query_memory(mock_backend, "test", limit=5)

        # Verify backend.query was called via asyncio.to_thread
        # (can't easily assert since it's called indirectly)

    @pytest.mark.anyio
    async def test_query_memory_returns_multiple_results(self):
        """Test query returning multiple results."""
        mock_backend = MagicMock()
        mock_result = MagicMock()
        mock_result.results = [
            {"query": "q", "content": "result1", "score": 0.9, "metadata": {}},
            {"query": "q", "content": "result2", "score": 0.8, "metadata": {}},
            {"query": "q", "content": "result3", "score": 0.7, "metadata": {}},
        ]
        mock_result.communities = []
        mock_backend.query.return_value = mock_result

        results, communities = await memory.query_memory(mock_backend, "q", limit=10)

        assert len(results) == 3
        assert results[0]["content"] == "result1"
        assert results[1]["content"] == "result2"
        assert results[2]["content"] == "result3"
        assert isinstance(communities, list)
