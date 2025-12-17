"""Graphiti backend adapter for episodic memory and temporal graph RAG."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import (
    BackendError,
    Capabilities,
    ChunkPayload,
    ConfigError,
    CorpusPayload,
    HealthStatus,
    IndexResult,
    MemoryBackend,
    PrepareResult,
    QueryPayload,
    QueryResult,
    TransientError,
)


@dataclass
class GraphitiConfig:
    """Configuration for Graphiti backend."""

    # Graphiti submodule location
    graphiti_path: Path = Path("external/graphiti")

    # Database configuration (FalkorDB)
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_username: str | None = None  # FalkorDB doesn't require auth
    falkordb_password: str | None = None

    # LLM configuration (required for Graphiti)
    openai_api_key: str | None = None
    openai_api_base: str | None = None  # Optional for alt endpoints
    openai_model: str | None = None

    # Embedding configuration
    embedding_model: str = "text-embedding-3-small"

    # Search reranker algorithm (rrf, mmr, cross_encoder, node_distance, episode_mentions)
    # RRF (Reciprocal Rank Fusion) is fast and provides good results for most cases
    reranker: str = "rrf"

    # Working directory for exports
    work_dir: Path | None = None

    # Test mode: Add pytest__ prefix to database names for isolation
    test_mode: bool = False


class GraphitiBackend(MemoryBackend):
    """
    Graphiti adapter implementing MemoryBackend contract.

    Graphiti provides:
    - Episodic ingestion (one episode per entry)
    - Temporal entity tracking with time-aware edges
    - Automatic fact extraction and deduplication
    - Hybrid search (semantic + graph traversal)
    - Chronological reasoning

    This adapter wraps Graphiti API calls and maps to/from canonical payloads.
    """

    # Maximum length for body snippet fallback in episode names
    # (50 chars provides enough context without bloating database keys or UI displays)
    _MAX_FALLBACK_NAME_LENGTH = 50

    # Maximum database name length (Redis/FalkorDB key size limit of 512 bytes,
    # we use 64 chars conservatively to allow for UTF-8 multi-byte characters)
    _MAX_DB_NAME_LENGTH = 64

    # Length of test database prefix (pytest__) for test isolation
    _TEST_PREFIX_LENGTH = len("pytest__")  # 8 characters

    # Maximum episode content length to include in query results (8KB)
    # Episodes can be large (multi-KB watercooler entries), so we truncate
    # to keep response sizes manageable while providing sufficient context for RAG
    _MAX_EPISODE_CONTENT_LENGTH = 8192

    # Maximum node summary length (2KB - shorter than episodes)
    # Node summaries are regional consolidations that can be verbose,
    # truncate to prevent payload bloat per Codex feedback
    _MAX_NODE_SUMMARY_LENGTH = 2048

    def __init__(self, config: GraphitiConfig | None = None) -> None:
        self.config = config or GraphitiConfig()
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration and Graphiti availability."""
        if not self.config.graphiti_path.exists():
            raise ConfigError(
                f"Graphiti not found at {self.config.graphiti_path}. "
                "Run: git submodule update --init external/graphiti"
            )

        # Check for required Graphiti module
        graphiti_core = self.config.graphiti_path / "graphiti_core"
        if not graphiti_core.exists():
            raise ConfigError(
                f"Graphiti core not found at {graphiti_core}. "
                "Ensure Graphiti submodule is properly initialized."
            )

        # Validate OpenAI API key is set (required for Graphiti)
        if not self.config.openai_api_key:
            import os

            self.config.openai_api_key = os.environ.get("OPENAI_API_KEY")
            if not self.config.openai_api_key:
                raise ConfigError(
                    "OPENAI_API_KEY is required for Graphiti. "
                    "Set via config or environment variable."
                )

    def prepare(self, corpus: CorpusPayload) -> PrepareResult:
        """
        Prepare corpus for Graphiti ingestion.

        Maps canonical payload to Graphiti's episodic format:
        - Each entry becomes an episode
        - Episodes include: name, content, source, timestamp

        Args:
            corpus: Canonical corpus with threads, entries, edges

        Returns:
            PrepareResult with prepared count and export location
        """
        # Create working directory
        if self.config.work_dir:
            work_dir = self.config.work_dir
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            work_dir = Path(tempfile.mkdtemp(prefix="graphiti-prepare-"))

        try:
            # Map corpus to Graphiti episodes format
            episodes = self._map_entries_to_episodes(corpus)

            # Write episodes file
            episodes_path = work_dir / "episodes.json"
            episodes_path.write_text(json.dumps(episodes, indent=2))

            # Write manifest
            manifest_path = work_dir / "manifest.json"
            manifest = {
                "format": "graphiti-episodes",
                "version": "1.0",
                "source": "watercooler-cloud",
                "memory_payload_version": corpus.manifest_version,
                "chunker": {
                    "name": corpus.chunker_name,
                    "params": corpus.chunker_params,
                },
                "statistics": {
                    "threads": len(corpus.threads),
                    "episodes": len(episodes),
                },
                "files": {
                    "episodes": "episodes.json",
                },
            }
            manifest_path.write_text(json.dumps(manifest, indent=2))

            return PrepareResult(
                manifest_version=corpus.manifest_version,
                prepared_count=len(episodes),
                message=f"Prepared {len(episodes)} episodes at {work_dir}",
            )

        except Exception as e:
            raise BackendError(f"Failed to prepare corpus: {e}") from e

    def _sanitize_redisearch_operators(self, text: str) -> str:
        """Sanitize RediSearch operator characters in text.

        Replaces special characters that RediSearch interprets as query operators
        with safe alternatives to prevent syntax errors during entity extraction.

        This is a workaround for Graphiti's fulltext search not properly escaping
        entity names containing RediSearch operators (/, |, (), etc.) during
        entity deduplication searches.

        Args:
            text: Input text that may contain RediSearch operators

        Returns:
            Sanitized text with operators replaced
        """
        if not text:
            return text

        # Map RediSearch operators to safe replacements (single-pass translation)
        # Based on lucene_sanitize() in graphiti_core/helpers.py:62-96
        # Using str.translate() for O(n) performance instead of O(n*m) with sequential replace()
        #
        # TODO: This is a workaround for Graphiti's fulltext search bypassing lucene_sanitize()
        # in entity deduplication. Track upstream fix at: https://github.com/getzep/graphiti
        translation_table = str.maketrans({
            '/': '-',      # Forward slash → dash
            '|': '-',      # Pipe → dash
            '(': ' ',      # Parentheses → space
            ')': ' ',
            '+': ' ',      # Plus → space
            '&': ' and ',  # Ampersand → word
            '!': ' ',      # Exclamation → space
            '{': ' ',      # Braces → space
            '}': ' ',
            '[': ' ',      # Brackets → space
            ']': ' ',
            '^': ' ',      # Caret → space
            '~': ' ',      # Tilde → space
            '*': ' ',      # Asterisk → space
            '?': ' ',      # Question mark → space
            ':': ' ',      # Colon → space
            '\\': ' ',     # Backslash → space
            '@': ' ',      # At sign → space
            '<': ' ',      # Angle brackets → space
            '>': ' ',
            '=': ' ',      # Equals → space
            '`': ' ',      # Backtick → space
        })

        # Apply translation and collapse multiple spaces
        result = text.translate(translation_table)
        result = re.sub(r'\s+', ' ', result)

        return result.strip()

    def _create_graphiti_client(self) -> Any:
        """Create and configure Graphiti client with FalkorDB and LLM.

        Returns:
            Configured Graphiti instance ready for operations.

        Raises:
            ConfigError: If required dependencies are not installed.
        """
        try:
            from graphiti_core import Graphiti
            from graphiti_core.driver.falkordb_driver import FalkorDriver
            from graphiti_core.llm_client import OpenAIClient
            from graphiti_core.llm_client.config import LLMConfig
        except ImportError as e:
            raise ConfigError(
                f"Graphiti dependencies not installed: {e}. "
                "Run: pip install -e 'external/graphiti[falkordb]'"
            ) from e

        # Create FalkorDB driver
        falkor_driver = FalkorDriver(
            host=self.config.falkordb_host,
            port=self.config.falkordb_port,
            username=self.config.falkordb_username,
            password=self.config.falkordb_password,
        )

        # Configure LLM client with explicit model
        model_name = self.config.openai_model or "gpt-4o-mini"
        llm_config = LLMConfig(
            api_key=self.config.openai_api_key,
            model=model_name,
            base_url=self.config.openai_api_base,
        )
        llm_client = OpenAIClient(
            config=llm_config,
            reasoning=None,  # Disable reasoning.effort (only for GPT-5 models)
            verbosity=None,  # Disable text.verbosity (unsupported by gpt-4o-mini)
        )

        return Graphiti(graph_driver=falkor_driver, llm_client=llm_client)

    def _get_search_config(self) -> Any:
        """Get SearchConfig based on configured reranker algorithm.

        Returns:
            SearchConfig instance for multi-layer hybrid search.
            COMBINED configs populate edges, episodes, nodes, and communities
            for comprehensive RAG with full episode content.

        Raises:
            ConfigError: If reranker name is invalid
        """
        try:
            from graphiti_core.search.search_config_recipes import (
                COMBINED_HYBRID_SEARCH_RRF,
                COMBINED_HYBRID_SEARCH_MMR,
                COMBINED_HYBRID_SEARCH_CROSS_ENCODER,
                EDGE_HYBRID_SEARCH_NODE_DISTANCE,
                EDGE_HYBRID_SEARCH_EPISODE_MENTIONS,
            )
        except ImportError as e:
            raise ConfigError(
                f"Graphiti search config not available: {e}. "
                "Ensure graphiti_core is properly installed."
            ) from e

        # Map reranker names to SearchConfig objects
        # Use COMBINED configs for rrf/mmr/cross_encoder to get episodes + nodes + communities
        # node_distance and episode_mentions remain edge-focused (no COMBINED variants)
        reranker_configs = {
            "rrf": COMBINED_HYBRID_SEARCH_RRF,
            "mmr": COMBINED_HYBRID_SEARCH_MMR,
            "cross_encoder": COMBINED_HYBRID_SEARCH_CROSS_ENCODER,
            "node_distance": EDGE_HYBRID_SEARCH_NODE_DISTANCE,
            "episode_mentions": EDGE_HYBRID_SEARCH_EPISODE_MENTIONS,
        }

        reranker = self.config.reranker.lower()
        if reranker not in reranker_configs:
            valid_options = ", ".join(reranker_configs.keys())
            raise ConfigError(
                f"Invalid reranker '{reranker}'. "
                f"Valid options: {valid_options}"
            )

        return reranker_configs[reranker]

    def _sanitize_thread_id(self, thread_id: str) -> str:
        """Sanitize thread ID for use as Graphiti group_id.

        With RediSearch escaping now handled in FalkorDB driver (external/graphiti),
        we only need minimal sanitization to remove truly problematic characters.
        
        Preserves hyphens and underscores for readability and provenance.

        Sanitization rules:
        - Remove control characters and null bytes
        - Strip leading/trailing whitespace
        - Ensure non-empty (defaults to "unknown")
        - Ensure starts with letter (prepends "t_" if needed, following FalkorDB best practice)
        - Enforce maximum length (64 chars, minus pytest__ prefix space if needed)
        - Add pytest__ prefix if in test mode

        Args:
            thread_id: Original thread identifier (e.g., "memory-backend.md")

        Returns:
            Sanitized group_id with pytest__ prefix if test_mode=True
            
        Examples:
            "memory-backend.md" → "memory-backend.md"
            "123-test" → "t_123-test"
            "  spaces  " → "spaces"
        """
        # Remove control characters and null bytes (keep printable chars including hyphens/underscores)
        sanitized = ''.join(c for c in thread_id if c.isprintable() and c != '\x00')
        
        # Strip whitespace from edges
        sanitized = sanitized.strip()
        
        # Ensure non-empty
        if not sanitized:
            sanitized = "unknown"
            
        # Ensure starts with letter (FalkorDB best practice)
        if not sanitized[0].isalpha():
            sanitized = "t_" + sanitized
        
        # Apply length limit (reserve space for pytest__ prefix if in test mode)
        max_len = self._MAX_DB_NAME_LENGTH - (self._TEST_PREFIX_LENGTH if self.config.test_mode else 0)
        if len(sanitized) > max_len:
            sanitized = sanitized[:max_len]
        
        # Add pytest__ prefix for test database identification (if in test mode)
        if self.config.test_mode:
            # Don't duplicate prefix if already present
            if not sanitized.startswith("pytest__"):
                sanitized = "pytest__" + sanitized

        return sanitized

    def _truncate_episode_content(
        self, content: str, max_length: int | None = None
    ) -> str:
        """Truncate episode content to maximum length with ellipsis marker.

        Args:
            content: Episode content to truncate
            max_length: Maximum character length (default: _MAX_EPISODE_CONTENT_LENGTH)

        Returns:
            Truncated content with "...[truncated]" marker if needed

        Example:
            >>> backend._truncate_episode_content("Short text")
            'Short text'
            >>> backend._truncate_episode_content("A" * 10000)
            'AAA...[truncated]'  # Truncated to 8192 chars
        """
        if max_length is None:
            max_length = self._MAX_EPISODE_CONTENT_LENGTH

        if len(content) <= max_length:
            return content

        return content[:max_length] + "\n...[truncated]"

    def _truncate_node_summary(self, summary: str | None) -> str | None:
        """Truncate node summary to prevent payload bloat.

        Args:
            summary: Node summary to truncate (may be None)

        Returns:
            Truncated summary with marker if needed, or None if input was None

        Example:
            >>> backend._truncate_node_summary(None)
            None
            >>> backend._truncate_node_summary("Short summary")
            'Short summary'
            >>> backend._truncate_node_summary("A" * 3000)
            'AAA...[truncated]'  # Truncated to 2048 chars
        """
        if not summary:
            return None

        if len(summary) <= self._MAX_NODE_SUMMARY_LENGTH:
            return summary

        return summary[:self._MAX_NODE_SUMMARY_LENGTH] + "...[truncated]"

    def _map_entries_to_episodes(
        self, corpus: CorpusPayload
    ) -> list[dict[str, Any]]:
        """Map canonical entries to Graphiti episode format with strict validation.

        Raises:
            BackendError: If entry missing required timestamp or both title and body
        """
        episodes = []

        for idx, entry in enumerate(corpus.entries):
            # Graphiti episode format:
            # - name: Episode identifier/title (required, cannot be None)
            # - episode_body: Content
            # - source_description: Metadata about source
            # - reference_time: datetime object (required, cannot be None)
            # - uuid: Entry ID for stable mapping
            # - group_id: Thread ID for per-thread partitioning

            # Get entry_id with fallback chain
            entry_id = entry.get("id") or entry.get("entry_id") or f"entry-{idx}"

            # STRICT: Fail fast on missing timestamp (temporal graph requirement)
            timestamp = entry.get("timestamp")
            if not timestamp:
                raise BackendError(
                    f"Entry '{entry_id}' missing required 'timestamp' field. "
                    "Temporal graph requires valid timestamps for all entries."
                )

            # Get name with body snippet fallback
            name = entry.get("title")
            body_text = entry.get("body", entry.get("content", ""))

            if not name:
                # Fallback to first N chars of body
                if body_text:
                    max_len = self._MAX_FALLBACK_NAME_LENGTH
                    name = (body_text[:max_len] + "...") if len(body_text) > max_len else body_text
                else:
                    raise BackendError(
                        f"Entry '{entry_id}' has neither 'title' nor 'body' content. "
                        "Cannot create episode with no name or content."
                    )

            # Get thread_id for group_id (sanitized for DB name)
            thread_id = entry.get("thread_id", "unknown")
            sanitized_thread = self._sanitize_thread_id(thread_id)

            # Embed entry_id in episode name for provenance
            # Format: "{entry_id}: {title/snippet}"
            episode_name = f"{entry_id}: {name}"

            episode = {
                "name": episode_name,
                "episode_body": self._sanitize_redisearch_operators(body_text),
                "source_description": self._format_source_description(entry),
                "reference_time": timestamp,
                "group_id": sanitized_thread,  # Per-thread partitioning
                "metadata": {
                    "entry_id": entry_id,
                    "thread_id": thread_id,
                    "agent": entry.get("agent"),
                    "role": entry.get("role"),
                    "type": entry.get("type"),
                },
            }
            episodes.append(episode)

        return episodes

    def _format_source_description(self, entry: dict[str, Any]) -> str:
        """Format entry metadata as source description."""
        agent = entry.get("agent", "Unknown")
        role = entry.get("role", "unknown")
        thread = entry.get("thread_id", "unknown")
        entry_type = entry.get("type", "Note")

        return f"Watercooler thread '{thread}' - {entry_type} by {agent} ({role})"

    def index(self, chunks: ChunkPayload) -> IndexResult:
        """
        Ingest episodes into Graphiti temporal graph.

        Uses Graphiti Python API to:
        1. Initialize Graphiti client
        2. Add episodes sequentially
        3. Extract entities and facts
        4. Build temporal graph in database

        Args:
            chunks: Chunk payload (contains episodes from prepare)

        Returns:
            IndexResult with indexed count

        Raises:
            BackendError: If ingestion fails
            TransientError: If database connection fails
        """
        if self.config.work_dir:
            work_dir = self.config.work_dir
        else:
            work_dir = Path(tempfile.mkdtemp(prefix="graphiti-index-"))

        try:
            # Load episodes from prepare() output
            episodes_path = work_dir / "episodes.json"
            if not episodes_path.exists():
                raise BackendError(
                    f"Episodes file not found at {episodes_path}. "
                    "Run prepare() first."
                )

            episodes = json.loads(episodes_path.read_text())

            # Create Graphiti client with FalkorDB connection
            try:
                graphiti = self._create_graphiti_client()
            except Exception as e:
                raise TransientError(f"Database connection failed: {e}") from e

            # Ingest episodes sequentially (async operation wrapped in sync)
            async def ingest_episodes():
                from datetime import datetime, timezone

                count = 0
                for episode in episodes:
                    try:
                        # Convert reference_time from ISO string to datetime object
                        ref_time_str = episode["reference_time"]
                        if isinstance(ref_time_str, str):
                            ref_time = datetime.fromisoformat(ref_time_str.replace('Z', '+00:00'))
                        else:
                            ref_time = ref_time_str  # Already a datetime

                        await graphiti.add_episode(
                            name=episode["name"],
                            episode_body=episode["episode_body"],
                            source_description=episode["source_description"],
                            reference_time=ref_time,
                            group_id=episode.get("group_id"),  # Per-thread partitioning
                        )
                        count += 1
                    except Exception as e:
                        raise BackendError(
                            f"Failed to add episode '{episode.get('name')}': {e}"
                        ) from e
                return count

            indexed_count = asyncio.run(ingest_episodes())

            return IndexResult(
                manifest_version=chunks.manifest_version,
                indexed_count=indexed_count,
                message=f"Indexed {indexed_count} episodes via Graphiti at {work_dir}",
            )

        except ConfigError:
            raise
        except TransientError:
            raise
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(f"Unexpected error during indexing: {e}") from e

    def query(self, query: QueryPayload) -> QueryResult:
        """
        Query Graphiti temporal graph with comprehensive multi-layer retrieval.

        Executes hybrid search across all four Graphiti subgraphs:
        - Edges: Extracted facts with bi-temporal tracking
        - Episodes: Full original content (non-lossy source data)
        - Nodes: Entity-centric summaries
        - Communities: Domain-level context clusters

        Args:
            query: Query payload with search queries

        Returns:
            QueryResult with:
            - results: List of edge-centric results, each containing:
                - content: Brief extracted fact (edge.fact)
                - score: Edge reranker relevance score (0.0-10.0+)
                - metadata:
                    - Edge identifiers (uuid, source_node_uuid, target_node_uuid)
                    - Temporal tracking (valid_at, invalid_at)
                    - Backend provenance (source_backend, reranker)
                    - episodes: List of source episodes with:
                        - uuid, content (truncated to 8KB), score (episode relevance)
                        - source, source_description, valid_at, created_at, name
                        - NOTE: episode.score represents episode relevance, may differ
                          from edge.score (fact relevance). For fact-based ranking, use
                          edge scores. For content-based ranking, use episode scores.
                    - nodes: List of connected entities with:
                        - uuid, name, labels, summary (truncated to 2KB), created_at
                        - role (source/target), edge_uuid (for context stitching)
            - communities: Top 5 domain-level clusters (optional) with:
                - uuid, name, summary, score

        Scoring Precedence (Codex feedback):
            - Edge scores: Rank extracted facts by relevance to query
            - Episode scores: Rank source content by relevance to query
            - Use edge scores for fact-based RAG (precise facts)
            - Use episode scores for content-based RAG (rich context)
            - Both are valid strategies depending on use case

        Example Multi-Strategy RAG:
            1. Fact-based: Rank by edge scores, extract episodes for context
            2. Entity-based: Filter by node labels, use node summaries
            3. Topic-based: Group by communities, aggregate related content
            4. Content-based: Rank by episode scores, use episodes as primary source

        Raises:
            BackendError: If query fails
            TransientError: If database connection fails
            ConfigError: If configuration is invalid
        """
        try:
            # Create Graphiti client with FalkorDB connection
            try:
                graphiti = self._create_graphiti_client()
            except Exception as e:
                raise TransientError(f"Database connection failed: {e}") from e

            # Execute queries asynchronously
            async def execute_queries():
                results = []
                all_communities = []  # Collect communities across all queries
                for query_item in query.queries:
                    query_text = query_item.get("query", "")
                    limit = query_item.get("limit", 10)

                    # Extract optional topic for group_id filtering
                    topic = query_item.get("topic")
                    if topic:
                        # Sanitize topic to group_id format
                        group_ids = [self._sanitize_thread_id(topic)]
                    else:
                        # No topic specified - search across all available graphs
                        # List all graphs from FalkorDB
                        try:
                            import redis
                            r = redis.Redis(
                                host=self.config.falkordb_host,
                                port=self.config.falkordb_port,
                                password=self.config.falkordb_password,
                            )
                            graph_list = r.execute_command('GRAPH.LIST')
                            # Filter out default_db and decode bytes to strings
                            group_ids = [
                                g.decode() if isinstance(g, bytes) else g
                                for g in graph_list
                                if (g.decode() if isinstance(g, bytes) else g) != 'default_db'
                            ]
                        except Exception as e:
                            # If we can't list graphs, fall back to None (searches default_db)
                            group_ids = None

                    try:
                        # Get search config with configured reranker
                        search_config = self._get_search_config()
                        
                        # Handle single group_id case: @handle_multiple_group_ids decorator
                        # only activates for len(group_ids) > 1, so we need to manually
                        # clone the driver for single group_id queries
                        if group_ids and len(group_ids) == 1:
                            # Clone driver to point at the specific database
                            driver = graphiti.clients.driver.clone(database=group_ids[0])
                            search_results = await graphiti.search_(
                                query=query_text,
                                config=search_config,
                                group_ids=group_ids,
                                driver=driver,
                            )
                        else:
                            # Multiple group_ids or None - let decorator handle it
                            search_results = await graphiti.search_(
                                query=query_text,
                                config=search_config,
                                group_ids=group_ids,
                            )

                        # Map Graphiti SearchResults to canonical format
                        # search_results.edges contains EntityEdge models
                        # search_results.edge_reranker_scores contains scores (positionally aligned)
                        # search_results.episodes contains EpisodicNode models with full content

                        # Build episode index for efficient edge→episode lookup
                        # Episodes link to edges via episode.entity_edges (list of edge UUIDs)
                        # Note: Not all edges have linked episodes (some are inferred/derived facts)
                        episode_index: dict[str, list[Any]] = {}
                        for ep in search_results.episodes:
                            # entity_edges is a list of edge UUIDs that reference this episode
                            for edge_uuid in ep.entity_edges:
                                if edge_uuid not in episode_index:
                                    episode_index[edge_uuid] = []
                                episode_index[edge_uuid].append(ep)

                        # Build node index for efficient edge→node lookup
                        # Nodes are connected entities (source/target) for each edge
                        node_index: dict[str, Any] = {}
                        for node in search_results.nodes:
                            node_index[node.uuid] = node

                        # Build episode score index with defensive length checks
                        # Codex: defend against array length mismatches
                        episode_score_index: dict[str, float] = {}
                        num_episode_scores = len(search_results.episode_reranker_scores)
                        for idx, ep in enumerate(search_results.episodes):
                            # Use positional alignment but defend against array length mismatch
                            if idx < num_episode_scores:
                                episode_score_index[ep.uuid] = search_results.episode_reranker_scores[idx]
                            else:
                                # Default to 0.0 if scores missing (shouldn't happen but defend anyway)
                                episode_score_index[ep.uuid] = 0.0

                        # Return only top N results after reranking
                        # Graphiti already sorted edges by reranker score
                        for idx, edge in enumerate(search_results.edges[:limit]):
                            # Extract score (defaults to 0.0 if not available)
                            score = 0.0
                            if idx < len(search_results.edge_reranker_scores):
                                score = search_results.edge_reranker_scores[idx]

                            # Find episodes that contain this edge
                            source_episodes = episode_index.get(edge.uuid, [])

                            # Find connected nodes (entities) for this edge
                            # Codex: include edge UUID for context stitching
                            source_node = node_index.get(edge.source_node_uuid)
                            target_node = node_index.get(edge.target_node_uuid)

                            # Build nodes list with role and edge linkage
                            edge_nodes = []
                            if source_node:
                                edge_nodes.append({
                                    "uuid": source_node.uuid,
                                    "name": source_node.name,
                                    "labels": source_node.labels,
                                    "summary": self._truncate_node_summary(
                                        source_node.summary if hasattr(source_node, 'summary') else None
                                    ),
                                    "created_at": source_node.created_at.isoformat() if source_node.created_at else None,
                                    "role": "source",
                                    "edge_uuid": edge.uuid,
                                })
                            if target_node and target_node.uuid != (source_node.uuid if source_node else None):
                                # Avoid duplicates when source and target are the same node
                                edge_nodes.append({
                                    "uuid": target_node.uuid,
                                    "name": target_node.name,
                                    "labels": target_node.labels,
                                    "summary": self._truncate_node_summary(
                                        target_node.summary if hasattr(target_node, 'summary') else None
                                    ),
                                    "created_at": target_node.created_at.isoformat() if target_node.created_at else None,
                                    "role": "target",
                                    "edge_uuid": edge.uuid,
                                })

                            results.append({
                                "query": query_text,
                                "content": edge.fact,  # The fact/relationship text
                                "score": score,  # Actual reranker score
                                "metadata": {
                                    # Graphiti-specific IDs
                                    "uuid": edge.uuid,
                                    "source_node_uuid": edge.source_node_uuid,
                                    "target_node_uuid": edge.target_node_uuid,
                                    "valid_at": edge.valid_at.isoformat() if edge.valid_at else None,
                                    "invalid_at": edge.invalid_at.isoformat() if edge.invalid_at else None,
                                    "group_id": edge.group_id,
                                    # Backend provenance for cross-backend reranking
                                    "source_backend": "graphiti",
                                    "reranker": self.config.reranker.lower(),
                                    # Episode content (non-lossy source data)
                                    "episodes": [
                                        {
                                            "uuid": ep.uuid,
                                            "content": self._truncate_episode_content(ep.content),
                                            "score": episode_score_index.get(ep.uuid, 0.0),  # Episode relevance score
                                            "source": ep.source.value if hasattr(ep.source, 'value') else str(ep.source),
                                            "source_description": ep.source_description,
                                            "valid_at": ep.valid_at.isoformat() if ep.valid_at else None,
                                            "created_at": ep.created_at.isoformat() if hasattr(ep, 'created_at') and ep.created_at else None,
                                            "name": ep.name,
                                        }
                                        for ep in source_episodes
                                    ],
                                    # Connected nodes (entities) with summaries
                                    # Codex: include for entity-centric queries and context stitching
                                    "nodes": edge_nodes,
                                },
                            })

                        # Extract top 5 communities (domain-level clusters)
                        # Codex: limit to small top-k to prevent payload bloat
                        for idx, comm in enumerate(search_results.communities[:5]):
                            comm_dict = {
                                "uuid": comm.uuid if hasattr(comm, 'uuid') else None,
                                "name": comm.name if hasattr(comm, 'name') else f"Community {idx}",
                                "summary": comm.summary if hasattr(comm, 'summary') else None,
                            }
                            # Add score if available (positional alignment)
                            if idx < len(search_results.community_reranker_scores):
                                comm_dict["score"] = search_results.community_reranker_scores[idx]
                            else:
                                comm_dict["score"] = 0.0

                            # Add if not already present (avoid duplicates across queries)
                            if comm_dict not in all_communities:
                                all_communities.append(comm_dict)

                    except Exception as e:
                        raise BackendError(f"Query '{query_text}' failed: {e}") from e

                return results, all_communities

            # Run async query execution
            results, communities = asyncio.run(execute_queries())

            return QueryResult(
                manifest_version=query.manifest_version,
                results=results,
                communities=communities,
            )

        except ConfigError:
            raise
        except TransientError:
            raise
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(f"Query execution failed: {e}") from e

    def healthcheck(self) -> HealthStatus:
        """
        Check Graphiti and database health.

        Verifies:
        - Graphiti module is accessible
        - Neo4j/FalkorDB is reachable

        Returns:
            HealthStatus with availability and details
        """
        try:
            # Check Graphiti availability
            self._validate_config()

            # Check FalkorDB connectivity (via Redis protocol)
            try:
                import redis

                r = redis.Redis(
                    host=self.config.falkordb_host,
                    port=self.config.falkordb_port,
                    username=self.config.falkordb_username,
                    password=self.config.falkordb_password,
                    socket_connect_timeout=2,
                )
                r.ping()
                db_status = "FalkorDB: connected"
            except ImportError:
                db_status = "FalkorDB: redis-py not installed"
            except (redis.ConnectionError, redis.TimeoutError) as e:
                db_status = f"FalkorDB: unreachable ({e})"

            return HealthStatus(
                ok=True,
                details=f"Graphiti available at {self.config.graphiti_path}, {db_status}",
            )

        except ConfigError as e:
            return HealthStatus(ok=False, details=str(e))
        except Exception as e:
            return HealthStatus(ok=False, details=f"Health check failed: {e}")

    def get_capabilities(self) -> Capabilities:
        """
        Return Graphiti capabilities.

        Graphiti provides:
        - Embeddings: Yes (via OpenAI)
        - Entity extraction: Yes (automatic)
        - Graph query: Yes (temporal graph)
        - Rerank: No (hybrid search instead)
        """
        return Capabilities(
            embeddings=True,  # Always via OpenAI or compatible
            entity_extraction=True,  # Automatic fact extraction
            graph_query=True,  # Temporal graph queries
            rerank=False,  # Hybrid search, not explicit reranking
            schema_versions=["1.0.0"],
            supports_falkor=True,  # Primary target via FalkorDriver
            supports_milvus=False,  # Not used
            supports_neo4j=True,  # Graphiti also supports Neo4j
            max_tokens=None,  # No fixed limit
        )
