# ADR 0001: Pluggable Memory Backend Contract

## Status

Proposed

## Context

We need a stable contract to integrate multiple memory backends (LeanRAG, Graphiti, future
adapters) while keeping watercooler core stdlib-only and file-based. Current LeanRAG integration
works but is tightly shaped to one backend and lacks a formal interface, schema versioning, and
capability negotiation. Graphiti has been added as a submodule and FalkorDB is available for both
adapters.

## Goals

- Define a single MemoryBackend contract for prepare/index/query/healthcheck using typed JSON/JSONL
  payloads.
- Enable multiple backends behind a registry; select one at runtime via config.
- Preserve loose coupling: no direct imports from backends into core; communicate via files or
  subprocesses.
- Support schema and capability versioning to prevent drift.
- Keep defaults simple: sync API, deterministic behavior, and graceful degradation.

## Non-goals

- Running multiple backends simultaneously (fan-out/multi-write) in v1.
- Deep feature parity between backends; capability flags describe what each can do.

## Decision

### Contract (sync API)

Define `MemoryBackend` (Protocol/ABC) in `src/watercooler_memory/backends/__init__.py` with:
- `prepare(corpus: CorpusPayload) -> PrepareResult`
- `index(chunks: ChunkPayload) -> IndexResult`
- `query(query: QueryPayload) -> QueryResult`
- `healthcheck() -> HealthStatus`
- `get_capabilities() -> Capabilities`

Notes:
- API is synchronous to simplify callers/tests; adapters may run subprocesses or blocking I/O.
- Adapters must be deterministic and side-effect free outside declared data directories.
- Errors should raise typed exceptions (e.g., BackendError, ConfigError, TransientError).

### Canonical payloads (JSON/JSONL)

Versioned schema `memory_payload_version: semver` in a manifest. Core payloads include:
- `threads`, `entries`, `chunks`, `embeddings`, `entities` (when present)
- Minimal required fields: ids (stable), text/content, timestamps (event_time, ingestion_time),
  relationships (contains/follows/references/mentions), metadata (agent, role, type, status, ball).
Adapters map from these payloads to their native ingest format. Schema versioning allows additive
fields; breaking changes bump MAJOR.

### Capability flags

`Capabilities` struct:
- `embeddings: bool`
- `entity_extraction: bool`
- `graph_query: bool`
- `rerank: bool`
- `schema_versions: list[str]` (supported payload versions)
- Optional: `max_tokens`, `supports_falkor`, `supports_milvus`, `supports_neo4j`

Watercooler uses capabilities to pick the best available features and degrade gracefully.

### Adapter boundary

- Keep core stdlib-only; adapters live in `src/watercooler_memory/backends/`.
- Adapters interact via files/JSON and subprocess or HTTP calls; no direct imports into core logic.
- Provide a registry/factory: load backend by name from config, validate capabilities vs requested
  features.

### Configuration boundary

- Watercooler config selects backend name and data paths.
- Backend-specific config lives with the adapter (e.g., LeanRAG config.yaml/env, Graphiti env).
- Document precedence: watercooler config does not override backend-specific files; env can override
  both where applicable.

### Testing strategy

- Contract tests against a null backend (pure in-process) to lock API and payload shape.
- Smoke tests per real adapter (LeanRAG, Graphiti) targeting FalkorDB with tiny fixtures; marked
  (e.g., `@pytest.mark.integration_falkor`) and off by default in CI unless env flag enables.
- Keep smoke runtime < 90s; heavier stacks (Milvus, Neo4j) remain gated.

### Versioning and pins

- Record backend pins in docs and setup guides:
  - LeanRAG submodule: 1ea1360caa50bec5531ac665d39a73bb152d8fb4 (heads/main)
  - Graphiti submodule: 1de752646a9557682c762b83a679d46ffc67e821 (heads/main)
- Document pins in `docs/LEANRAG_SETUP.md`, `docs/GRAPHITI_SETUP.md`, and note them in
  `docs/MEMORY.md` under Backend Adapters.

## Consequences

- Clear interface enables adding new adapters without touching core.
- Sync API keeps integration simple; if async is needed later, we can add optional async variants.
- Capability flags allow graceful degradation and schema negotiation.
- Marked smoke tests prevent CI bloat while still validating real integrations when enabled.

## Open Questions

- Do we need a formal async mirror of the contract in v1, or defer until a backend requires it?
- Should we standardize a retry/backoff policy in the contract or leave it to adapters?
- For Graphiti, should we target FalkorDB only for tests, or also support Neo4j as an alternate
  profile in the adapter?***
