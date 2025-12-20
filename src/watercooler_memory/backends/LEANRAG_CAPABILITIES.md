# LeanRAG Backend Capability Analysis

**Author:** Cascade (AI Assistant)  
**Date:** 2025-12-19  
**Status:** Analysis Complete - For Team Review  

---

## Executive Summary

This document analyzes LeanRAG's capabilities in the context of the proposed `MemoryBackend` protocol extension. LeanRAG provides robust entity extraction, relationship extraction, and hierarchical graph construction. Most proposed protocol methods can be supported, with some caveats around ID formats and multi-tenancy.

**Key Finding:** LeanRAG **does** have entity and relationship extraction (contrary to initial assumptions). The extraction is LLM-based and produces entities with types, descriptions, and source references.

---

## Table of Contents

1. [Search Operations Support](#1-search-operations-support)
2. [Retrieval Operations Support](#2-retrieval-operations-support)
3. [Grouping/Multi-tenancy](#3-groupingmulti-tenancy)
4. [Response Format](#4-response-format)
5. [Capability Declaration Recommendation](#5-capability-declaration-recommendation)
6. [Implementation Notes](#6-implementation-notes)

---

## 1. Search Operations Support

### ✅ `search_nodes()` - SUPPORTED

LeanRAG has full entity/node extraction and vector-based search.

**Underlying LeanRAG API:**
- `search_vector_search()` in `leanrag/database/milvus.py`
- `search_nodes()` in `leanrag/database/adapter.py` (unified API)

**How it works:**

```python
# From leanrag/database/milvus.py:114-167
def search_vector_search(working_dir, query, topk=10, level_mode=2):
    """
    Vector similarity search on entity embeddings.
    
    level_mode:
        0: original nodes (base entities only)
        1: aggregated nodes (cluster summaries only)
        2: all nodes (both levels)
    """
    search_results = milvus_client.search(
        collection_name="entity_collection",
        data=query_list,
        limit=topk,
        output_fields=["entity_name", "description", "parent", "level", "source_id"],
    )
    return [(entity_name, parent, description, source_id) for ...]
```

**Response format:**

```python
[
    ("OAUTH2", "AUTHENTICATION", "OAuth2 implementation for secure auth...", "chunk_abc123"),
    ("JWT_TOKENS", "OAUTH2", "JSON Web Tokens for session management...", "chunk_def456"),
]
# Format: (entity_name, parent, description, source_id)
```

**Performance considerations:**
- Uses Milvus vector index (IVF_FLAT) with inner product similarity
- TopK configurable (default: 10)
- Level filtering available (base entities vs. clusters)
- Latency: ~50-200ms depending on corpus size

---

### ✅ `search_facts()` - SUPPORTED (with caveats)

LeanRAG extracts relationships between entities during indexing.

**Underlying LeanRAG API:**
- `search_nodes_link()` in `leanrag/database/adapter.py`
- Relationships stored as `RELATES_TO` edges in FalkorDB

**How it works:**

```python
# From leanrag/database/falkordb.py:417-462
def search_nodes_link(entity1, entity2, working_dir, level=None):
    """Find direct relationship between two entities (checks both directions)."""
    query = """
    MATCH (e1:Entity {entity_name: $entity1})
    MATCH (e2:Entity {entity_name: $entity2})
    MATCH (e1)-[r:RELATES_TO]-(e2)
    RETURN r.src_tgt, r.tgt_src, r.description, r.weight, r.level
    LIMIT 1
    """
```

**Response format:**

```python
("OAUTH2", "JWT_TOKENS", "OAuth2 uses JWT tokens for authentication", 1.0, 0)
# Format: (source, target, description, weight, level)
```

**Important caveat:** 

LeanRAG doesn't have a direct "search facts by query string" API like Graphiti's `search_()`. The workflow is:

1. Search for entities via vector search (`search_vector_search`)
2. Traverse relationships between found entities (`search_nodes_link`)
3. Aggregate relationship descriptions

This is what `get_reasoning_chain()` in `leanrag/pipelines/query.py` does internally.

**To implement `search_facts(query)`:** We would need to:
1. Embed the query
2. Find top-K relevant entities
3. Find relationships between those entities
4. Return relationship descriptions with scores

---

### ✅ `search_episodes()` - SUPPORTED (chunks = episodes)

LeanRAG chunks map conceptually to Graphiti's "episodes".

**Underlying LeanRAG API:**
- `search_chunks()` in `leanrag/database/adapter.py`
- `get_text_units()` in `leanrag/database/mysql.py`

**How it works:**

```python
# From leanrag/database/falkordb.py:465-499
def search_chunks(working_dir, entity_set):
    """Retrieve source chunk IDs for a set of entities."""
    query = """
    UNWIND $entities AS entity_name
    MATCH (n:Entity {entity_name: entity_name})
    RETURN n.source_id
    """
```

**Response format:**
- Returns chunk hash codes (e.g., `"abc123def456"`)
- Actual text retrieved from `threads_chunk.json` file

**Mapping to protocol:**

| Protocol Field | LeanRAG Equivalent |
|----------------|-------------------|
| `id` | `hash_code` (MD5 hash) |
| `name` | N/A (use first line of text) |
| `content` | `text` |
| `score` | Milvus distance (inner product) |
| `valid_at` | N/A (no timestamps) |
| `source_description` | N/A |

---

## 2. Retrieval Operations Support

### ⚠️ `get_node(node_id)` - PARTIALLY SUPPORTED

LeanRAG can retrieve entities by **name**, but not by arbitrary UUID.

**Underlying LeanRAG API:**

```python
# From leanrag/database/falkordb.py:502-533
def search_nodes(entity_set, working_dir):
    """Retrieve full entity data for base-level entities (level=0)."""
    query = """
    UNWIND $entities AS entity_name
    MATCH (n:Entity {entity_name: entity_name, level: 0})
    RETURN n.entity_name, n.description, n.source_id, n.degree, n.parent, n.level
    """
```

**ID format in LeanRAG:**

LeanRAG uses **entity names** as identifiers, not UUIDs:
- Example: `"OAUTH2"`, `"JWT_TOKENS"`, `"CLAUDE"`
- Names are uppercase (normalized during extraction)

**Implementation approach:**

```python
def get_node(self, node_id: str, group_id: str | None = None) -> dict | None:
    """Get node by entity name (LeanRAG's ID format)."""
    results = search_nodes([node_id], self.config.work_dir)
    if results:
        row = results[0]
        return {
            "id": row[0],           # entity_name
            "name": row[0],         # entity_name
            "summary": row[1],      # description
            "source_id": row[2],    # source chunk
            "degree": row[3],
            "parent": row[4],
            "level": row[5],
        }
    return None
```

---

### ❌ `get_edge(edge_id)` - NOT SUPPORTED

LeanRAG **does not** have edge IDs. Relationships are identified by `(source, target)` pairs.

**Workaround:**

Use `search_nodes_link(entity1, entity2, working_dir)` to get a specific relationship by its endpoints.

**Implementation approach:**

```python
def get_edge(self, edge_id: str, group_id: str | None = None) -> dict | None:
    """
    LeanRAG doesn't support edge IDs.
    
    If edge_id is in format "SOURCE||TARGET", we can parse and look up.
    Otherwise, return None.
    """
    if "||" in edge_id:
        source, target = edge_id.split("||", 1)
        result = search_nodes_link(source, target, self.config.work_dir)
        if result:
            return {
                "id": edge_id,
                "source_node_id": result[0],
                "target_node_id": result[1],
                "fact": result[2],
                "weight": result[3],
                "level": result[4],
            }
    return None
```

---

## 3. Grouping/Multi-tenancy

### ❌ Limited Support

LeanRAG uses `working_dir` basename as the database name:

```python
# From leanrag/database/falkordb.py:78-79
graph_name = os.path.basename(working_dir)
db, graph = get_falkordb_connection(graph_name)
```

**Comparison with Graphiti:**

| Feature | Graphiti | LeanRAG |
|---------|----------|---------|
| Partition key | `group_id` (per-thread) | `working_dir` (per-corpus) |
| Granularity | Thread-level | Corpus-level |
| Filter in query | Yes (`group_ids` param) | No |
| Multiple partitions | Same database | Separate databases |

**Options for supporting `group_ids` filtering:**

1. **Multiple databases** (one per thread) - Expensive, requires separate index builds
2. **Schema extension** - Add `thread_id` field to entities and filter in queries
3. **Accept limitation** - Document that LeanRAG doesn't support per-query filtering

**Recommendation:** Accept the limitation for now. Document that `group_ids` parameter is ignored by LeanRAG backend.

---

## 4. Response Format

### Chunks/Episodes

| Field | LeanRAG Name | Type | Notes |
|-------|--------------|------|-------|
| ID | `hash_code` | String | MD5 hash of chunk text |
| Content | `text` | String | Full chunk text |
| Score | N/A | Float | Milvus inner product distance |
| Metadata | `source_id` on entities | String | Links entity → chunk |

### Entities/Nodes

| Field | LeanRAG Name | Type | Notes |
|-------|--------------|------|-------|
| ID | `entity_name` | String | Uppercase, normalized |
| Name | `entity_name` | String | Same as ID |
| Type | `entity_type` | String | e.g., "TECHNOLOGY", "PERSON" |
| Summary | `description` | String | LLM-generated description |
| Level | `level` | Integer | 0=base, 1+=clusters |
| Parent | `parent` | String | Parent entity name |
| Source | `source_id` | String | Chunk hash(es), pipe-delimited |

### Relationships/Facts

| Field | LeanRAG Name | Type | Notes |
|-------|--------------|------|-------|
| Source | `src_tgt` | String | Source entity name |
| Target | `tgt_src` | String | Target entity name |
| Description | `description` | String | Relationship description |
| Weight | `weight` | Float | Default 1.0 |
| Level | `level` | Integer | Hierarchy level |

---

## 5. Capability Declaration Recommendation

Based on the analysis, here's the recommended capability declaration:

```python
class LeanRAGBackend(MemoryBackend):
    def get_capabilities(self) -> Capabilities:
        return Capabilities(
            # Core capabilities
            embeddings=True,           # Via Milvus vector search
            entity_extraction=True,    # LLM-based triple extraction
            graph_query=True,          # Hierarchical graph traversal
            rerank=False,              # No reranking layer
            
            # Database support
            supports_falkor=True,      # Primary graph DB
            supports_milvus=True,      # Vector search
            supports_neo4j=False,
            
            # Schema versions
            schema_versions=["1.0.0"],
            max_tokens=1024,
        )
```

**Protocol method support matrix:**

| Method | Supported | Notes |
|--------|-----------|-------|
| `search_nodes()` | ✅ Yes | Vector similarity on entity embeddings |
| `search_facts()` | ✅ Yes | Via entity search + relationship traversal |
| `search_episodes()` | ✅ Yes | Chunks map to episodes |
| `get_node(id)` | ⚠️ Partial | By name, not UUID |
| `get_edge(id)` | ❌ No | No edge IDs (use source||target format) |
| `group_ids` filter | ❌ No | Separate databases only |

---

## 6. Implementation Notes

### Entity Extraction Pipeline

LeanRAG's extraction is robust and comparable to Graphiti:

```python
# From leanrag/extraction/chunk.py:49
async def triple_extraction(chunks, use_llm_func, output_dir, save_filtered=False):
    """
    Extract entities AND relationships from chunks.
    
    Uses prompts adapted from Microsoft's GraphRAG.
    Includes entity verification to filter hallucinated entities.
    
    Outputs:
        - entity.jsonl: Extracted entities
        - relation.jsonl: Extracted relationships
    """
```

**Entity output format:**

```json
{
    "entity_name": "OAUTH2",
    "entity_type": "TECHNOLOGY",
    "description": "OAuth2 is an authorization framework...",
    "source_id": "abc123def456"
}
```

**Relationship output format:**

```json
{
    "src_tgt": "OAUTH2",
    "tgt_src": "JWT_TOKENS",
    "description": "OAuth2 uses JWT tokens for secure authentication",
    "weight": 1.0,
    "source_id": "abc123def456"
}
```

### Hierarchical Clustering

LeanRAG builds a hierarchical graph with multiple levels:

- **Level 0:** Base entities (raw extracted)
- **Level 1+:** Cluster entities (aggregated summaries)

This is similar to Graphiti's community detection but uses GMM + UMAP clustering.

### Existing `LeanRAGBackend` Implementation

The current implementation in `backends/leanrag.py` already handles:
- `prepare()` - Converts corpus to LeanRAG format
- `index()` - Runs triple extraction and graph building
- `query()` - Executes queries via `query_graph()`
- `healthcheck()` - Validates FalkorDB connectivity

**Missing methods to add:**
- `search_nodes()`
- `search_facts()`
- `search_episodes()`
- `get_node()`
- `get_edge()` (stub returning None)

---

## Summary

| Question | Answer |
|----------|--------|
| Does LeanRAG have entity extraction? | ✅ Yes - LLM-based with verification |
| Does LeanRAG have relationship extraction? | ✅ Yes - Stored as RELATES_TO edges |
| Can chunks map to episodes? | ✅ Yes - hash_code → id, text → content |
| Can we retrieve nodes by ID? | ⚠️ By name only, not UUID |
| Can we retrieve edges by ID? | ❌ No - use source||target format |
| Does LeanRAG support group_ids filtering? | ❌ No - separate databases only |

**Recommendation:** Implement LeanRAG support with the caveats documented. The backend provides valuable entity/relationship extraction that complements Graphiti's temporal graph approach.

---

## References

- LeanRAG extraction: `external/LeanRAG/leanrag/extraction/chunk.py`
- LeanRAG query: `external/LeanRAG/leanrag/pipelines/query.py`
- LeanRAG FalkorDB adapter: `external/LeanRAG/leanrag/database/falkordb.py`
- LeanRAG Milvus adapter: `external/LeanRAG/leanrag/database/milvus.py`
- Current backend implementation: `backends/leanrag.py`
