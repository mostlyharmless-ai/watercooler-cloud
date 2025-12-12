# Memory Backend Smoke Tests

## Overview

The memory backend smoke tests validate the full prepare→index→query pipeline with real databases. These tests are marked with `@pytest.mark.integration_falkor` and require specific environment setup.

## Test Structure

### Basic Tests (Always Run)
- **Healthcheck**: Validates backend and database availability
- **Prepare Only**: Tests corpus preparation without database access

These tests run quickly and don't require databases.

### Full Pipeline Tests (Environment Required)
- **Prepare→Index→Query**: Full workflow with real database operations
- **Multi-Backend Comparison**: Validates consistency across backends

These tests require installed dependencies and running databases.

## Environment Setup

### 1. LeanRAG Backend Requirements

**Install LeanRAG:**
```bash
# From watercooler-cloud root
pip install -e external/LeanRAG
```

**Required Dependencies:**
- Python 3.10+
- LeanRAG dependencies (installed with above command)

**Optional (for embeddings):**
- OpenAI API key or compatible endpoint
- Milvus vector database

**Database:**
- FalkorDB on port 6379 (Redis protocol)
- OR Neo4j on bolt port 7687

### 2. Graphiti Backend Requirements

**Install Graphiti:**
```bash
# From watercooler-cloud root
pip install -e external/graphiti
```

**Required Dependencies:**
- Python 3.10+
- Graphiti dependencies (neo4j, openai, diskcache, etc.)
- **OpenAI API key** (required for Graphiti's LLM operations)

**Environment Variables:**
```bash
export OPENAI_API_KEY="sk-..."
```

**Database:**
- FalkorDB on bolt port 7687
- OR Neo4j on bolt port 7687

### 3. Database Setup

**Option A: Docker (Recommended)**
```bash
# FalkorDB with both Redis and Bolt protocols
docker run -d \
  --name falkordb \
  -p 6379:6379 \
  -p 7687:7687 \
  falkordb/falkordb:latest
```

**Option B: Neo4j**
```bash
# Neo4j Community Edition
docker run -d \
  --name neo4j \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=none \
  neo4j:latest
```

**Verify Database:**
```bash
# Test Redis protocol (LeanRAG)
redis-cli ping

# Test Bolt protocol (Graphiti)
# (requires neo4j-driver or similar)
```

## Running Tests

### Run All Tests (Requires Full Environment)
```bash
pytest tests/test_backend_smoke.py -v
```

### Run Only Basic Tests (No Database)
```bash
pytest tests/test_backend_smoke.py -v -k "healthcheck or prepare_only"
```

### Skip Specific Backends
```bash
# Skip LeanRAG indexing
export SKIP_LEANRAG_INDEX=1
pytest tests/test_backend_smoke.py -v

# Skip Graphiti indexing
export SKIP_GRAPHITI_INDEX=1
pytest tests/test_backend_smoke.py -v

# Skip backend comparison
export SKIP_BACKEND_COMPARISON=1
pytest tests/test_backend_smoke.py -v
```

### Mark-Based Filtering
```bash
# Run only integration tests
pytest -m integration_falkor

# Skip integration tests
pytest -m "not integration_falkor"
```

## Expected Results

### With Full Environment
```
7 tests collected:
- 4 basic tests (healthcheck, prepare_only) ✅
- 3 full pipeline tests ✅

Total time: <90 seconds
```

### Without Environment
```
7 tests collected:
- 4 basic tests ✅
- 3 full pipeline tests ❌ (environment errors)

Errors expected:
- ModuleNotFoundError: leanrag not installed
- ConnectionRefusedError: database not running
```

## Troubleshooting

### LeanRAG: "ModuleNotFoundError: No module named 'leanrag'"
**Fix:** Install LeanRAG submodule
```bash
pip install -e external/LeanRAG
```

### Graphiti: "ConnectionRefusedError: Connect call failed ('127.0.0.1', 7687)"
**Fix:** Start FalkorDB or Neo4j on bolt port 7687
```bash
docker run -p 7687:7687 -p 6379:6379 falkordb/falkordb:latest
```

### Graphiti: "ConfigError: OPENAI_API_KEY is required"
**Fix:** Set OpenAI API key
```bash
export OPENAI_API_KEY="sk-..."
```

### LeanRAG: Wrong bolt port
**Note:** LeanRAG can use either:
- Redis protocol on port 6379 (preferred)
- Bolt protocol on port 7687

Default config uses Redis port 6379.

### Graphiti: Wrong bolt port
**Note:** Graphiti requires bolt protocol on port 7687 (not Redis protocol on 6379).

## Test Fixtures

### minimal_corpus
- 2 threads (auth-feature, payment-feature)
- 5 entries total
- Realistic content with OAuth2, Stripe examples
- Small enough for fast execution

### minimal_chunks
- 5 chunks derived from minimal_corpus
- Token counts, hash codes included
- Mapped to thread/entry metadata

### sample_queries
- 2 queries about authentication and payments
- Limit of 3 results per query

## Performance Targets

- **Basic tests**: <1 second
- **Full pipeline tests**: <90 seconds total
- **Individual backend**: <45 seconds

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Install test dependencies
  run: |
    pip install -e ".[dev]"
    pip install -e external/LeanRAG
    pip install -e external/graphiti

- name: Start FalkorDB
  run: |
    docker run -d -p 6379:6379 -p 7687:7687 falkordb/falkordb:latest
    sleep 5  # Wait for startup

- name: Run smoke tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: pytest tests/test_backend_smoke.py -v
```

## Architecture Notes

### Why Two Backends?

- **LeanRAG**: Subprocess-based, entity extraction, hierarchical clustering
- **Graphiti**: Library-based, episodic memory, temporal graphs

Testing both validates:
1. Contract works for subprocess execution model
2. Contract works for library API model
3. Async wrapping strategy works correctly
4. Registry handles import failures gracefully

### Test Database Isolation

Both backends support `test_mode=True` for CI/test environments to prevent database pollution:

**LeanRAG:**
- Applies `pytest__` prefix to work_dir basename
- Example: `leanrag_work` → `pytest__leanrag_work` (database name)
- Configured via: `LeanRAGConfig(work_dir=path, test_mode=True)`

**Graphiti:**
- Applies `pytest__` prefix to group_id (database name)
- Example: `thread_name` → `pytest__thread_name` (after sanitization)
- Configured via: `GraphitiConfig(work_dir=path, test_mode=True)`

**Automatic Cleanup:**
- Session-scoped fixture runs **before** tests
- Removes all databases with `pytest__` prefix
- Allows post-test inspection in database UI
- Next test run cleans up previous results

**Production Usage:**
- NEVER set `test_mode=True` in production
- Production databases have clean names without prefixes
- Unit tests verify prefix NOT applied when `test_mode=False`

### Contract vs Integration

- **Contract tests** (`test_memory_backend_contract.py`): Fast, no databases, validate API
- **Smoke tests** (`test_backend_smoke.py`): Real databases, validate full workflows

Both are essential for comprehensive validation.

## CI/CD Configuration

### Timeout Recommendations

**Test Markers:**
- Graphiti integration tests use `@pytest.mark.integration_leanrag_llm` marker
- LeanRAG integration tests may use similar markers
- CI workflow excludes these markers: `-m "not integration_falkor and not integration_leanrag_llm"`

**Timeout Configuration:**
```yaml
# .github/workflows/ci.yml
jobs:
  test:
    timeout-minutes: 20  # Adjust based on test suite runtime
    steps:
      - name: Run tests
        run: pytest tests/ -v -m "not integration_falkor and not integration_leanrag_llm"
        timeout-minutes: 15  # Per-step timeout
```

**Rationale:**
- Graphiti tests with real data can run 30+ minutes (15 entries ≈ 46 minutes)
- LeanRAG tests are much faster (66 entries ≈ 22 seconds)
- CI excludes long-running tests via markers to keep build times reasonable
- Local developers can run full integration tests with `pytest tests/ -v` (no markers)
