"""Memory backend integration for MCP server.

Provides lazy-loading of Graphiti memory backend with graceful degradation.
Follows MCP server patterns for configuration, observability, and error handling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .observability import log_debug, log_error, log_warning


@dataclass
class GraphitiConfig:
    """Configuration for Graphiti memory backend."""

    enabled: bool
    graphiti_path: Path
    work_dir: Path
    falkordb_host: str
    falkordb_port: int
    openai_api_key: str
    openai_api_base: Optional[str]
    openai_model: str
    strict_mode: bool  # If True, raise errors; if False, return None on failures


def load_graphiti_config() -> Optional[GraphitiConfig]:
    """Load Graphiti configuration from environment variables.

    Returns None if Graphiti is disabled or configuration is invalid.
    Logs warnings for configuration issues.

    Environment Variables:
        WATERCOOLER_GRAPHITI_ENABLED: "1" to enable (default: "0")
        WATERCOOLER_GRAPHITI_PATH: Path to graphiti submodule (default: external/graphiti)
        WATERCOOLER_GRAPHITI_WORK_DIR: Index storage directory (default: ~/.watercooler/graphiti)
        WATERCOOLER_GRAPHITI_FALKORDB_HOST: FalkorDB host (default: localhost)
        WATERCOOLER_GRAPHITI_FALKORDB_PORT: FalkorDB port (default: 6379)
        WATERCOOLER_GRAPHITI_OPENAI_API_KEY: OpenAI API key (required if enabled)
        WATERCOOLER_GRAPHITI_OPENAI_API_BASE: Custom API base URL (optional)
        WATERCOOLER_GRAPHITI_OPENAI_MODEL: Model name (default: gpt-4o-mini)
        WATERCOOLER_GRAPHITI_STRICT_MODE: "1" for strict mode (default: "0")

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

    # Load configuration with defaults
    graphiti_path_str = os.getenv("WATERCOOLER_GRAPHITI_PATH", "external/graphiti")
    graphiti_path = Path(graphiti_path_str).expanduser().resolve()

    work_dir_str = os.getenv(
        "WATERCOOLER_GRAPHITI_WORK_DIR",
        str(Path.home() / ".watercooler" / "graphiti"),
    )
    work_dir = Path(work_dir_str).expanduser().resolve()

    falkordb_host = os.getenv("WATERCOOLER_GRAPHITI_FALKORDB_HOST", "localhost")

    falkordb_port_str = os.getenv("WATERCOOLER_GRAPHITI_FALKORDB_PORT", "6379")
    try:
        falkordb_port = int(falkordb_port_str)
    except ValueError:
        log_warning(
            f"MEMORY: Invalid WATERCOOLER_GRAPHITI_FALKORDB_PORT='{falkordb_port_str}', "
            "using default 6379"
        )
        falkordb_port = 6379

    # Strict mode: raise errors vs return None (check early for API key validation)
    strict_mode = os.getenv("WATERCOOLER_GRAPHITI_STRICT_MODE", "0") == "1"

    # OpenAI API key is required
    openai_api_key = os.getenv("WATERCOOLER_GRAPHITI_OPENAI_API_KEY", "")
    if not openai_api_key:
        # Fall back to OPENAI_API_KEY if not set
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        if not openai_api_key:
            msg = (
                "MEMORY: Graphiti enabled but WATERCOOLER_GRAPHITI_OPENAI_API_KEY not set. "
                "Memory queries will fail."
            )
            if strict_mode:
                log_error(msg)
                raise ValueError(
                    "WATERCOOLER_GRAPHITI_OPENAI_API_KEY or OPENAI_API_KEY required when "
                    "WATERCOOLER_GRAPHITI_ENABLED=1 and WATERCOOLER_GRAPHITI_STRICT_MODE=1"
                )
            else:
                log_warning(msg)
                return None

    openai_api_base = os.getenv("WATERCOOLER_GRAPHITI_OPENAI_API_BASE")
    openai_model = os.getenv("WATERCOOLER_GRAPHITI_OPENAI_MODEL", "gpt-4o-mini")

    return GraphitiConfig(
        enabled=enabled,
        graphiti_path=graphiti_path,
        work_dir=work_dir,
        falkordb_host=falkordb_host,
        falkordb_port=falkordb_port,
        openai_api_key=openai_api_key,
        openai_api_base=openai_api_base,
        openai_model=openai_model,
        strict_mode=strict_mode,
    )


def get_graphiti_backend(config: GraphitiConfig) -> Any:
    """Lazy-load and initialize Graphiti backend.

    Args:
        config: GraphitiConfig instance from load_graphiti_config()

    Returns:
        GraphitiBackend instance or None if dependencies unavailable

    Raises:
        ImportError: If watercooler_memory.backends not installed (strict mode)
        ConfigError: If Graphiti configuration is invalid (strict mode)

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
        msg = (
            f"MEMORY: Graphiti backend unavailable: {e}. "
            "Install with: pip install watercooler-cloud[memory]"
        )
        if config.strict_mode:
            log_error(msg)
            raise
        else:
            log_warning(msg)
            return None

    # Map MCP config to backend config
    backend_config = BackendConfig(
        graphiti_path=config.graphiti_path,
        falkordb_host=config.falkordb_host,
        falkordb_port=config.falkordb_port,
        openai_api_key=config.openai_api_key,
        openai_api_base=config.openai_api_base,
        openai_model=config.openai_model,
        work_dir=config.work_dir,
    )

    try:
        backend = GraphitiBackend(backend_config)
        log_debug(f"MEMORY: Initialized Graphiti backend (work_dir={config.work_dir})")
        return backend
    except Exception as e:
        msg = f"MEMORY: Failed to initialize Graphiti backend: {e}"
        if config.strict_mode:
            log_error(msg)
            raise
        else:
            log_warning(msg)
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
