"""Memory backend integration for MCP server.

Provides lazy-loading of Graphiti memory backend with graceful degradation.
Follows MCP server patterns for configuration, observability, and error handling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .observability import log_debug, log_warning


@dataclass
class GraphitiConfig:
    """Configuration for Graphiti memory backend."""

    enabled: bool
    openai_api_key: str


def load_graphiti_config() -> Optional[GraphitiConfig]:
    """Load Graphiti configuration from environment variables.

    Returns None if Graphiti is disabled or configuration is invalid.
    Logs warnings for configuration issues.

    Environment Variables:
        WATERCOOLER_GRAPHITI_ENABLED: "1" to enable (default: "0")
        OPENAI_API_KEY: OpenAI API key (required if enabled)
        WATERCOOLER_GRAPHITI_RERANKER: Reranker algorithm (default: "rrf")
            Options: rrf, mmr, cross_encoder, node_distance, episode_mentions

    Returns:
        GraphitiConfig instance or None if disabled/invalid

    Example:
        >>> config = load_graphiti_config()
        >>> if config:
        ...     backend = get_graphiti_backend(config)
    """
    # Check master switch (default: disabled)
    enabled = os.getenv("WATERCOOLER_GRAPHITI_ENABLED", "0") == "1"
    if not enabled:
        log_debug("MEMORY: Graphiti disabled (WATERCOOLER_GRAPHITI_ENABLED != '1')")
        return None

    # OpenAI API key is required
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_api_key:
        log_warning(
            "MEMORY: Graphiti enabled but OPENAI_API_KEY not set. "
            "Memory queries will fail."
        )
        return None

    # Get reranker algorithm (default: rrf for speed)
    reranker = os.getenv("WATERCOOLER_GRAPHITI_RERANKER", "rrf").lower()

    return GraphitiConfig(
        openai_api_key=openai_api_key,
        reranker=reranker,
    )


def get_graphiti_backend(config: GraphitiConfig) -> Any:
    """Lazy-load and initialize Graphiti backend.

    Args:
        config: GraphitiConfig instance from load_graphiti_config()

    Returns:
        GraphitiBackend instance or None if dependencies unavailable

    Raises:
        ImportError: If watercooler_memory.backends not installed

    Example:
        >>> config = load_graphiti_config()
        >>> if config:
        ...     backend = get_graphiti_backend(config)
        ...     if backend:
        ...         results = query_memory(backend, "test query", limit=10)
    """
    try:
        from watercooler_memory.backends import GraphitiBackend  # type: ignore[attr-defined]
        from watercooler_memory.backends.graphiti import (  # type: ignore[import-not-found]
            GraphitiConfig as BackendConfig,
        )
    except ImportError as e:
        # Add path and Python version diagnostics
        import sys
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

        # Try to get package path, but guard against watercooler_memory itself being missing
        package_path = "unknown"
        try:
            import watercooler_memory
            package_path = watercooler_memory.__file__
        except ImportError:
            # watercooler_memory itself is missing - keep original error
            pass

        error_msg = (
            f"MEMORY: Graphiti backend unavailable: {e}\n"
            f"Python version: {python_version}\n"
            f"Package loaded from: {package_path}\n"
            f"Expected source path: {Path(__file__).parent.parent.parent}/src\n"
            f"Fix: Ensure MCP server uses correct Python environment"
        )
        log_warning(error_msg)
        return {
            "error": "import_failed",
            "details": str(e),
            "package_path": package_path,
            "python_version": python_version,
        }

    # Use backend defaults with env var overrides for FalkorDB settings
    # Backend GraphitiConfig provides defaults for graphiti_path, work_dir, model, etc.
    # We only override what's needed: API key and optionally FalkorDB connection
    backend_config = BackendConfig(
        openai_api_key=config.openai_api_key,
        reranker=config.reranker,
        falkordb_host=os.getenv("FALKORDB_HOST", "localhost"),
        falkordb_port=int(os.getenv("FALKORDB_PORT", "6379")),
        falkordb_password=os.getenv("FALKORDB_PASSWORD") or None,
    )

    try:
        backend = GraphitiBackend(backend_config)
        log_debug(
            f"MEMORY: Initialized Graphiti backend "
            f"(work_dir={backend_config.work_dir})"
        )
        return backend
    except Exception as e:
        import sys
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        error_msg = f"MEMORY: Failed to initialize Graphiti backend: {e}"
        log_warning(error_msg)
        return {
            "error": "init_failed",
            "details": str(e),
            "python_version": python_version,
            "backend_config": str(backend_config),
        }


async def query_memory(
    backend: Any,
    query_text: str,
    limit: int = 10,
    topic: Optional[str] = None,
) -> Sequence[Mapping[str, Any]]:
    """Execute memory query against Graphiti backend.

    Args:
        backend: GraphitiBackend instance
        query_text: Search query string
        limit: Maximum results to return (1-50)
        topic: Optional thread topic to filter by (will be converted to group_id)
              If None, searches across ALL indexed threads.

    Returns:
        List of result dictionaries with keys: query, content, score, metadata

    Raises:
        Exception: For query execution failures

    Example:
        >>> backend = get_graphiti_backend(config)
        >>> results = await query_memory(backend, "What auth was implemented?", limit=5)
        >>> for result in results:
        ...     print(f"{result['content']} (score: {result['score']})")
    """
    from watercooler_memory.backends import QueryPayload

    # Build query dict
    query_dict: dict[str, Any] = {
        "query": query_text,
        "limit": limit,
    }

    # Add topic for group_id filtering
    # Note: If topic is None, backend will search across all available graphs
    if topic:
        query_dict["topic"] = topic

    payload = QueryPayload(
        manifest_version="1.0",
        queries=[query_dict],
    )

    result = await backend.query(payload)
    return result.results
