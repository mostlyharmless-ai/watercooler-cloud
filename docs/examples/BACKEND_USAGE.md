# Memory Backend Usage Examples

This guide provides practical examples for using watercooler memory backends. All backends implement the same `MemoryBackend` protocol, allowing you to swap implementations without changing application code.

## Table of Contents

1. [Installation](#installation)
2. [Basic LeanRAG Usage](#basic-leanrag-usage)
3. [Graphiti Episodic Memory](#graphiti-episodic-memory)
4. [Error Handling](#error-handling)
5. [Testing with Null Backend](#testing-with-null-backend)
6. [Full Pipeline Example](#full-pipeline-example)
7. [Common Patterns](#common-patterns)

## Installation

```bash
# Install with all backends
pip install watercooler-cloud[memory]

# Install specific backends
pip install watercooler-cloud[leanrag]   # LeanRAG only
pip install watercooler-cloud[graphiti]  # Graphiti only
```

## Basic LeanRAG Usage

LeanRAG provides hierarchical graph-based RAG with entity extraction and semantic clustering.

### Complete Example

```python
from pathlib import Path
from watercooler_memory.backends import get_backend, LeanRAGConfig
from watercooler_memory.backends import CorpusPayload, ChunkPayload, QueryPayload

# Step 1: Configure the backend
config = LeanRAGConfig(
    work_dir=Path("./memory/leanrag"),
    # Optional: set API keys if not in environment
    # deepseek_api_key="sk-...",
    # embedding_api_base="http://localhost:8080/v1",
)

# Step 2: Get backend instance
backend = get_backend("leanrag", config)

# Step 3: Check health
health = backend.healthcheck()
if not health.ok:
    print(f"Backend not healthy: {health.details}")
    exit(1)

# Step 4: Prepare corpus (parse threads and extract entities)
corpus = CorpusPayload(
    manifest_version="1.0.0",
    threads=[
        {
            "thread_id": "feature-auth",
            "title": "Authentication Feature",
            "status": "OPEN",
        }
    ],
    entries=[
        {
            "id": "entry-001",
            "thread_id": "feature-auth",
            "agent": "Claude",
            "role": "implementer",
            "entry_type": "Note",
            "timestamp": "2025-01-01T12:00:00Z",
            "title": "OAuth2 Implementation",
            "body": "Implemented OAuth2 authentication with JWT tokens...",
        },
        {
            "id": "entry-002",
            "thread_id": "feature-auth",
            "agent": "Codex",
            "role": "reviewer",
            "entry_type": "Note",
            "timestamp": "2025-01-01T14:30:00Z",
            "title": "Security Review",
            "body": "Reviewed the OAuth2 implementation. Looks good...",
        },
    ],
)

prepare_result = backend.prepare(corpus)
print(f"Prepared {prepare_result.prepared_count} entries")

# Step 5: Index chunks (build knowledge graph)
# The prepare step generates chunks that we now index
from watercooler_memory import MemoryGraph

graph = MemoryGraph()
graph.build(Path("./threads"))  # Build graph from threads
chunks_list = graph.chunk_all_entries()

chunks = ChunkPayload(
    manifest_version="1.0.0",
    chunks=chunks_list,
    threads=corpus.threads,
    entries=corpus.entries,
)

index_result = backend.index(chunks)
print(f"Indexed {index_result.indexed_count} chunks")

# Step 6: Query the knowledge graph
queries = QueryPayload(
    manifest_version="1.0.0",
    queries=[
        {"query": "What authentication method was implemented?"},
        {"query": "Who reviewed the security?"},
    ],
)

query_result = backend.query(queries)
for item in query_result.results:
    # Each item is a dict with keys: query, content, score, metadata
    print(f"Query: {item['query']}")
    print(f"Content: {item['content'][:200]}...")
    print(f"Score: {item['score']}")
    print(f"Metadata: {item.get('metadata', {})}")
    print()
```

### Quick Start (Minimal Example)

```python
from pathlib import Path
from watercooler_memory.backends import get_backend, LeanRAGConfig

# Create backend
config = LeanRAGConfig(work_dir=Path("./memory"))
backend = get_backend("leanrag", config)

# Use it (assuming corpus, chunks, queries are already prepared)
backend.prepare(corpus)
backend.index(chunks)
results = backend.query(queries)
```

## Graphiti Episodic Memory

Graphiti provides temporal episodic memory with time-aware entity tracking and hybrid search.

### Complete Example

```python
import os
from pathlib import Path
from watercooler_memory.backends import get_backend, GraphitiConfig
from watercooler_memory.backends import CorpusPayload, QueryPayload

# Step 1: Configure (requires OpenAI API key)
config = GraphitiConfig(
    work_dir=Path("./memory/graphiti"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    openai_model="gpt-4o-mini",  # Or gpt-5-mini
    test_mode=False,  # IMPORTANT: Never use test_mode in production
)

# Step 2: Get backend instance
backend = get_backend("graphiti", config)

# Step 3: Check health
health = backend.healthcheck()
print(f"Graphiti available: {health.ok}")
print(f"Details: {health.details}")

# Step 4: Prepare episodic corpus
# Each entry becomes a temporal episode in the graph
corpus = CorpusPayload(
    manifest_version="1.0.0",
    threads=[{"thread_id": "team-standup", "title": "Daily Standup"}],
    entries=[
        {
            "id": "standup-001",
            "thread_id": "team-standup",
            "agent": "Alice",
            "role": "pm",
            "entry_type": "Note",
            "timestamp": "2025-01-01T09:00:00Z",
            "title": "Monday Standup",
            "body": "Working on authentication feature. Blocked on API docs.",
        },
        {
            "id": "standup-002",
            "thread_id": "team-standup",
            "agent": "Bob",
            "role": "implementer",
            "entry_type": "Note",
            "timestamp": "2025-01-01T09:05:00Z",
            "title": "API Docs Available",
            "body": "I just published the API docs. They're on the wiki now.",
        },
        {
            "id": "standup-003",
            "thread_id": "team-standup",
            "agent": "Alice",
            "role": "pm",
            "entry_type": "Note",
            "timestamp": "2025-01-01T15:00:00Z",
            "title": "Blocker Resolved",
            "body": "Thanks Bob! I can proceed with the auth feature now.",
        },
    ],
)

prepare_result = backend.prepare(corpus)
print(f"Prepared {prepare_result.prepared_count} episodic entries")

# Step 5: Index (Graphiti doesn't use separate index step)
# The prepare step already indexed episodes into the temporal graph
print("Graphiti indexes during prepare - no separate index step needed")

# Step 6: Query with temporal awareness
queries = QueryPayload(
    manifest_version="1.0.0",
    queries=[
        {"query": "What was Alice blocked on?"},
        {"query": "Who helped resolve the blocker?"},
        {"query": "What happened between 09:00 and 15:00?"},
    ],
)

query_result = backend.query(queries)
for item in query_result.results:
    # Each item is a dict with keys: query, content, score, metadata
    print(f"Query: {item['query']}")
    print(f"Content: {item['content']}")
    print(f"Metadata: {item.get('metadata', {})}")
    print()
```

### Key Differences from LeanRAG

1. **No separate index step**: Graphiti indexes episodes during `prepare()`
2. **Temporal awareness**: Queries can reason about time and sequence
3. **Episodic model**: Each entry is a distinct episode with timestamps
4. **Requires OpenAI**: Uses GPT models for entity extraction and fact deduplication

## Error Handling

### Structured Exception Handling

```python
from watercooler_memory.backends import (
    get_backend,
    BackendError,
    ConfigError,
    TransientError,
    LeanRAGConfig,
)
from pathlib import Path

try:
    # Try to create backend
    config = LeanRAGConfig(work_dir=Path("./memory"))
    backend = get_backend("leanrag", config)

    # Try to prepare corpus
    result = backend.prepare(corpus)

except ConfigError as e:
    # Configuration problems (missing API keys, invalid paths, etc.)
    print(f"Configuration error: {e}")
    print("Check your config and environment variables")
    exit(1)

except TransientError as e:
    # Temporary failures (network timeouts, API rate limits, etc.)
    print(f"Temporary error: {e}")
    print("Safe to retry - this is likely a transient issue")
    # Implement retry logic here
    import time
    time.sleep(5)
    # Retry...

except BackendError as e:
    # General backend errors
    print(f"Backend error: {e}")
    # Log and handle appropriately
    import logging
    logging.error(f"Backend failed: {e}", exc_info=True)

except Exception as e:
    # Unexpected errors
    print(f"Unexpected error: {e}")
    raise
```

### Checking Health Before Operations

```python
from watercooler_memory.backends import get_backend, LeanRAGConfig
from pathlib import Path

config = LeanRAGConfig(work_dir=Path("./memory"))
backend = get_backend("leanrag", config)

# Always check health first
health = backend.healthcheck()
if not health.ok:
    print(f"Backend not healthy: {health.details}")
    print("Cannot proceed with operations")
    exit(1)

# Now safe to proceed
backend.prepare(corpus)
```

## Testing with Null Backend

The `NullBackend` provides a no-op implementation for testing without external dependencies.

### Unit Testing

```python
import pytest
from watercooler_memory.backends import NullBackend
from watercooler_memory.backends import CorpusPayload, QueryPayload

def test_my_application_logic():
    """Test application logic without real backend dependencies."""

    # Use Null backend for testing
    backend = NullBackend()

    # Null backend returns success for all operations
    corpus = CorpusPayload(
        manifest_version="1.0.0",
        threads=[],
        entries=[],
    )

    # These succeed but don't actually do anything
    prepare_result = backend.prepare(corpus)
    assert prepare_result.prepared_count == 0  # Null backend returns 0

    health = backend.healthcheck()
    assert health.ok is True  # Always healthy

    # Test your application logic that uses the backend
    # ...
```

### Mocking Backend Behavior

```python
from unittest.mock import Mock
from watercooler_memory.backends import MemoryBackend, QueryResult, QueryResultItem

def test_with_mock_backend():
    """Test with controlled mock responses."""

    # Create a mock that implements MemoryBackend
    mock_backend = Mock(spec=MemoryBackend)

    # Configure mock responses
    mock_backend.query.return_value = QueryResult(
        results=[
            QueryResultItem(
                query="test query",
                content="mock result",
                score=0.95,
                metadata={"source": "mock"},
            )
        ]
    )

    # Use mock in your application code
    result = mock_backend.query(queries)
    assert len(result.results) == 1
    assert result.results[0].content == "mock result"
```

## Full Pipeline Example

### End-to-End Watercooler Integration

```python
"""
Complete example: Load watercooler threads, build memory graph, query results.
"""
from pathlib import Path
from watercooler_memory import MemoryGraph, ChunkerConfig
from watercooler_memory.backends import get_backend, LeanRAGConfig
from watercooler_memory.backends import CorpusPayload, ChunkPayload, QueryPayload

# Configuration
threads_dir = Path("./watercooler-threads")
memory_dir = Path("./memory")

# Step 1: Build memory graph from threads
print("Building memory graph from watercooler threads...")
graph = MemoryGraph()
graph.build(threads_dir)

stats = graph.stats()
print(f"Loaded {stats['threads']} threads, {stats['entries']} entries")

# Step 2: Prepare corpus for backend
print("Preparing corpus...")
threads_data = []
entries_data = []

for thread in graph.threads.values():
    threads_data.append({
        "thread_id": thread.thread_id,
        "title": thread.title or f"Thread {thread.thread_id}",
        "status": thread.status,
    })

    for entry in thread.entries:
        entries_data.append({
            "id": entry.entry_id,
            "thread_id": thread.thread_id,
            "agent": entry.agent,
            "role": entry.role,
            "entry_type": entry.entry_type,
            "timestamp": entry.timestamp,
            "title": entry.title,
            "body": entry.body,
        })

corpus = CorpusPayload(
    manifest_version="1.0.0",
    threads=threads_data,
    entries=entries_data,
)

# Step 3: Initialize backend
print("Initializing LeanRAG backend...")
config = LeanRAGConfig(work_dir=memory_dir / "leanrag")
backend = get_backend("leanrag", config)

health = backend.healthcheck()
if not health.ok:
    print(f"Backend not healthy: {health.details}")
    exit(1)

# Step 4: Prepare and index
print("Preparing corpus (entity extraction)...")
prepare_result = backend.prepare(corpus)
print(f"Prepared {prepare_result.prepared_count} entries")

print("Chunking entries...")
chunker_config = ChunkerConfig.watercooler_preset()
chunks_list = graph.chunk_all_entries(config=chunker_config)

chunks = ChunkPayload(
    manifest_version="1.0.0",
    chunks=chunks_list,
    threads=corpus.threads,
    entries=corpus.entries,
)

print("Building knowledge graph...")
index_result = backend.index(chunks)
print(f"Indexed {index_result.indexed_count} chunks")

# Step 5: Query the memory
print("\nQuerying memory...")
queries = QueryPayload(
    manifest_version="1.0.0",
    queries=[
        {"query": "What features were implemented?"},
        {"query": "What technical decisions were made?"},
        {"query": "What issues were encountered?"},
    ],
)

query_result = backend.query(queries)

for item in query_result.results:
    print(f"\n{'='*60}")
    # Each item is a dict with keys: query, content, score, metadata
    print(f"Query: {item['query']}")
    print(f"Score: {item['score']:.3f}")
    print(f"Content: {item['content'][:300]}...")
    if item.get('metadata'):
        print(f"Source: {item['metadata'].get('thread_id', 'unknown')}")

print("\n✅ Pipeline complete!")
```

## Common Patterns

### Pattern 1: Backend Factory with Configuration

```python
"""Create backend based on environment or user preference."""
import os
from pathlib import Path
from watercooler_memory.backends import get_backend, LeanRAGConfig, GraphitiConfig

def create_backend_from_env():
    """Create backend based on MEMORY_BACKEND environment variable."""
    backend_type = os.getenv("MEMORY_BACKEND", "leanrag").lower()
    work_dir = Path(os.getenv("MEMORY_DIR", "./memory"))

    if backend_type == "leanrag":
        config = LeanRAGConfig(work_dir=work_dir / "leanrag")
        return get_backend("leanrag", config)

    elif backend_type == "graphiti":
        config = GraphitiConfig(
            work_dir=work_dir / "graphiti",
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
        return get_backend("graphiti", config)

    else:
        raise ValueError(f"Unknown backend type: {backend_type}")

# Usage
backend = create_backend_from_env()
```

### Pattern 2: Retry Logic for Transient Errors

```python
"""Retry transient failures with exponential backoff."""
import time
from watercooler_memory.backends import TransientError

def prepare_with_retry(backend, corpus, max_retries=3):
    """Prepare corpus with automatic retry on transient errors."""
    for attempt in range(max_retries):
        try:
            return backend.prepare(corpus)

        except TransientError as e:
            if attempt == max_retries - 1:
                raise  # Last attempt, give up

            wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
            print(f"Transient error (attempt {attempt + 1}/{max_retries}): {e}")
            print(f"Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

# Usage
result = prepare_with_retry(backend, corpus)
```

### Pattern 3: Progress Tracking

```python
"""Track progress through prepare/index/query pipeline."""
from typing import Callable
from watercooler_memory.backends import MemoryBackend

def run_pipeline_with_progress(
    backend: MemoryBackend,
    corpus,
    chunks,
    queries,
    progress_callback: Callable[[str, int, int], None] = None,
):
    """Run full pipeline with progress callbacks."""

    # Step 1: Prepare
    if progress_callback:
        progress_callback("prepare", 0, 3)

    prepare_result = backend.prepare(corpus)

    if progress_callback:
        progress_callback("prepare", 1, 3)

    # Step 2: Index
    if progress_callback:
        progress_callback("index", 1, 3)

    index_result = backend.index(chunks)

    if progress_callback:
        progress_callback("index", 2, 3)

    # Step 3: Query
    if progress_callback:
        progress_callback("query", 2, 3)

    query_result = backend.query(queries)

    if progress_callback:
        progress_callback("query", 3, 3)

    return {
        "prepare": prepare_result,
        "index": index_result,
        "query": query_result,
    }

# Usage with progress callback
def show_progress(step: str, current: int, total: int):
    percent = (current / total) * 100
    print(f"[{percent:.0f}%] {step}: {current}/{total}")

results = run_pipeline_with_progress(
    backend,
    corpus,
    chunks,
    queries,
    progress_callback=show_progress,
)
```

### Pattern 4: Multiple Backends for Comparison

```python
"""Run same query across multiple backends and compare results."""
from watercooler_memory.backends import get_backend, LeanRAGConfig, GraphitiConfig
from pathlib import Path

def compare_backends(corpus, chunks, queries):
    """Compare query results across different backends."""

    # Initialize backends
    leanrag = get_backend("leanrag", LeanRAGConfig(work_dir=Path("./memory/leanrag")))
    graphiti = get_backend("graphiti", GraphitiConfig(work_dir=Path("./memory/graphiti")))

    backends = {"leanrag": leanrag, "graphiti": graphiti}
    results = {}

    # Prepare and index (same data)
    for name, backend in backends.items():
        print(f"Preparing {name}...")
        backend.prepare(corpus)
        if name == "leanrag":  # Graphiti doesn't use separate index
            backend.index(chunks)

    # Query all backends
    for name, backend in backends.items():
        print(f"Querying {name}...")
        query_result = backend.query(queries)
        results[name] = query_result.results

    # Compare results
    print("\n=== Comparison ===")
    for query_idx, query in enumerate(queries.queries):
        print(f"\nQuery: {query['query']}")
        for name in backends.keys():
            if query_idx < len(results[name]):
                item = results[name][query_idx]
                # Each item is a dict
                print(f"{name}: score={item['score']:.3f}, content={item['content'][:100]}...")

    return results
```

## See Also

- [Memory Backend Status](../MEMORY_BACKEND_STATUS.md) - Implementation progress
- [LeanRAG Setup Guide](../LEANRAG_SETUP.md) - LeanRAG installation and configuration
- [Graphiti Setup Guide](../GRAPHITI_SETUP.md) - Graphiti installation and configuration
- [ADR 0001](../adr/0001-memory-backend-contract.md) - Backend contract specification
- [Smoke Tests Guide](../SMOKE_TESTS.md) - Testing documentation
