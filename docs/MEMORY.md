# Memory Module

The `watercooler_memory` module provides tools for building a memory graph from watercooler threads, enabling semantic search, entity extraction, and integration with LeanRAG.

## Installation

The memory module requires additional dependencies. Install with:

```bash
pip install 'watercooler-cloud[memory]'
```

Or using uvx:

```bash
uvx watercooler-cloud[memory]
```

## Quick Start

```python
from watercooler_memory import MemoryGraph, GraphConfig

# Create a graph with default config (no API calls)
config = GraphConfig(
    generate_summaries=False,
    generate_embeddings=False,
)
graph = MemoryGraph(config)

# Build from threads directory
graph.build("/path/to/threads")

# Export to LeanRAG format
from watercooler_memory import export_to_leanrag
manifest = export_to_leanrag(graph, "/path/to/output")

# Save graph for later use
graph.save("/path/to/graph.json")
```

## Architecture

The graph uses a hierarchical structure:

```
Thread → Entry → Chunk
```

With hyperedges for membership and temporal edges for sequencing.

### Node Types

- **ThreadNode**: Represents a watercooler thread with metadata (status, ball, timestamps)
- **EntryNode**: Represents an individual entry in a thread (agent, role, type, body)
- **ChunkNode**: Text chunks created by splitting entry bodies for embedding
- **EntityNode**: Named entities extracted from chunks (future feature)

### Edge Types

- **CONTAINS**: Thread contains entries, entries contain chunks
- **FOLLOWS**: Temporal sequence between entries
- **MENTIONS**: Entity mentions (future feature)

## Configuration

### GraphConfig

```python
from watercooler_memory import GraphConfig

config = GraphConfig(
    # Enable/disable LLM summary generation
    generate_summaries=True,

    # Enable/disable embedding generation
    generate_embeddings=True,

    # Chunker settings
    chunk_max_tokens=1024,
    chunk_overlap_tokens=100,
)
```

### Environment Variables

For summary generation:
- `DEEPSEEK_API_KEY`: API key for DeepSeek LLM
- `LLM_API_BASE`: LLM API endpoint (default: `https://api.deepseek.com/v1`)

For embedding generation:
- `EMBEDDING_API_BASE`: bge-m3 API endpoint (default: `http://localhost:8000/v1`)

## CLI Usage

Build a memory graph:

```bash
# Basic build (no API calls)
python scripts/build_memory_graph.py /path/to/threads -o graph.json

# With summaries (requires DEEPSEEK_API_KEY)
python scripts/build_memory_graph.py /path/to/threads -o graph.json

# Skip summaries
python scripts/build_memory_graph.py /path/to/threads --no-summaries -o graph.json

# Skip embeddings
python scripts/build_memory_graph.py /path/to/threads --no-embeddings -o graph.json

# Export to LeanRAG format
python scripts/build_memory_graph.py /path/to/threads --export-leanrag ./leanrag-output
```

## LeanRAG Export

The module exports to LeanRAG-compatible format for knowledge graph building.

### Export Format

The export creates three files:

**manifest.json**
```json
{
  "format": "leanrag",
  "version": "1.0",
  "source": "watercooler-cloud",
  "statistics": {
    "threads": 51,
    "documents": 530,
    "chunks": 569,
    "embeddings_included": true
  },
  "files": {
    "documents": "documents.json",
    "threads": "threads.json"
  }
}
```

**documents.json** - Entries as documents with chunks:
```json
[
  {
    "doc_id": "entry-001",
    "title": "Implementation Complete",
    "content": "Full entry body...",
    "summary": "Generated summary...",
    "chunks": [
      {
        "hash_code": "abc123",
        "text": "Chunk text...",
        "token_count": 100,
        "embedding": [0.1, 0.2, ...]
      }
    ],
    "metadata": {
      "thread_id": "feature-auth",
      "agent": "Claude",
      "role": "implementer",
      "entry_type": "Note",
      "timestamp": "2025-01-01T12:00:00Z"
    }
  }
]
```

**threads.json** - Thread metadata:
```json
[
  {
    "thread_id": "feature-auth",
    "title": "Authentication Feature",
    "status": "OPEN",
    "ball": "Claude",
    "entry_count": 10,
    "summary": "Thread summary..."
  }
]
```

### Validation

Exports are validated by default against the LeanRAG schema:

```python
from watercooler_memory import export_to_leanrag, ValidationError

try:
    manifest = export_to_leanrag(graph, output_dir)
except ValidationError as e:
    print(f"Validation failed: {e}")
    for error in e.errors:
        print(f"  {error['type']}: {error['errors']}")

# Skip validation if needed
manifest = export_to_leanrag(graph, output_dir, validate=False)
```

### Direct Validation

```python
from watercooler_memory import (
    validate_chunk,
    validate_document,
    validate_export,
    validate_pipeline_chunks,
    ValidationError,
)

# Validate a single chunk
errors = validate_chunk({"hash_code": "abc", "text": "Hello"})
if errors:
    print("Invalid chunk:", errors)

# Validate full export
try:
    validate_export(documents, threads, manifest)
except ValidationError as e:
    print("Export validation failed")
```

## Schema Reference

### JSON Schemas

The module provides JSON schemas for validation:

```python
from watercooler_memory import (
    LEANRAG_CHUNK_SCHEMA,
    LEANRAG_DOCUMENT_SCHEMA,
    LEANRAG_MANIFEST_SCHEMA,
    LEANRAG_PIPELINE_CHUNK_SCHEMA,
)
```

### Chunk Schema (Required Fields)

```json
{
  "hash_code": "string (required, non-empty)",
  "text": "string (required)",
  "embedding": "array of numbers or null (optional)",
  "metadata": "object (optional)"
}
```

### Document Schema (Required Fields)

```json
{
  "doc_id": "string (required, non-empty)",
  "content": "string (required)",
  "chunks": "array of chunks (required)"
}
```

## Caching

The module includes caching for summaries and embeddings to avoid redundant API calls:

```python
from watercooler_memory import (
    SummaryCache,
    EmbeddingCache,
    cache_stats,
    clear_cache,
)

# View cache statistics
stats = cache_stats()
print(f"Summary cache: {stats['summaries']} entries")
print(f"Embedding cache: {stats['embeddings']} entries")

# Clear caches
clear_cache()
```

## API Reference

### MemoryGraph

```python
class MemoryGraph:
    def __init__(self, config: GraphConfig = None): ...
    def build(self, threads_dir: Path, branch_context: str = None,
              progress_callback: Callable = None): ...
    def add_thread(self, thread_path: Path) -> ThreadNode: ...
    def chunk_all_entries(self) -> list[ChunkNode]: ...
    def stats(self) -> dict[str, int]: ...
    def to_dict(self) -> dict: ...
    def save(self, path: Path): ...
    @classmethod
    def load(cls, path: Path) -> "MemoryGraph": ...
```

### Export Functions

```python
def export_to_leanrag(
    graph: MemoryGraph,
    output_dir: Path,
    include_embeddings: bool = True,
    validate: bool = True,
) -> dict[str, Any]: ...

def export_for_leanrag_pipeline(
    graph: MemoryGraph,
    output_path: Path,
    validate: bool = True,
) -> None: ...
```

### Validation Functions

```python
def validate_chunk(chunk: dict) -> list[str]: ...
def validate_document(doc: dict) -> list[str]: ...
def validate_manifest(manifest: dict) -> list[str]: ...
def validate_export(documents: list, threads: list, manifest: dict) -> None: ...
def validate_pipeline_chunks(chunks: list) -> None: ...
```

## Checkpointing and Recovery

For long-running graph builds, use checkpointing to save progress and enable recovery from failures.

### Using Checkpoints

```python
from watercooler_memory import MemoryGraph, GraphConfig
from pathlib import Path

graph = MemoryGraph()

# Build with checkpointing enabled
graph.build(
    threads_dir=Path("./threads"),
    checkpoint_path=Path("./graph-checkpoint.json"),
    timeout=3600,  # 1 hour timeout
)
```

The checkpoint file is saved atomically after each stage (parsing, chunking, summarization, embeddings).

### Recovery Workflow

If a build fails partway through:

```python
from watercooler_memory import MemoryGraph
from pathlib import Path

checkpoint_path = Path("./graph-checkpoint.json")

if checkpoint_path.exists():
    # Load from checkpoint
    print("Resuming from checkpoint...")
    graph = MemoryGraph.load(checkpoint_path)

    # Check what's already done
    stats = graph.stats()
    print(f"Loaded: {stats['threads']} threads, {stats['entries']} entries")
    print(f"Summaries: {stats['entries_with_summaries']}/{stats['entries']}")

    # Continue remaining steps manually
    if stats['entries_with_summaries'] < stats['entries']:
        graph.generate_summaries()
    if stats['entries_with_embeddings'] < stats['entries']:
        graph.generate_embeddings()

    # Save final result
    graph.save(Path("./graph.json"))
else:
    # Fresh build
    graph = MemoryGraph()
    graph.build(
        threads_dir=Path("./threads"),
        checkpoint_path=checkpoint_path,
    )
```

### Caching Benefits

Even without explicit checkpoints, the disk caches for summaries and embeddings survive pipeline failures:

- **Summary cache**: `~/.cache/watercooler/summaries/`
- **Embedding cache**: `~/.cache/watercooler/embeddings/`

Re-running `generate_summaries()` or `generate_embeddings()` automatically reuses cached results, so failed builds can be restarted without re-processing already-completed items.

### Timeout Handling

```python
try:
    graph.build(
        threads_dir=Path("./threads"),
        timeout=1800,  # 30 minutes
        checkpoint_path=Path("./checkpoint.json"),
    )
except TimeoutError:
    print("Build timed out - checkpoint saved")
    # Load checkpoint and continue in a new session
```

## Graceful Degradation

The module supports graceful degradation when optional dependencies are missing:

```python
from watercooler_memory import MEMORY_AVAILABLE

if MEMORY_AVAILABLE:
    # Full functionality available
    from watercooler_memory import MemoryGraph
    graph = MemoryGraph()
else:
    # Validation is always available (no external deps)
    from watercooler_memory import validate_chunk
    errors = validate_chunk({"hash_code": "abc", "text": "test"})
```

## Integration with LeanRAG

The exported format is designed to work with LeanRAG's entity extraction and graph building pipeline:

```bash
# 1. Build memory graph from watercooler threads
python scripts/build_memory_graph.py ./threads --export-leanrag ./export

# 2. Run LeanRAG entity extraction on exported chunks
python /path/to/LeanRAG/process_markdown_pipeline.py ./export/documents.json

# 3. Build LeanRAG knowledge graph
python /path/to/LeanRAG/build_graph.py ./export
```

The chunks contain the required `hash_code` and `text` fields that LeanRAG's pipeline expects.
