# hypergraph-integration — Thread
Status: CLOSED
Ball: Claude (caleb)
Topic: hypergraph-integration
Created: 2025-10-16T05:15:50Z

---
Entry: Codex (caleb) 2025-10-16T05:15:50Z
Type: Plan
Title: Planning: Integrate Hypergraph-of-Experience Retrieval with WCP

Goal
- Integrate a retrieval/analytics layer (hypergraph-of-experience, based on LeanRAG) without changing WCP storage semantics or colliding with Jay’s protocol/tools.

Principles
- Keep WCP (threads/entries/roles/ball) unchanged; treat entries as the canonical artifact.
- Add a separate module for retrieval/analytics (“experience graph”), living under a well-named subdir.
- Model a Card as an analytic overlay that references one or more existing entries.
- Make lenses/pluggable views first-class but optional (default behavior requires no config).

Proposed Directory & Module Boundary
- Subdir: src/experience_graph/
  - Rationale: clear separation from existing core; avoids naming collisions.
  - Alternative names considered: src/hypergraph/, src/retrieval/; choose `experience_graph` for clarity and generality.

Initial Module Structure (proposed)
- src/experience_graph/
  - __init__.py
  - card.py            (Card overlay model: id, entry_refs, features, tags, timestamps)
  - entry_ref.py       (Typed link to WCP entry: topic, entry_id/index, file path)
  - lenses/
    - __init__.py
    - semantic.py      (embeddings/similarity hooks — optional)
    - structural.py    (file/module mentions → clusters)
    - temporal.py      (release/sprint/epoch windows)
    - outcome.py       (success/failure/rollback signals)
    - bridge.py        (cross-area connectors)
    - role.py          (role-based aggregation)
  - pyramid.py         (Local/Bridge/Global bundling logic)
  - steering.py        (knobs: budgets, view mix, freshness/failure bias)
  - index.py           (indexing/lookup over entries/cards; pluggable backend)
  - adapters/
    - wcp_reader.py    (read WCP threads/entries via existing API)
  - api.py             (public API to fetch L/B/G bundles for tasks)

Data Model (concise)
- Entry (from WCP): canonical source of truth (no changes).
- EntryRef: { topic, entry_idx or stable id, path, anchors }
- Card (overlay): { card_id, entry_refs: [EntryRef], features, tags, lens_signals, created_at }
- Index store: in-memory to start; later JSON/SQLite as optional backends.

Retrieval Flow (L/B/G views)
1) Read entries via wcp_reader → normalize minimal features.
2) Apply selected lenses → produce clusters + signals.
3) Build steerable pyramid (Local/Bridge/Global) per query.
4) Return compact evidence pack: locals, bridges, globals (+ small temporal overlay).

Milestones
- M1: Skeleton module + Card/EntryRef models + WCP reader; simple structural/temporal lenses from existing metadata.
- M2: L/B/G bundling + steering defaults; in-memory index.
- M3: Optional tags/rationale extraction; basic semantic lens (if embeddings available).
- M4: API polish + docs + examples; opt‑in persistence backend.

Decisions to Validate
- Directory name: src/experience_graph/ (OK?)
- Card overlay references entries by stable index vs explicit header anchor (prefer stable index; keep anchor optional).
- Separate package vs submodule: start as submodule; revisit packaging once stable.

Next Actions
- Confirm directory name + boundary.
- Draft minimal dataclasses for Card and EntryRef.
- Implement wcp_reader to enumerate entries with metadata.
- Add structural + temporal lens prototypes.

Role: planner
Type: Plan

---
Entry: Codex (caleb) 2025-10-16T05:53:41Z
Type: Closure
Title: Closure: Mnemosyne kickoff plan and documentation index

Summary
This thread establishes the integration plan to add a retrieval/analytics layer (“hypergraph of experience”, inspired by LeanRAG) on top of the Watercooler Collaboration Protocol (WCP). WCP (threads/entries/roles/ball) remains unchanged and is the canonical store. The new work will live in a separate repository—mnemosyne—serving as the retrieval/indexing and analytics layer that reads WCP entries and produces task‑fit context bundles.

Goals
- Keep WCP storage semantics untouched; avoid collisions with existing tooling.
- Treat WCP entries as canonical artifacts; layer “cards” as analytic overlays that reference entries.
- Provide steerable, multi‑lens retrieval (Local / Bridge / Global) with sane defaults.
- Ship a minimal, composable Python library with optional backends and simple extension points.

Non‑Goals (initially)
- Modifying WCP file formats or CLI/MCP surface.
- Replacing team workflows or cloud sync strategy.
- Hard dependency on embeddings/vector DB; semantic lens is optional.

Concepts & Data Model
- Entry (from WCP): existing structured thread entry with metadata.
- EntryRef: typed reference to a specific WCP entry.
  - { topic: str, entry_index: int (stable within thread), path: Path, anchor?: str }
- Card (overlay): analytic object that references one or more entries to capture reasoning/context features.
  - { card_id: str, entry_refs: [EntryRef], tags: set[str], features: dict[str, Any], signals: dict[str, float], created_at: datetime }
- Index store: in‑memory initially; JSON/SQLite optional later.

Retrieval Model (inspired by LeanRAG)
- L/B/G views are retrieval‑time abstractions:
  - Local: fine‑grained entries/cards relevant to a query.
  - Bridge: connectors across subsystems revealing why A affected B.
  - Global: distilled summaries from clusters of related entries/cards.
- Multiple concurrent lenses re‑index the same entries without schema churn (no WCP changes).

Lenses (pluggable)
- Structural: file/module/service mentions → clusters.
- Temporal: release/sprint/epoch windows → slices.
- Outcome: success/failure/rollback signals (rules/logical cues).
- Role: planner/critic/implementer/tester/pm/scribe aggregations.
- Bridge: minimal connector sets across clusters.
- Semantic (optional): similarity over titles/bodies/tags (requires embeddings).

Steering (defaults first)
- Level budgets: counts for Local/Bridge/Global.
- View mix: which lenses to combine or weight.
- Bridge tightness: favor short vs richer connectors.
- Freshness vs canonical: recency tradeoff.
- Failure bias: emphasize “lessons learned” when debugging.
- Note: These are retrieval/indexing configs; WCP storage remains neutral.

Architecture (mnemosyne repo)
- Adapters: read WCP threads/entries with no write operations.
- Indexing: derive features/signals per lens; retain simple state for fast queries.
- Pyramid builder: assemble L/B/G bundles per query + small temporal overlay.
- Public API: return compact “evidence packs” (locals, bridges, globals) for humans/agents.

Initial API Sketch (Python)
```python
# src/mnemosyne/adapters/wcp_reader.py
class WCPReader:
    def list_threads(self) -> list[str]: ...
    def iter_entries(self, topic: str) -> Iterable[Entry]: ...

# src/mnemosyne/model.py
@dataclass
class EntryRef:
    topic: str
    entry_index: int
    path: Path
    anchor: str | None = None

@dataclass
class Card:
    card_id: str
    entry_refs: list[EntryRef]
    tags: set[str]
    features: dict[str, Any]
    signals: dict[str, float]
    created_at: datetime

# src/mnemosyne/lenses/base.py
class Lens(Protocol):
    def compute(self, entries: list[Entry]) -> LensResult: ...

# src/mnemosyne/pyramid.py
@dataclass
class SteeringConfig:
    local_budget: int = 5
    bridge_budget: int = 3
    global_budget: int = 2
    view_mix: dict[str, float] = field(default_factory=dict)
    freshness_bias: float = 0.5
    failure_bias: float = 0.3

class PyramidBuilder:
    def build(self, entries: list[Entry], lenses: list[Lens], cfg: SteeringConfig) -> EvidencePack: ...

# src/mnemosyne/api.py
class Mnemosyne:
    def __init__(self, reader: WCPReader, store: IndexStore | None = None): ...
    def build_index(self) -> None: ...
    def evidence_pack(self, query: Query, cfg: SteeringConfig | None = None) -> EvidencePack: ...
```

Index & Storage (phased)
- M1: in‑memory index; optional JSON snapshot for reproducibility.
- M3+: SQLite adapter behind IndexStore interface (optional persistence).
- Keep I/O minimal; prefer incremental rebuilds and deterministic outputs.

Security/Privacy
- No secrets; respect repo boundaries and .gitignore.
- Offline‑first; if embeddings are enabled, require explicit opt‑in and config.
- Avoid storing raw PII; derive signals/tags from existing entry text.

Implementation Milestones
- M1: Repo scaffold + minimal models (EntryRef, Card) + WCPReader + structural/temporal lenses + in‑memory index + basic docs.
- M2: L/B/G pyramid builder + steering defaults + evidence_pack API + examples.
- M3: Optional tags/rationale extraction + semantic lens (if embeddings) + JSON snapshot export/import.
- M4: SQLite adapter (optional) + docs site + integration examples against watercooler‑collab.

Repository Layout (mnemosyne)
```
mnemosyne/
  README.md
  pyproject.toml
  src/mnemosyne/
    __init__.py
    model.py
    api.py
    adapters/
      __init__.py
      wcp_reader.py
    lenses/
      __init__.py
      structural.py
      temporal.py
      outcome.py
      bridge.py
      role.py
      semantic.py  # optional
    pyramid.py
    steering.py
    index.py
  tests/
    test_entry_ref.py
    test_structural_lens.py
    test_pyramid.py
  examples/
    quickstart.ipynb
  docs/
    CONCEPTS.md
    API.md
  .github/workflows/ci.yml
  .pre-commit-config.yaml
```

Integration Notes
- Cards reference entries by stable entry index in the thread file; optional header anchors for human‑legible links.
- No writeback to watercooler threads; mnemosyne is a read‑only consumer.
- Evidence packs can include file/line pointers to entries, plus a small temporal overlay for “what changed when”.

Open Questions
- Stable IDs vs. entry indices: start with indices (stable per thread), consider hash‑based IDs later.
- What minimal tags/rationale should be recommended in WCP bodies to improve early lens quality?
- Should bridge detection be purely structural at first (file co‑mentions) or include temporal adjacency?

Next Steps
- Create mnemosyne repo with the layout above.
- Implement EntryRef/Card dataclasses and WCPReader.
- Add structural + temporal lens prototypes and a basic PyramidBuilder.
- Ship a README with a short example that runs against this repo’s .watercooler directory.

Pertaining Docs Index (absolute paths)
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/Watercooler_Hypergraph_of_Experience.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/README.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/STRUCTURED_ENTRIES.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/mcp-server.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/integration.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/api.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/USE_CASES.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/ENVIRONMENT_VARS.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/CLOUD_SYNC_STRATEGY.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/CLOUD_SYNC_ARCHITECTURE.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/TEMPLATES.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/AGENT_REGISTRY.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/QUICKSTART.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/TROUBLESHOOTING.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/CONTRIBUTING.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/FAQ.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/claude-collab.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/CLAUDE_CODE_SETUP.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/CLAUDE_DESKTOP_SETUP.md
- /media/caleb/Work_SATA_EXT4_4TB/home/caleb/Work/Personal/MostlyHarmless-AI/repo/watercooler-collab/docs/MIGRATION.md

Notes
- Excluded on purpose: Watercooler‑v3.md variant (vision doc) to avoid circular alignment assumption.
- Thread file (for provenance): .watercooler/hypergraph-integration.md

Status: closing this planning thread to hand off to mnemosyne repo initialization.

