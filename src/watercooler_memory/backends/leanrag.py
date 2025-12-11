"""LeanRAG backend adapter for entity extraction and hierarchical graph RAG."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
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
class LeanRAGConfig:
    """Configuration for LeanRAG backend."""

    # LeanRAG submodule location
    leanrag_path: Path = Path("external/LeanRAG")

    # Database configuration
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379

    # LLM configuration (optional)
    llm_api_base: str | None = None
    llm_model: str | None = None

    # Embedding configuration (optional)
    embedding_api_base: str | None = None
    embedding_model: str | None = None

    # Working directory for exports
    work_dir: Path | None = None

    # Test mode: Add pytest__ prefix to database names for isolation
    test_mode: bool = False


class LeanRAGBackend(MemoryBackend):
    """
    LeanRAG adapter implementing MemoryBackend contract.

    LeanRAG provides:
    - Entity and relation extraction
    - Hierarchical semantic clustering (GMM + UMAP)
    - Multi-layer knowledge graph construction
    - Reduced redundancy (~46% vs flat baselines)

    This adapter wraps LeanRAG subprocess calls and maps to/from canonical payloads.
    """

    def __init__(self, config: LeanRAGConfig | None = None) -> None:
        self.config = config or LeanRAGConfig()
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration and LeanRAG availability."""
        if not self.config.leanrag_path.exists():
            raise ConfigError(
                f"LeanRAG not found at {self.config.leanrag_path}. "
                "Run: git submodule update --init external/LeanRAG"
            )

        process_script = self.config.leanrag_path / "leanrag/pipelines/process.py"
        if not process_script.exists():
            raise ConfigError(
                f"LeanRAG process script not found at {process_script}. "
                "Ensure LeanRAG submodule is properly initialized."
            )

    def prepare(self, corpus: CorpusPayload) -> PrepareResult:
        """
        Prepare corpus for LeanRAG ingestion.

        Maps canonical payload to LeanRAG's expected JSON format:
        - documents.json: Entries with content and metadata
        - threads.json: Thread metadata
        - threads_chunk.json: Chunks generated from provided entries
        - manifest.json: Export metadata
        """
        if self.config.work_dir:
            work_dir = self.config.work_dir
            work_dir.mkdir(parents=True, exist_ok=True)
        else:
            work_dir = Path(tempfile.mkdtemp(prefix="leanrag-prepare-"))
        
        # Convert to absolute path for reliability
        work_dir = work_dir.resolve()

        try:
            documents = [
                {
                    "id": entry.get("id"),
                    "thread_id": entry.get("thread_id"),
                    "title": entry.get("title"),
                    "content": entry.get("body", entry.get("content", "")),
                    "agent": entry.get("agent"),
                    "role": entry.get("role"),
                    "type": entry.get("type"),
                    "timestamp": entry.get("timestamp"),
                }
                for entry in corpus.entries
            ]

            threads = [
                {
                    "id": thread.get("id"),
                    "topic": thread.get("topic"),
                    "status": thread.get("status"),
                    "ball": thread.get("ball"),
                    "entry_count": thread.get("entry_count"),
                    "title": thread.get("title"),
                }
                for thread in corpus.threads
            ]

            chunks = self._extract_chunks_from_entries(corpus)

            (work_dir / "documents.json").write_text(json.dumps(documents, indent=2))
            (work_dir / "threads.json").write_text(json.dumps(threads, indent=2))
            (work_dir / "threads_chunk.json").write_text(json.dumps(chunks, indent=2))

            manifest = {
                "format": "leanrag-corpus",
                "version": "1.0",
                "source": "watercooler-cloud",
                "memory_payload_version": corpus.manifest_version,
                "chunker": {
                    "name": corpus.chunker_name,
                    "params": corpus.chunker_params,
                },
                "statistics": {
                    "threads": len(corpus.threads),
                    "entries": len(corpus.entries),
                    "chunks": len(chunks),
                },
                "files": {
                    "documents": "documents.json",
                    "threads": "threads.json",
                    "chunks": "threads_chunk.json",
                },
            }
            (work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

            return PrepareResult(
                manifest_version=corpus.manifest_version,
                prepared_count=len(documents),
                message=f"Prepared corpus at {work_dir}",
            )
        except Exception as exc:
            raise BackendError(f"Failed to prepare corpus: {exc}") from exc

    def _extract_chunks_from_entries(
        self, corpus: CorpusPayload
    ) -> list[dict[str, Any]]:
        """
        Extract chunks from all entries for LeanRAG query pipeline.

        Creates threads_chunk.json with format:
        [{"hash_code": "...", "text": "..."}, ...]
        """
        import hashlib

        chunks: list[dict[str, Any]] = []
        for entry in corpus.entries:
            entry_chunks = entry.get("chunks", [])

            if not entry_chunks:
                full_text = f"# {entry.get('title', '')}\n\n{entry.get('body', '')}"
                hash_code = hashlib.md5(full_text.encode()).hexdigest()
                chunks.append({"hash_code": hash_code, "text": full_text})
                continue

            for chunk in entry_chunks:
                if isinstance(chunk, str):
                    chunk_text = chunk
                elif isinstance(chunk, dict):
                    chunk_text = chunk.get("text", chunk.get("content", str(chunk)))
                else:
                    chunk_text = str(chunk)

                hash_code = hashlib.md5(chunk_text.encode()).hexdigest()
                chunks.append({"hash_code": hash_code, "text": chunk_text})

        return chunks

    def _ensure_chunk_file(self, work_dir: Path, chunks: ChunkPayload) -> Path:
        """Ensure threads_chunk.json exists in the working directory."""
        chunk_file = work_dir / "threads_chunk.json"
        if chunk_file.exists():
            return chunk_file

        serialized = []
        for item in chunks.chunks:
            text = item.get("text", item.get("content", ""))
            hash_code = item.get("hash_code") or item.get("id") or item.get("chunk_id")
            if not hash_code:
                import hashlib

                hash_code = hashlib.md5(text.encode()).hexdigest()
            serialized.append({"hash_code": hash_code, "text": text})

        chunk_file.write_text(json.dumps(serialized, indent=2))
        return chunk_file

    def index(self, chunks: ChunkPayload) -> IndexResult:
        """
        Run LeanRAG entity extraction and graph building.

        Executes LeanRAG pipeline:
        1. triple_extraction (bypasses LeanRAG chunking)
        2. build.py to construct hierarchical graph
        """
        work_dir = self.config.work_dir or Path(tempfile.mkdtemp(prefix="leanrag-index-"))
        work_dir.mkdir(parents=True, exist_ok=True)
        
        # Convert to absolute path so it works when we change directories
        work_dir = work_dir.resolve()

        try:
            chunk_file = self._ensure_chunk_file(work_dir, chunks)

            leanrag_abspath = self.config.leanrag_path.resolve()
            if str(leanrag_abspath) not in sys.path:
                sys.path.insert(0, str(leanrag_abspath))

            with open(chunk_file, "r") as fh:
                corpus = json.load(fh)
            chunks_dict = {item["hash_code"]: item["text"] for item in corpus}

            original_cwd = os.getcwd()
            try:
                os.chdir(str(self.config.leanrag_path))

                from leanrag.extraction.chunk import triple_extraction
                from leanrag.core.llm import generate_text_async

                asyncio.run(
                    triple_extraction(
                        chunks_dict, generate_text_async, str(work_dir), save_filtered=False
                    )
                )
            finally:
                os.chdir(original_cwd)

            build_cmd = [
                "python3",
                "leanrag/pipelines/build.py",
                "--path",
                str(work_dir),
                "--num",
                "2",
            ]

            env = os.environ.copy()
            env["PYTHONPATH"] = str(leanrag_abspath) + os.pathsep + env.get("PYTHONPATH", "")

            print(f"Running LeanRAG graph building: {' '.join(build_cmd)}")
            
            build_result = subprocess.run(
                build_cmd,
                check=True,
                # Don't capture output - let it stream to console so user can see progress
                timeout=1800,  # 30 minutes for build.py (community summaries via LLM)
                cwd=str(self.config.leanrag_path),
                env=env,
            )
            
            print(f"Graph building complete")

            return IndexResult(
                manifest_version=chunks.manifest_version,
                indexed_count=len(chunks.chunks),
                message=f"Indexed {len(chunks.chunks)} chunks via LeanRAG at {work_dir}",
            )
        except subprocess.TimeoutExpired as exc:
            stderr_tail = exc.stderr[-500:] if exc.stderr else ""
            raise TransientError(
                f"LeanRAG pipeline timed out after {exc.timeout}s. "
                f"Command: {' '.join(exc.cmd)}. "
                f"Stderr: {stderr_tail}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr_tail = exc.stderr[-500:] if exc.stderr else ""
            raise BackendError(
                f"LeanRAG pipeline failed with exit code {exc.returncode}. "
                f"Command: {' '.join(exc.cmd)}. "
                f"Stderr: {stderr_tail}"
            ) from exc
        except FileNotFoundError as exc:
            raise ConfigError(
                f"Required LeanRAG files not found: {exc}. "
                "Ensure LeanRAG submodule is initialized and prepared has been run."
            ) from exc
        except Exception as exc:
            raise BackendError(f"Unexpected error during index: {exc}") from exc

    def query(self, query: QueryPayload) -> QueryResult:
        """
        Execute queries against LeanRAG graph by calling query_graph directly.
        """
        work_dir = self.config.work_dir or Path(tempfile.mkdtemp(prefix="leanrag-query-"))
        # Convert to absolute path for reliability
        work_dir = work_dir.resolve()
        
        if not (work_dir / "threads_chunk.json").exists():
            raise ConfigError(
                f"threads_chunk.json not found in {work_dir}. "
                "Run prepare() and index() before querying."
            )

        try:
            leanrag_abspath = self.config.leanrag_path.resolve()
            if str(leanrag_abspath) not in sys.path:
                sys.path.insert(0, str(leanrag_abspath))

            original_cwd = os.getcwd()
            try:
                os.chdir(str(self.config.leanrag_path))

                from leanrag.pipelines.query import query_graph
                from leanrag.core.llm import embedding, generate_text

                results: list[dict[str, Any]] = []
                for q in query.queries:
                    query_text = q.get("query", q.get("text", ""))
                    topk = q.get("limit", q.get("topk", 5))
                    if not query_text:
                        continue

                    global_config = {
                        "working_dir": str(work_dir),
                        "chunks_file": str(work_dir / "threads_chunk.json"),
                        "embeddings_func": embedding,
                        "use_llm_func": generate_text,
                        "topk": topk,
                        "level_mode": 1,
                    }

                    context, answer = query_graph(global_config, None, query_text)
                    results.append(
                        {
                            "query": query_text,
                            "answer": answer,
                            "context": context,
                            "topk": topk,
                        }
                    )

                    if answer:
                        print(f"Query answer: {answer[:200]}...")
            finally:
                os.chdir(original_cwd)

            return QueryResult(
                manifest_version=query.manifest_version,
                results=results,
                message=f"Executed {len(results)} queries via LeanRAG",
            )
        except Exception as exc:
            raise BackendError(f"Unexpected error during query: {exc}") from exc

    def healthcheck(self) -> HealthStatus:
        """
        Check LeanRAG and database health.
        """
        try:
            self._validate_config()

            try:
                import redis

                redis.Redis(
                    host=self.config.falkordb_host,
                    port=self.config.falkordb_port,
                    socket_connect_timeout=2,
                ).ping()
                db_status = "FalkorDB: connected"
            except ImportError:
                db_status = "FalkorDB: redis-py not installed"
            except (redis.ConnectionError, redis.TimeoutError) as exc:
                db_status = f"FalkorDB: unreachable ({exc})"

            return HealthStatus(
                ok=True,
                details=f"LeanRAG available at {self.config.leanrag_path}, {db_status}",
            )
        except ConfigError as exc:
            return HealthStatus(ok=False, details=str(exc))
        except Exception as exc:
            return HealthStatus(ok=False, details=f"Health check failed: {exc}")

    def get_capabilities(self) -> Capabilities:
        """Return LeanRAG capabilities."""
        return Capabilities(
            embeddings=bool(self.config.embedding_api_base),
            entity_extraction=True,
            graph_query=True,
            rerank=False,
            schema_versions=["1.0.0"],
            supports_falkor=True,
            supports_milvus=bool(self.config.embedding_api_base),
            supports_neo4j=False,
            max_tokens=1024,
        )
