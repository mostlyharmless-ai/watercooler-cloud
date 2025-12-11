# Graph-First Architecture Gaps

This document identifies areas where the codebase could be refactored for a true graph-first architecture, where the graph representation is the primary read source.

## Current State (as of 2025-01)

The graph representation stores **complete data** (entry bodies, summaries, embeddings), not just metadata. However, most read operations still parse markdown directly.

## Identified Gaps

### 1. Thread Reading Operations (`commands.py`)

**Current:** `read_thread()` parses markdown files directly.

**Gap:** Could read from `{threads_dir}/graph/baseline/nodes.jsonl` instead.

**Migration Path:**
- Add `read_thread_from_graph()` function
- Implement fallback: graph -> markdown
- Config flag: `prefer_graph_reads = true`

### 2. List Operations (`commands.py`)

**Current:** `list_threads()` scans `.md` files and parses headers.

**Gap:** Could query graph nodes of type `thread` directly.

**Migration Path:**
- Add `list_threads_from_graph()` function
- Build index by `type: thread` from nodes.jsonl
- Faster for large thread directories

### 3. MCP Server Read Tools (`server.py`)

**Current:** `watercooler_v1_read_thread`, `watercooler_v1_list_threads`, `watercooler_v1_get_thread_entry*` all parse markdown.

**Gap:** Could read from graph representation.

**Migration Path:**
- Add graph-backed implementations
- Use config to control read source
- Maintain backward compatibility

### 4. Entry Listing (`structured_entries.py`)

**Current:** `parse_thread_entries()` parses markdown file.

**Gap:** Could load entries from graph nodes.

**Migration Path:**
- Add `load_entries_from_graph()` function
- Filter graph nodes by `thread_topic == topic`

### 5. Dashboard API (`dashboard/routes.py`)

**Current:** Parses markdown for dashboard display.

**Gap:** Could serve pre-computed graph data.

**Migration Path:**
- Add graph endpoint: `/api/graph/{topic}`
- Return pre-summarized, pre-embedded data

## What's Already Graph-First

- **Write operations**: All writes go to markdown, then sync to graph (correct)
- **Summaries**: Generated at write-time, stored in graph
- **Embeddings**: Generated at write-time, stored in graph
- **Export/Build**: `baseline_graph_build` creates complete graph representation
- **Reconciliation**: `reconcile_graph` rebuilds from markdown

## Recommended Phased Approach

### Phase 1: Config Flag (Low Risk)
Add `mcp.graph.prefer_graph_reads = false` to config schema.

### Phase 2: Parallel Implementations (Medium Risk)
Implement graph-backed read functions alongside markdown ones.

### Phase 3: A/B Testing (Low Risk)
Enable graph reads for specific operations based on config.

### Phase 4: Migration (Higher Risk)
Default to graph reads, keep markdown as authoritative write target.

## Key Invariants to Maintain

1. **Markdown is authoritative for writes** - all modifications go through markdown
2. **Graph is derived** - always rebuildable from markdown via `reconcile_graph`
3. **Sync is non-blocking** - graph sync failures don't prevent markdown writes
4. **Backward compatible** - graph reads should fall back to markdown if graph is stale

## Performance Considerations

- Graph reads could be significantly faster for large threads
- Pre-computed summaries eliminate on-read summarization
- Embeddings enable semantic search without re-computation
- JSONL format allows incremental updates and streaming

## Files to Modify for Full Graph-First

1. `src/watercooler/commands.py` - Core read operations
2. `src/watercooler_mcp/server.py` - MCP tool implementations
3. `src/watercooler/structured_entries.py` - Entry parsing
4. `src/watercooler/config_schema.py` - Add `prefer_graph_reads` flag
5. `src/watercooler/dashboard/routes.py` - Dashboard API (if exists)
