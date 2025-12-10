"""Graphiti backend adapter for episodic memory and temporal graph RAG."""

from __future__ import annotations

import asyncio
import json
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

    # Working directory for exports
    work_dir: Path | None = None


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

    def _map_entries_to_episodes(
        self, corpus: CorpusPayload
    ) -> list[dict[str, Any]]:
        """Map canonical entries to Graphiti episode format."""
        episodes = []

        for entry in corpus.entries:
            # Graphiti episode format:
            # - name: Episode identifier/title
            # - episode_body: Content
            # - source_description: Metadata about source
            # - reference_time: ISO timestamp

            episode = {
                "name": entry.get("title", f"Entry {entry.get('id')}"),
                "episode_body": entry.get("body", entry.get("content", "")),
                "source_description": self._format_source_description(entry),
                "reference_time": entry.get("timestamp"),
                "metadata": {
                    "entry_id": entry.get("id", entry.get("entry_id")),
                    "thread_id": entry.get("thread_id"),
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

            # Initialize Graphiti client with FalkorDB
            try:
                from graphiti_core import Graphiti
                from graphiti_core.driver.falkordb_driver import FalkorDriver
            except ImportError as e:
                raise ConfigError(
                    f"Graphiti dependencies not installed: {e}. "
                    "Run: pip install -e 'external/graphiti[falkordb]'"
                ) from e

            # Create Graphiti client with FalkorDB connection
            try:
                falkor_driver = FalkorDriver(
                    host=self.config.falkordb_host,
                    port=self.config.falkordb_port,
                    username=self.config.falkordb_username,
                    password=self.config.falkordb_password,
                )
                graphiti = Graphiti(graph_driver=falkor_driver)
            except Exception as e:
                raise TransientError(f"Database connection failed: {e}") from e

            # Ingest episodes sequentially (async operation wrapped in sync)
            async def ingest_episodes():
                count = 0
                for episode in episodes:
                    try:
                        await graphiti.add_episode(
                            name=episode["name"],
                            episode_body=episode["episode_body"],
                            source_description=episode["source_description"],
                            reference_time=episode["reference_time"],
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
        Query Graphiti temporal graph.

        Executes hybrid search:
        - Semantic similarity search
        - Graph traversal for related entities
        - Temporal filtering

        Args:
            query: Query payload with search queries

        Returns:
            QueryResult with ranked results

        Raises:
            BackendError: If query fails
        """
        try:
            # Initialize Graphiti client with FalkorDB
            try:
                from graphiti_core import Graphiti
                from graphiti_core.driver.falkordb_driver import FalkorDriver
            except ImportError as e:
                raise ConfigError(
                    f"Graphiti dependencies not installed: {e}. "
                    "Run: pip install -e 'external/graphiti[falkordb]'"
                ) from e

            # Create Graphiti client with FalkorDB connection
            try:
                falkor_driver = FalkorDriver(
                    host=self.config.falkordb_host,
                    port=self.config.falkordb_port,
                    username=self.config.falkordb_username,
                    password=self.config.falkordb_password,
                )
                graphiti = Graphiti(graph_driver=falkor_driver)
            except Exception as e:
                raise TransientError(f"Database connection failed: {e}") from e

            # Execute queries (async operation wrapped in sync)
            async def execute_queries():
                results = []
                for query_item in query.queries:
                    query_text = query_item.get("query", "")
                    limit = query_item.get("limit", 10)

                    try:
                        # Graphiti search is async
                        search_results = await graphiti.search(
                            query=query_text,
                            num_results=limit,
                        )

                        # Map Graphiti results to canonical format
                        for result in search_results:
                            results.append({
                                "query": query_text,
                                "content": result.get("content", ""),
                                "score": result.get("score", 0.0),
                                "metadata": result.get("metadata", {}),
                            })

                    except Exception as e:
                        raise BackendError(
                            f"Query '{query_text}' failed: {e}"
                        ) from e
                return results

            all_results = asyncio.run(execute_queries())

            return QueryResult(
                manifest_version=query.manifest_version,
                results=all_results,
                message=f"Executed {len(query.queries)} queries, returned {len(all_results)} results",
            )

        except ConfigError:
            raise
        except TransientError:
            raise
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(f"Query failed: {e}") from e

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
