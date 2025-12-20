# Memory Backend Abstraction Refactoring Plan

**Author:** Cascade (AI Assistant)  
**Date:** 2025-12-19  
**Status:** Draft for Team Review  

---

## Executive Summary

The current MCP server (`watercooler_mcp/server.py`) contains ~700 lines of memory tool implementations that are tightly coupled to the Graphiti backend. This makes it impossible to swap memory systems (e.g., LeanRAG, future backends) without significant MCP layer changes.

This document proposes a refactoring plan to:
1. Extend the `MemoryBackend` protocol with search operations
2. Create a unified memory service layer
3. Reduce MCP tools to thin wrappers
4. Enable backend swapping via configuration

---

## Table of Contents

1. [Current Architecture Analysis](#current-architecture-analysis)
2. [Problem Statement](#problem-statement)
3. [Proposed Architecture](#proposed-architecture)
4. [Implementation Phases](#implementation-phases)
5. [File Changes Summary](#file-changes-summary)
6. [Migration Strategy](#migration-strategy)
7. [Open Questions for Team](#open-questions-for-team)

---

## Current Architecture Analysis

### What's Already Abstracted (Good)

The `GraphitiBackend` class in `backends/graphiti.py` already implements Graphiti-specific search methods:

| Method | Lines | Description |
|--------|-------|-------------|
| `search_nodes()` | 951-1037 | Node search with hybrid semantic |
| `get_entity_edge()` | 1039-1093 | Edge retrieval by UUID |
| `search_memory_facts()` | 1095-1170 | Fact/edge search |
| `get_episodes()` | 1172-1252 | Episode search |

These methods are **already in the backend layer**, which is the correct location.

### The `MemoryBackend` Protocol (Current)

Located in `backends/__init__.py`, the protocol defines only 5 methods:

```python
class MemoryBackend(Protocol):
    def prepare(self, corpus: CorpusPayload) -> PrepareResult: ...
    def index(self, chunks: ChunkPayload) -> IndexResult: ...
    def query(self, query: QueryPayload) -> QueryResult: ...
    def healthcheck(self) -> HealthStatus: ...
    def get_capabilities(self) -> Capabilities: ...
```

The search methods (`search_nodes`, `get_entity_edge`, etc.) are **not part of the protocol**.

### MCP Server Memory Tools (Current)

Located in `watercooler_mcp/server.py` (lines 2850-3700+):

| Tool | Lines | Description |
|------|-------|-------------|
| `watercooler_query_memory` | ~2800-3032 | General memory query |
| `watercooler_search_nodes` | ~3037-3185 | Node search |
| `watercooler_get_entity_edge` | ~3188-3313 | Edge retrieval |
| `watercooler_search_memory_facts` | ~3316-3474 | Fact search |
| `watercooler_get_episodes` | ~3477-3620 | Episode search |
| `diagnose_memory` | ~3625-3700+ | Diagnostics |

### MCP Memory Module (Current)

Located in `watercooler_mcp/memory.py` (304 lines):

- `load_graphiti_config()` - Loads Graphiti-specific config from env vars
- `get_graphiti_backend()` - Initializes GraphitiBackend
- `query_memory()` - Executes query via backend
- `validate_memory_prerequisites()` - Common validation
- `create_error_response()` - Error formatting

---

## Problem Statement

### 1. Protocol Incompleteness

The `MemoryBackend` protocol doesn't include search operations. MCP tools call methods that only exist on `GraphitiBackend`:

```python
# In server.py - calls Graphiti-specific method
results = await asyncio.to_thread(backend.search_nodes, query=query, ...)
```

If we swap to `LeanRAGBackend`, this call fails because `search_nodes()` doesn't exist.

### 2. Hardcoded Configuration

`memory.py` hardcodes Graphiti configuration:

```python
def load_graphiti_config() -> Optional[GraphitiConfig]:
    enabled = os.getenv("WATERCOOLER_GRAPHITI_ENABLED", "0") == "1"
    # ... Graphiti-specific logic
```

No mechanism to select a different backend.

### 3. Duplicated Validation Logic

Each MCP tool repeats ~50-100 lines of:
- Import memory module
- Load config
- Validate backend
- Handle errors
- Format response

### 4. Response Format Coupling

MCP tools format Graphiti-specific response structures (episodes, nodes, edges with UUIDs, group_ids, etc.). Other backends may have different data models.

---

## Proposed Architecture

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Tools (server.py)                    │
│  watercooler_query_memory, watercooler_search_nodes, etc.   │
│                    ~150 lines (thin wrappers)               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Memory Service Layer                        │
│              (watercooler_mcp/memory_service.py)            │
│  - Backend selection via registry                           │
│  - Unified validation & error handling                      │
│  - Async wrapper for sync backends                          │
│  - Response normalization                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  MemoryBackend Protocol                      │
│                  (backends/__init__.py)                      │
│  prepare(), index(), query(), healthcheck()                 │
│  + NEW: search_nodes(), search_facts(), search_episodes()   │
│  + NEW: get_edge(), get_node()                              │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ GraphitiBackend │ │ LeanRAGBackend  │ │   NullBackend   │
│  (graphiti.py)  │ │  (leanrag.py)   │ │   (null.py)     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Design Principles

1. **Protocol-First**: All operations go through `MemoryBackend` protocol
2. **Backend-Agnostic Service**: MCP layer doesn't know which backend is active
3. **Registry-Based Selection**: Backend chosen via `WATERCOOLER_MEMORY_BACKEND` env var
4. **Graceful Degradation**: Missing capabilities return empty results, not errors
5. **Normalized Responses**: Service layer normalizes backend-specific formats

---

## Implementation Phases

### Phase 1: Extend `MemoryBackend` Protocol

**File:** `backends/__init__.py`

Add new abstract methods to the protocol:

```python
@runtime_checkable
class MemoryBackend(Protocol):
    # Existing methods
    def prepare(self, corpus: CorpusPayload) -> PrepareResult: ...
    def index(self, chunks: ChunkPayload) -> IndexResult: ...
    def query(self, query: QueryPayload) -> QueryResult: ...
    def healthcheck(self) -> HealthStatus: ...
    def get_capabilities(self) -> Capabilities: ...
    
    # NEW: Search operations
    def search_nodes(
        self,
        query: str,
        group_ids: list[str] | None = None,
        max_results: int = 10,
        entity_types: list[str] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        """Search for entity nodes using semantic search.
        
        Args:
            query: Search query string
            group_ids: Optional list of group/thread IDs to filter by
            max_results: Maximum results to return (1-50)
            entity_types: Optional list of entity type labels to filter
            
        Returns:
            List of node dicts with at minimum:
            - id: Unique identifier
            - name: Node name/label
            - summary: Optional summary text
            - score: Relevance score (0.0-1.0)
        """
        ...
    
    def search_facts(
        self,
        query: str,
        group_ids: list[str] | None = None,
        max_results: int = 10,
        center_node_id: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        """Search for facts/relationships between entities.
        
        Args:
            query: Search query string
            group_ids: Optional list of group/thread IDs to filter by
            max_results: Maximum results to return (1-50)
            center_node_id: Optional node ID to center search around
            
        Returns:
            List of fact dicts with at minimum:
            - id: Unique identifier
            - fact: Fact/relationship text
            - source_node_id: Source entity ID
            - target_node_id: Target entity ID
            - score: Relevance score (0.0-1.0)
        """
        ...
    
    def search_episodes(
        self,
        query: str,
        group_ids: list[str] | None = None,
        max_results: int = 10,
    ) -> Sequence[Mapping[str, Any]]:
        """Search for episodes (source content).
        
        Args:
            query: Search query string
            group_ids: Optional list of group/thread IDs to filter by
            max_results: Maximum results to return (1-50)
            
        Returns:
            List of episode dicts with at minimum:
            - id: Unique identifier
            - name: Episode name/title
            - content: Episode content (may be truncated)
            - score: Relevance score (0.0-1.0)
        """
        ...
    
    def get_edge(
        self,
        edge_id: str,
        group_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Get a specific edge/relationship by ID.
        
        Args:
            edge_id: Edge unique identifier
            group_id: Optional group/thread ID for multi-database setups
            
        Returns:
            Edge dict or None if not found
        """
        ...
    
    def get_node(
        self,
        node_id: str,
        group_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Get a specific node by ID.
        
        Args:
            node_id: Node unique identifier
            group_id: Optional group/thread ID for multi-database setups
            
        Returns:
            Node dict or None if not found
        """
        ...
```

**Rationale for naming changes:**
- `search_memory_facts` → `search_facts` (simpler, matches pattern)
- `get_entity_edge` → `get_edge` (simpler)
- `uuid` → `id` (backend-agnostic, not all backends use UUIDs)
- `max_nodes/max_facts/max_episodes` → `max_results` (consistent)

### Phase 2: Update `GraphitiBackend`

**File:** `backends/graphiti.py`

Rename methods to match protocol (keep old names as aliases for backwards compatibility):

```python
class GraphitiBackend(MemoryBackend):
    # Rename to match protocol
    def search_facts(self, query: str, ...) -> list[dict[str, Any]]:
        """Search for facts (edges) with optional center-node traversal."""
        # Existing implementation from search_memory_facts()
        ...
    
    # Backwards compatibility alias
    search_memory_facts = search_facts
    
    def get_edge(self, edge_id: str, group_id: str | None = None) -> dict[str, Any]:
        """Get an entity edge by ID."""
        # Existing implementation from get_entity_edge()
        ...
    
    # Backwards compatibility alias  
    get_entity_edge = get_edge
    
    def search_episodes(self, query: str, ...) -> list[dict[str, Any]]:
        """Search for episodes."""
        # Existing implementation from get_episodes()
        ...
    
    # Backwards compatibility alias
    get_episodes = search_episodes
    
    def get_node(self, node_id: str, group_id: str | None = None) -> dict[str, Any] | None:
        """Get a specific node by ID."""
        # NEW: Implement node retrieval
        ...
```

**Response normalization:** Ensure returned dicts use `id` key (can include `uuid` as alias):

```python
return {
    "id": edge.uuid,      # Protocol-standard key
    "uuid": edge.uuid,    # Graphiti-specific alias
    "fact": edge.fact,
    ...
}
```

### Phase 3: Implement in `LeanRAGBackend`

**File:** `backends/leanrag.py`

Implement new protocol methods using LeanRAG's capabilities:

```python
class LeanRAGBackend(MemoryBackend):
    def search_nodes(self, query: str, ...) -> list[dict[str, Any]]:
        """Search for nodes using LeanRAG's entity index."""
        # Implementation using LeanRAG's vector search
        ...
    
    def search_facts(self, query: str, ...) -> list[dict[str, Any]]:
        """Search for facts/relationships."""
        # LeanRAG may not have explicit facts - return empty or use chunk search
        return []
    
    def search_episodes(self, query: str, ...) -> list[dict[str, Any]]:
        """Search for episodes (chunks in LeanRAG)."""
        # Map LeanRAG chunks to episode format
        ...
    
    def get_edge(self, edge_id: str, ...) -> dict[str, Any] | None:
        """LeanRAG doesn't have explicit edges."""
        return None
    
    def get_node(self, node_id: str, ...) -> dict[str, Any] | None:
        """Get node from LeanRAG entity index."""
        ...
```

### Phase 4: Implement in `NullBackend`

**File:** `backends/null.py`

Stub implementations returning empty results:

```python
class NullBackend(MemoryBackend):
    def search_nodes(self, query: str, **kwargs) -> list[dict[str, Any]]:
        return []
    
    def search_facts(self, query: str, **kwargs) -> list[dict[str, Any]]:
        return []
    
    def search_episodes(self, query: str, **kwargs) -> list[dict[str, Any]]:
        return []
    
    def get_edge(self, edge_id: str, **kwargs) -> dict[str, Any] | None:
        return None
    
    def get_node(self, node_id: str, **kwargs) -> dict[str, Any] | None:
        return None
```

### Phase 5: Create Memory Service Layer

**File:** `watercooler_mcp/memory_service.py` (NEW)

```python
"""Unified memory service abstracting backend selection.

This module provides a backend-agnostic interface for MCP memory tools.
Backend selection is controlled via WATERCOOLER_MEMORY_BACKEND env var.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Mapping, Optional, Sequence

from watercooler_memory.backends import (
    MemoryBackend,
    resolve_backend,
    HealthStatus,
    Capabilities,
)

from .observability import log_debug, log_warning, log_error, log_action


class MemoryService:
    """Backend-agnostic memory service for MCP tools.
    
    Provides:
    - Lazy backend initialization
    - Unified validation and error handling
    - Async wrappers for sync backend methods
    - Response normalization
    
    Usage:
        service = MemoryService()
        nodes = await service.search_nodes("authentication", max_results=10)
    """
    
    _instance: Optional["MemoryService"] = None
    
    def __init__(self):
        self._backend: MemoryBackend | None = None
        self._backend_name: str | None = None
        self._init_error: str | None = None
    
    @classmethod
    def get_instance(cls) -> "MemoryService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_backend(self) -> tuple[MemoryBackend | None, str | None]:
        """Lazy-load configured backend.
        
        Returns:
            Tuple of (backend, error_message)
            - (backend, None) if successful
            - (None, error_message) if failed
        """
        if self._init_error:
            return None, self._init_error
        
        if self._backend is not None:
            return self._backend, None
        
        # Determine backend from environment
        backend_name = os.getenv("WATERCOOLER_MEMORY_BACKEND", "graphiti")
        
        # Check if memory is enabled
        enabled_var = f"WATERCOOLER_{backend_name.upper()}_ENABLED"
        if os.getenv(enabled_var, "0") != "1":
            self._init_error = (
                f"Memory backend '{backend_name}' not enabled. "
                f"Set {enabled_var}=1 to enable."
            )
            return None, self._init_error
        
        try:
            self._backend = resolve_backend(backend_name)
            self._backend_name = backend_name
            log_debug(f"MEMORY: Initialized {backend_name} backend")
            return self._backend, None
        except Exception as e:
            self._init_error = f"Failed to initialize {backend_name}: {e}"
            log_error(self._init_error)
            return None, self._init_error
    
    def reset(self) -> None:
        """Reset backend (for testing or reconfiguration)."""
        self._backend = None
        self._backend_name = None
        self._init_error = None
    
    async def healthcheck(self) -> HealthStatus:
        """Check backend health."""
        backend, error = self.get_backend()
        if error:
            return HealthStatus(ok=False, details=error)
        return await asyncio.to_thread(backend.healthcheck)
    
    async def get_capabilities(self) -> Capabilities | None:
        """Get backend capabilities."""
        backend, error = self.get_backend()
        if error:
            return None
        return await asyncio.to_thread(backend.get_capabilities)
    
    async def search_nodes(
        self,
        query: str,
        group_ids: list[str] | None = None,
        max_results: int = 10,
        entity_types: list[str] | None = None,
    ) -> tuple[Sequence[Mapping[str, Any]], str | None]:
        """Search for entity nodes.
        
        Returns:
            Tuple of (results, error_message)
        """
        backend, error = self.get_backend()
        if error:
            return [], error
        
        log_action("memory.search_nodes", query=query, max_results=max_results)
        
        try:
            results = await asyncio.to_thread(
                backend.search_nodes,
                query=query,
                group_ids=group_ids,
                max_results=max_results,
                entity_types=entity_types,
            )
            return results, None
        except Exception as e:
            log_error(f"MEMORY: search_nodes failed: {e}")
            return [], str(e)
    
    async def search_facts(
        self,
        query: str,
        group_ids: list[str] | None = None,
        max_results: int = 10,
        center_node_id: str | None = None,
    ) -> tuple[Sequence[Mapping[str, Any]], str | None]:
        """Search for facts/relationships."""
        backend, error = self.get_backend()
        if error:
            return [], error
        
        log_action("memory.search_facts", query=query, max_results=max_results)
        
        try:
            results = await asyncio.to_thread(
                backend.search_facts,
                query=query,
                group_ids=group_ids,
                max_results=max_results,
                center_node_id=center_node_id,
            )
            return results, None
        except Exception as e:
            log_error(f"MEMORY: search_facts failed: {e}")
            return [], str(e)
    
    async def search_episodes(
        self,
        query: str,
        group_ids: list[str] | None = None,
        max_results: int = 10,
    ) -> tuple[Sequence[Mapping[str, Any]], str | None]:
        """Search for episodes."""
        backend, error = self.get_backend()
        if error:
            return [], error
        
        log_action("memory.search_episodes", query=query, max_results=max_results)
        
        try:
            results = await asyncio.to_thread(
                backend.search_episodes,
                query=query,
                group_ids=group_ids,
                max_results=max_results,
            )
            return results, None
        except Exception as e:
            log_error(f"MEMORY: search_episodes failed: {e}")
            return [], str(e)
    
    async def get_edge(
        self,
        edge_id: str,
        group_id: str | None = None,
    ) -> tuple[Mapping[str, Any] | None, str | None]:
        """Get a specific edge by ID."""
        backend, error = self.get_backend()
        if error:
            return None, error
        
        log_action("memory.get_edge", edge_id=edge_id)
        
        try:
            result = await asyncio.to_thread(
                backend.get_edge,
                edge_id=edge_id,
                group_id=group_id,
            )
            return result, None
        except Exception as e:
            log_error(f"MEMORY: get_edge failed: {e}")
            return None, str(e)
    
    async def query(
        self,
        query_text: str,
        limit: int = 10,
        topic: str | None = None,
    ) -> tuple[Sequence[Mapping[str, Any]], Sequence[Mapping[str, Any]], str | None]:
        """Execute general memory query.
        
        Returns:
            Tuple of (results, communities, error_message)
        """
        backend, error = self.get_backend()
        if error:
            return [], [], error
        
        log_action("memory.query", query=query_text, limit=limit, topic=topic)
        
        try:
            from watercooler_memory.backends import QueryPayload
            
            query_dict: dict[str, Any] = {"query": query_text, "limit": limit}
            if topic:
                query_dict["topic"] = topic
            
            payload = QueryPayload(
                manifest_version="1.0",
                queries=[query_dict],
            )
            
            result = await asyncio.to_thread(backend.query, payload)
            return result.results, result.communities, None
        except Exception as e:
            log_error(f"MEMORY: query failed: {e}")
            return [], [], str(e)


def get_memory_service() -> MemoryService:
    """Get the singleton memory service instance."""
    return MemoryService.get_instance()
```

### Phase 6: Simplify MCP Tools

**File:** `watercooler_mcp/server.py`

Replace ~700 lines with thin wrappers (~150 lines total):

```python
import json
from typing import List, Optional

from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from .memory_service import get_memory_service


def _format_response(data: dict) -> ToolResult:
    """Format dict as JSON ToolResult."""
    return ToolResult(content=[TextContent(
        type="text",
        text=json.dumps(data, indent=2)
    )])


def _format_error(error: str, operation: str, **kwargs) -> ToolResult:
    """Format error response."""
    return _format_response({
        "error": error,
        "operation": operation,
        **kwargs,
    })


@mcp.tool(name="watercooler_query_memory")
async def query_memory(
    query: str,
    ctx: Context,
    code_path: str = "",
    limit: int = 10,
    topic: Optional[str] = None,
) -> ToolResult:
    """Query memory for relevant information."""
    if not query or not query.strip():
        return _format_error("Invalid query", "query_memory", query=query)
    
    limit = max(1, min(limit, 50))
    
    service = get_memory_service()
    results, communities, error = await service.query(query, limit, topic)
    
    if error:
        return _format_error(error, "query_memory", query=query)
    
    return _format_response({
        "query": query,
        "result_count": len(results),
        "results": list(results),
        "communities": list(communities),
        "message": f"Found {len(results)} results",
    })


@mcp.tool(name="watercooler_search_nodes")
async def search_nodes(
    query: str,
    ctx: Context,
    code_path: str = "",
    group_ids: Optional[List[str]] = None,
    max_nodes: int = 10,
    entity_types: Optional[List[str]] = None,
) -> ToolResult:
    """Search for entity nodes."""
    if not query or not query.strip():
        return _format_error("Invalid query", "search_nodes", query=query)
    
    max_nodes = max(1, min(max_nodes, 50))
    
    service = get_memory_service()
    results, error = await service.search_nodes(
        query, group_ids, max_nodes, entity_types
    )
    
    if error:
        return _format_error(error, "search_nodes", query=query)
    
    return _format_response({
        "query": query,
        "result_count": len(results),
        "results": list(results),
        "message": f"Found {len(results)} node(s)",
    })


@mcp.tool(name="watercooler_get_entity_edge")
async def get_entity_edge(
    uuid: str,
    ctx: Context,
    code_path: str = "",
    group_id: Optional[str] = None,
) -> ToolResult:
    """Get a specific entity edge by UUID."""
    if not uuid or not uuid.strip():
        return _format_error("Invalid UUID", "get_entity_edge")
    
    if len(uuid) > 100:
        return _format_error("UUID too long", "get_entity_edge")
    
    service = get_memory_service()
    edge, error = await service.get_edge(uuid, group_id)
    
    if error:
        return _format_error(error, "get_entity_edge", uuid=uuid)
    
    if edge is None:
        return _format_error("Edge not found", "get_entity_edge", uuid=uuid)
    
    return _format_response({
        **edge,
        "message": f"Retrieved edge {uuid}",
    })


@mcp.tool(name="watercooler_search_memory_facts")
async def search_memory_facts(
    query: str,
    ctx: Context,
    code_path: str = "",
    group_ids: Optional[List[str]] = None,
    max_facts: int = 10,
    center_node_uuid: Optional[str] = None,
) -> ToolResult:
    """Search for facts/relationships."""
    if not query or not query.strip():
        return _format_error("Invalid query", "search_memory_facts", query=query)
    
    max_facts = max(1, min(max_facts, 50))
    
    service = get_memory_service()
    results, error = await service.search_facts(
        query, group_ids, max_facts, center_node_uuid
    )
    
    if error:
        return _format_error(error, "search_memory_facts", query=query)
    
    return _format_response({
        "query": query,
        "result_count": len(results),
        "results": list(results),
        "message": f"Found {len(results)} fact(s)",
    })


@mcp.tool(name="watercooler_get_episodes")
async def get_episodes(
    query: str,
    ctx: Context,
    code_path: str = "",
    group_ids: Optional[List[str]] = None,
    max_episodes: int = 10,
) -> ToolResult:
    """Search for episodes."""
    if not query or not query.strip():
        return _format_error("Invalid query", "get_episodes")
    
    max_episodes = max(1, min(max_episodes, 50))
    
    service = get_memory_service()
    results, error = await service.search_episodes(query, group_ids, max_episodes)
    
    if error:
        return _format_error(error, "get_episodes", query=query)
    
    return _format_response({
        "result_count": len(results),
        "results": list(results),
        "message": f"Found {len(results)} episode(s)",
    })
```

### Phase 7: Update Registry

**File:** `backends/registry.py`

Ensure `resolve_backend()` supports all backends:

```python
def resolve_backend(name: str | None = None) -> MemoryBackend:
    """Resolve backend by name or from environment.
    
    Args:
        name: Backend name (graphiti, leanrag, null)
              If None, reads from WATERCOOLER_MEMORY_BACKEND env var
    
    Returns:
        Initialized MemoryBackend instance
    
    Raises:
        ConfigError: If backend not found or initialization fails
    """
    name = name or os.getenv("WATERCOOLER_MEMORY_BACKEND", "graphiti")
    
    # Auto-register builtins if needed
    auto_register_builtin()
    
    return get_backend(name)
```

---

## File Changes Summary

| File | Action | Lines Changed |
|------|--------|---------------|
| `backends/__init__.py` | Add 5 new protocol methods | +80 |
| `backends/graphiti.py` | Rename methods, add aliases, add `get_node()` | +50, ~20 renamed |
| `backends/leanrag.py` | Implement new protocol methods | +100 |
| `backends/null.py` | Implement stub methods | +30 |
| `backends/registry.py` | Minor updates to `resolve_backend()` | +10 |
| `watercooler_mcp/memory_service.py` | **NEW** - Unified service layer | +250 |
| `watercooler_mcp/memory.py` | Simplify or deprecate | -200 |
| `watercooler_mcp/server.py` | Replace memory tools | -550, +150 |

**Net change:** ~-300 lines (reduction in complexity)

---

## Migration Strategy

### Backwards Compatibility

1. **Keep old method names as aliases** in `GraphitiBackend`:
   ```python
   search_memory_facts = search_facts
   get_entity_edge = get_edge
   get_episodes = search_episodes
   ```

2. **Keep old env vars working**:
   - `WATERCOOLER_GRAPHITI_ENABLED=1` continues to work
   - New: `WATERCOOLER_MEMORY_BACKEND=graphiti` (optional, defaults to graphiti)

3. **Keep old response fields**:
   - Include both `id` and `uuid` in responses
   - Include both `max_results` and `max_nodes/max_facts/max_episodes`

### Incremental Rollout

1. **Phase 1-4**: Backend changes (no MCP impact)
2. **Phase 5**: Add `memory_service.py` alongside existing `memory.py`
3. **Phase 6**: Migrate one tool at a time, test each
4. **Phase 7**: Remove old `memory.py` after all tools migrated

### Feature Flag

```bash
# Use new service layer (default after migration)
WATERCOOLER_MEMORY_SERVICE=new

# Use old memory.py (fallback during migration)
WATERCOOLER_MEMORY_SERVICE=legacy
```

---

## Open Questions for Team

### 1. Protocol Method Naming

Should we use:
- `search_facts()` or `search_relationships()`?
- `get_edge()` or `get_relationship()`?
- `id` or keep backend-specific names (`uuid`, `entry_id`)?

### 2. LeanRAG Capabilities

What should `LeanRAGBackend` return for:
- `search_facts()` - LeanRAG doesn't have explicit fact extraction
- `get_edge()` - No edge concept in LeanRAG

Options:
- Return empty results
- Raise `NotImplementedError`
- Map to closest equivalent (chunks → episodes)

### 3. Response Normalization

Should the service layer normalize all responses to a common format, or preserve backend-specific fields?

**Option A: Strict normalization**
```python
{
    "id": "...",
    "name": "...",
    "content": "...",
    "score": 0.85,
}
```

**Option B: Preserve backend fields**
```python
{
    "id": "...",
    "uuid": "...",  # Graphiti-specific
    "name": "...",
    "content": "...",
    "score": 0.85,
    "group_id": "...",  # Graphiti-specific
    "valid_at": "...",  # Graphiti-specific
}
```

### 4. Deprecation Timeline

When should we:
- Deprecate old method names (`search_memory_facts`, `get_entity_edge`)?
- Remove `watercooler_mcp/memory.py`?
- Remove backwards compatibility aliases?

### 5. Testing Strategy

How should we test backend swapping?
- Unit tests with `NullBackend`?
- Integration tests with both Graphiti and LeanRAG?
- Mock-based tests for MCP layer?

---

## Appendix: Current File Locations

```
src/
├── watercooler_memory/
│   └── backends/
│       ├── __init__.py      # MemoryBackend protocol
│       ├── graphiti.py      # GraphitiBackend (1318 lines)
│       ├── leanrag.py       # LeanRAGBackend (16440 bytes)
│       ├── null.py          # NullBackend (2071 bytes)
│       └── registry.py      # Backend registry (2078 bytes)
│
└── watercooler_mcp/
    ├── server.py            # MCP server with memory tools (~3786 lines)
    ├── memory.py            # Graphiti-specific helpers (304 lines)
    └── observability.py     # Logging utilities
```

---

## References

- `MemoryBackend` Protocol: `backends/__init__.py:106-263`
- `GraphitiBackend` search methods: `backends/graphiti.py:951-1252`
- MCP memory tools: `watercooler_mcp/server.py:2850-3700+`
- Existing registry: `backends/registry.py`
