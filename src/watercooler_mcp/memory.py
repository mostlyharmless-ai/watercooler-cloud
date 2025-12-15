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

    return GraphitiConfig(
        enabled=enabled,
        openai_api_key=openai_api_key,
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
        log_warning(
            f"MEMORY: Graphiti backend unavailable: {e}. "
            "Install with: pip install watercooler-cloud[memory]"
        )
        return None

    # Use hardcoded defaults for all configuration
    backend_config = BackendConfig(
        graphiti_path=Path("external/graphiti"),
        falkordb_host="localhost",
        falkordb_port=6379,
        openai_api_key=config.openai_api_key,
        openai_api_base=None,
        openai_model="gpt-4o-mini",
        work_dir=Path.home() / ".watercooler" / "graphiti",
    )

    try:
        backend = GraphitiBackend(backend_config)
        log_debug(
            f"MEMORY: Initialized Graphiti backend "
            f"(work_dir={backend_config.work_dir})"
        )
        return backend
    except Exception as e:
        log_warning(f"MEMORY: Failed to initialize Graphiti backend: {e}")
        return None


def query_memory(
    backend: Any,
    query_text: str,
    limit: int = 10,
) -> Sequence[Mapping[str, Any]]:
    """Execute memory query against Graphiti backend.

    Args:
        backend: GraphitiBackend instance
        query_text: Search query string
        limit: Maximum results to return (1-50)

    Returns:
        List of result dictionaries with keys: query, content, score, metadata

    Raises:
        Exception: For query execution failures

    Example:
        >>> backend = get_graphiti_backend(config)
        >>> results = query_memory(backend, "What auth was implemented?", limit=5)
        >>> for result in results:
        ...     print(f"{result['content']} (score: {result['score']})")
    """
    from watercooler_memory.backends import QueryPayload

    payload = QueryPayload(
        manifest_version="1.0",
        queries=[{"query": query_text, "limit": limit}],
    )

    result = backend.query(payload)
    return result.results
