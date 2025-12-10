# Watercooler Graph Sync

This document describes the automatic graph synchronization system that keeps the baseline knowledge graph in sync with markdown thread files.

## Overview

Every MCP write operation (`say`, `ack`, `handoff`, `set_status`) automatically updates the baseline graph in addition to the markdown files. This enables:

- **Fast queries**: Read operations can query the graph instead of parsing markdown
- **Semantic search**: Graph nodes include embeddings for similarity search
- **Cross-references**: Automatic detection of references between threads/entries
- **Usage analytics**: Access counting for identifying hot topics

## Architecture

```
MCP Write Operation
       │
       ▼
┌─────────────────┐
│  Markdown Write │  ← Source of truth
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Graph Sync    │  ← Derived index (non-blocking)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   JSONL Export  │  ← Git-friendly storage
└─────────────────┘
```

### Key Principles

1. **Markdown is source of truth** - Graph is a derived index
2. **Non-blocking sync** - Graph failures don't block markdown writes
3. **Atomic operations** - JSONL writes use temp file + rename
4. **Eventually consistent** - Reconciliation tools fix drift
5. **Per-topic locking** - Concurrent writes serialized per topic

## Storage Format

Graph data is stored in JSONL format at `{threads-repo}/graph/baseline/`:

```
graph/baseline/
├── nodes.jsonl      # Thread and entry nodes
├── edges.jsonl      # Relationships between nodes
├── manifest.json    # Metadata and checksums
└── sync_state.json  # Per-topic sync status
```

### Node Schema

**Thread Node:**
```json
{
  "id": "thread:feature-auth",
  "type": "thread",
  "topic": "feature-auth",
  "title": "Authentication Feature Thread",
  "status": "OPEN",
  "ball": "Claude (user)",
  "last_updated": "2025-01-15T10:30:00Z",
  "summary": "Discussion about OAuth2 implementation...",
  "entry_count": 12
}
```

**Entry Node:**
```json
{
  "id": "entry:01KB6VPBN440PJEYBV3RWYW9NC",
  "type": "entry",
  "entry_id": "01KB6VPBN440PJEYBV3RWYW9NC",
  "thread_topic": "feature-auth",
  "index": 0,
  "agent": "Claude Code (user)",
  "role": "planner",
  "entry_type": "Plan",
  "title": "Authentication Architecture Plan",
  "timestamp": "2025-01-15T10:00:00Z",
  "summary": "Proposed OAuth2 with PKCE flow...",
  "file_refs": ["src/auth/oauth.py"],
  "pr_refs": ["#123"],
  "commit_refs": ["abc1234"]
}
```

### Edge Schema

```json
{"source": "thread:feature-auth", "target": "entry:01KB...", "type": "contains"}
{"source": "entry:01KB...", "target": "entry:01KC...", "type": "followed_by"}
{"source": "entry:01KB...", "target": "thread:other-topic", "type": "references_thread"}
```

## Sync State

Each topic tracks its sync status in `sync_state.json`:

```json
{
  "topics": {
    "feature-auth": {
      "status": "ok",
      "last_synced_entry_id": "01KC0534JYTZS6Y915MHBJ432J",
      "last_sync_at": "2025-01-15T10:30:00Z",
      "error_message": null,
      "entries_synced": 12
    }
  },
  "last_updated": "2025-01-15T10:30:00Z"
}
```

### Status Values

| Status | Description |
|--------|-------------|
| `ok` | Graph is in sync with markdown |
| `error` | Sync failed - see error_message |
| `pending` | Sync queued but not yet complete |

## Failure Handling

When graph sync fails:

1. **Error is logged** but write operation succeeds
2. **Status marked as `error`** in sync state
3. **Error message preserved** for debugging
4. **Reconciliation available** via CLI or MCP tool

This ensures graph issues never block thread operations.

## Health Checking

Check graph sync health:

```bash
# CLI (coming soon)
watercooler graph-health

# MCP tool (coming soon)
watercooler_v1_graph_health
```

Health report includes:
- Total threads in directory
- Threads with successful sync
- Threads with sync errors
- Stale threads (no sync state)

## Reconciliation

Fix graph drift by reconciling with markdown:

```python
from watercooler.baseline_graph.sync import reconcile_graph

# Reconcile all stale/error topics
results = reconcile_graph(threads_dir)

# Reconcile specific topics
results = reconcile_graph(threads_dir, topics=["feature-auth"])
```

Reconciliation:
1. Identifies stale/error topics
2. Re-parses markdown files
3. Rebuilds graph nodes/edges
4. Updates sync state

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WATERCOOLER_GRAPH_SYNC` | `1` | Enable graph sync on writes |
| `WATERCOOLER_GRAPH_SUMMARIES` | `0` | Generate LLM summaries (slow) |

### Disabling Graph Sync

To disable graph sync (e.g., for performance testing):

```bash
export WATERCOOLER_GRAPH_SYNC=0
```

## Concurrency

Graph sync is safe under concurrent writes:

1. **Per-topic locking**: MCP operations acquire topic lock before write
2. **Atomic JSONL writes**: temp file + rename prevents corruption
3. **Deduplication**: JSONL append merges by node/edge ID

## Performance

### Sync Latency

| Operation | Typical Time |
|-----------|--------------|
| Entry sync (no summaries) | ~10-50ms |
| Entry sync (with LLM summary) | ~500-2000ms |
| Full thread sync | ~50-200ms |
| Reconcile all topics | ~1-5s |

### Optimization Tips

1. **Disable LLM summaries** for fast writes (`generate_summaries=False`)
2. **Use extractive summaries** when needed (faster than LLM)
3. **Batch reconciliation** during low-activity periods

## Future Enhancements

1. **Graph read operations** - Query graph instead of parsing markdown
2. **Unified search** - Keyword, semantic, and time-boxed search via graph
3. **Odometer counters** - Track access counts for analytics
4. **FalkorDB backend** - Optional graph database for complex queries
5. **Incremental sync** - Only sync changed entries (sidecar index)

## Related Documentation

- Thread: `graph-driven-mcp-architecture` - Architecture planning
- Thread: `baseline-graph-thread-parser` - Parser implementation
- Thread: `baseline-graph-enhancements` - Cross-references and summaries
