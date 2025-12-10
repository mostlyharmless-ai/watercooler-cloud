"""Graph sync module for atomic updates after MCP writes.

This module provides functions to sync thread/entry data to the baseline graph
atomically after markdown writes. It integrates with the MCP write pipeline
to keep the graph in sync with markdown files.

Key functions:
- sync_entry_to_graph(): Upsert entry + thread nodes/edges after a write
- sync_thread_to_graph(): Full thread sync (for rebuilds)
- record_graph_sync_error(): Track sync failures for later reconciliation
- get_graph_sync_state(): Check current sync state
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from watercooler.baseline_graph.export import (
    entry_to_node,
    generate_edges,
    thread_to_node,
)
from watercooler.baseline_graph.parser import (
    ParsedEntry,
    ParsedThread,
    parse_thread_file,
)
from watercooler.baseline_graph.summarizer import create_summarizer_config

logger = logging.getLogger(__name__)


# ============================================================================
# Graph Sync State
# ============================================================================


@dataclass
class GraphSyncState:
    """State of graph synchronization for a thread."""

    status: str = "ok"  # ok, error, pending
    last_synced_entry_id: Optional[str] = None
    last_sync_at: Optional[str] = None
    error_message: Optional[str] = None
    entries_synced: int = 0


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _get_state_file(threads_dir: Path) -> Path:
    """Get path to graph sync state file."""
    graph_dir = threads_dir / "graph" / "baseline"
    return graph_dir / "sync_state.json"


def get_graph_sync_state(threads_dir: Path, topic: str) -> Optional[GraphSyncState]:
    """Get graph sync state for a topic.

    Args:
        threads_dir: Threads directory
        topic: Thread topic

    Returns:
        GraphSyncState or None if no state exists
    """
    state_file = _get_state_file(threads_dir)
    if not state_file.exists():
        return None

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        topic_state = data.get("topics", {}).get(topic)
        if topic_state:
            return GraphSyncState(
                status=topic_state.get("status", "ok"),
                last_synced_entry_id=topic_state.get("last_synced_entry_id"),
                last_sync_at=topic_state.get("last_sync_at"),
                error_message=topic_state.get("error_message"),
                entries_synced=topic_state.get("entries_synced", 0),
            )
    except Exception as e:
        logger.warning(f"Failed to read graph sync state: {e}")

    return None


def _update_graph_sync_state(
    threads_dir: Path,
    topic: str,
    state: GraphSyncState,
) -> None:
    """Update graph sync state for a topic.

    Uses atomic write (temp file + rename) to prevent corruption.

    Args:
        threads_dir: Threads directory
        topic: Thread topic
        state: New state
    """
    state_file = _get_state_file(threads_dir)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing state
    data: Dict[str, Any] = {"topics": {}, "last_updated": _now_iso()}
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Update topic state
    if "topics" not in data:
        data["topics"] = {}

    data["topics"][topic] = {
        "status": state.status,
        "last_synced_entry_id": state.last_synced_entry_id,
        "last_sync_at": state.last_sync_at,
        "error_message": state.error_message,
        "entries_synced": state.entries_synced,
    }
    data["last_updated"] = _now_iso()

    # Atomic write
    _atomic_write_json(state_file, data)


def record_graph_sync_error(
    threads_dir: Path,
    topic: str,
    entry_id: Optional[str],
    error: Exception,
) -> None:
    """Record a graph sync error for later reconciliation.

    Args:
        threads_dir: Threads directory
        topic: Thread topic
        entry_id: Entry ID that failed to sync (if known)
        error: The exception that occurred
    """
    existing = get_graph_sync_state(threads_dir, topic)
    state = GraphSyncState(
        status="error",
        last_synced_entry_id=existing.last_synced_entry_id if existing else None,
        last_sync_at=_now_iso(),
        error_message=str(error),
        entries_synced=existing.entries_synced if existing else 0,
    )
    _update_graph_sync_state(threads_dir, topic, state)
    logger.warning(f"Graph sync error recorded for {topic}: {error}")


# ============================================================================
# Atomic File Operations
# ============================================================================


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON file atomically using temp file + rename.

    Args:
        path: Target path
        data: Data to write as JSON
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".tmp_",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_append_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    """Append items to JSONL file atomically.

    This reads existing content, appends new items, and writes atomically.
    For incremental sync, we need to handle deduplication.

    Args:
        path: Target JSONL path
        items: Items to append (will be deduplicated by 'id' field)
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing items
    existing: Dict[str, Dict[str, Any]] = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        item = json.loads(line)
                        item_id = item.get("id") or item.get("source", "") + item.get("target", "")
                        if item_id:
                            existing[item_id] = item
        except Exception as e:
            logger.warning(f"Failed to read existing JSONL {path}: {e}")

    # Merge new items (upsert)
    for item in items:
        item_id = item.get("id") or item.get("source", "") + item.get("target", "")
        if item_id:
            existing[item_id] = item

    # Write atomically
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".tmp_",
        suffix=".jsonl",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for item in existing.values():
                f.write(json.dumps(item) + "\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ============================================================================
# Graph Sync Functions
# ============================================================================


def sync_entry_to_graph(
    threads_dir: Path,
    topic: str,
    entry_id: Optional[str] = None,
    generate_summaries: bool = False,
) -> bool:
    """Sync a single entry to the graph after an MCP write.

    This function:
    1. Parses the thread file
    2. Upserts the entry node (and thread node)
    3. Updates edges (contains, followed_by)
    4. Updates sync state

    Args:
        threads_dir: Threads directory
        topic: Thread topic
        entry_id: Specific entry ID to sync (or None for latest)
        generate_summaries: Whether to generate LLM summaries (slow)

    Returns:
        True if sync succeeded, False otherwise
    """
    thread_path = threads_dir / f"{topic}.md"
    if not thread_path.exists():
        logger.warning(f"Thread file not found for sync: {thread_path}")
        return False

    try:
        # Parse thread
        config = create_summarizer_config() if generate_summaries else None
        parsed = parse_thread_file(
            thread_path,
            config=config,
            generate_summaries=generate_summaries,
        )
        if not parsed:
            logger.warning(f"Failed to parse thread for sync: {topic}")
            return False

        # Find the entry to sync
        if entry_id:
            entry = next((e for e in parsed.entries if e.entry_id == entry_id), None)
            if not entry:
                # Entry ID not found, sync full thread
                logger.debug(f"Entry {entry_id} not found, syncing full thread")
                return sync_thread_to_graph(threads_dir, topic, generate_summaries)
        else:
            # Sync latest entry
            entry = parsed.entries[-1] if parsed.entries else None

        if not entry:
            logger.warning(f"No entries found in thread: {topic}")
            return False

        # Prepare graph output directory
        graph_dir = threads_dir / "graph" / "baseline"
        nodes_file = graph_dir / "nodes.jsonl"
        edges_file = graph_dir / "edges.jsonl"

        # Build nodes (thread + entry)
        nodes = [
            thread_to_node(parsed),
            entry_to_node(entry, topic),
        ]

        # Build edges for this entry
        edges = []
        thread_id = f"thread:{topic}"
        entry_node_id = f"entry:{entry.entry_id}"

        # Thread contains entry
        edges.append({
            "source": thread_id,
            "target": entry_node_id,
            "type": "contains",
        })

        # Find previous entry for followed_by edge
        if entry.index > 0 and len(parsed.entries) > entry.index:
            prev_entry = parsed.entries[entry.index - 1] if entry.index > 0 else None
            if not prev_entry and entry.index > 0:
                # Try to find by index
                for e in parsed.entries:
                    if e.index == entry.index - 1:
                        prev_entry = e
                        break
            if prev_entry:
                edges.append({
                    "source": f"entry:{prev_entry.entry_id}",
                    "target": entry_node_id,
                    "type": "followed_by",
                })

        # Atomic writes
        _atomic_append_jsonl(nodes_file, nodes)
        _atomic_append_jsonl(edges_file, edges)

        # Update manifest
        _update_manifest(graph_dir, topic, entry.entry_id)

        # Update sync state
        state = GraphSyncState(
            status="ok",
            last_synced_entry_id=entry.entry_id,
            last_sync_at=_now_iso(),
            error_message=None,
            entries_synced=(get_graph_sync_state(threads_dir, topic) or GraphSyncState()).entries_synced + 1,
        )
        _update_graph_sync_state(threads_dir, topic, state)

        logger.debug(f"Graph sync complete for {topic}/{entry.entry_id}")
        return True

    except Exception as e:
        logger.error(f"Graph sync failed for {topic}: {e}")
        record_graph_sync_error(threads_dir, topic, entry_id, e)
        return False


def sync_thread_to_graph(
    threads_dir: Path,
    topic: str,
    generate_summaries: bool = False,
) -> bool:
    """Sync an entire thread to the graph.

    This is a full resync - useful for reconciliation or initial build.

    Args:
        threads_dir: Threads directory
        topic: Thread topic
        generate_summaries: Whether to generate LLM summaries

    Returns:
        True if sync succeeded, False otherwise
    """
    thread_path = threads_dir / f"{topic}.md"
    if not thread_path.exists():
        logger.warning(f"Thread file not found for sync: {thread_path}")
        return False

    try:
        # Parse thread
        config = create_summarizer_config() if generate_summaries else None
        parsed = parse_thread_file(
            thread_path,
            config=config,
            generate_summaries=generate_summaries,
        )
        if not parsed:
            logger.warning(f"Failed to parse thread for sync: {topic}")
            return False

        # Prepare graph output directory
        graph_dir = threads_dir / "graph" / "baseline"
        nodes_file = graph_dir / "nodes.jsonl"
        edges_file = graph_dir / "edges.jsonl"

        # Build all nodes
        nodes = [thread_to_node(parsed)]
        for entry in parsed.entries:
            nodes.append(entry_to_node(entry, topic))

        # Build all edges
        edges = list(generate_edges(parsed))

        # Atomic writes
        _atomic_append_jsonl(nodes_file, nodes)
        _atomic_append_jsonl(edges_file, edges)

        # Update manifest
        last_entry_id = parsed.entries[-1].entry_id if parsed.entries else None
        _update_manifest(graph_dir, topic, last_entry_id)

        # Update sync state
        state = GraphSyncState(
            status="ok",
            last_synced_entry_id=last_entry_id,
            last_sync_at=_now_iso(),
            error_message=None,
            entries_synced=len(parsed.entries),
        )
        _update_graph_sync_state(threads_dir, topic, state)

        logger.debug(f"Full thread sync complete for {topic}: {len(parsed.entries)} entries")
        return True

    except Exception as e:
        logger.error(f"Thread sync failed for {topic}: {e}")
        record_graph_sync_error(threads_dir, topic, None, e)
        return False


def _update_manifest(graph_dir: Path, topic: str, entry_id: Optional[str]) -> None:
    """Update the manifest file with sync metadata.

    Args:
        graph_dir: Graph output directory
        topic: Thread topic that was synced
        entry_id: Last synced entry ID
    """
    manifest_path = graph_dir / "manifest.json"

    # Load existing manifest
    manifest: Dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": _now_iso(),
        "last_updated": _now_iso(),
        "topics_synced": {},
    }
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Update
    manifest["last_updated"] = _now_iso()
    if "topics_synced" not in manifest:
        manifest["topics_synced"] = {}
    manifest["topics_synced"][topic] = {
        "last_entry_id": entry_id,
        "synced_at": _now_iso(),
    }

    # Atomic write
    _atomic_write_json(manifest_path, manifest)


# ============================================================================
# Health Check & Reconciliation
# ============================================================================


@dataclass
class GraphHealthReport:
    """Health report for graph sync status."""

    healthy: bool = True
    total_threads: int = 0
    synced_threads: int = 0
    error_threads: int = 0
    pending_threads: int = 0
    stale_threads: List[str] = field(default_factory=list)
    error_details: Dict[str, str] = field(default_factory=dict)


def check_graph_health(threads_dir: Path) -> GraphHealthReport:
    """Check graph sync health for all threads.

    Returns:
        GraphHealthReport with status of all threads
    """
    report = GraphHealthReport()

    # Count total threads
    thread_files = list(threads_dir.glob("*.md"))
    report.total_threads = len(thread_files)

    # Load sync state
    state_file = _get_state_file(threads_dir)
    if not state_file.exists():
        # No sync state = all threads need sync
        report.stale_threads = [f.stem for f in thread_files]
        report.healthy = False
        return report

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        topic_states = data.get("topics", {})
    except Exception as e:
        report.healthy = False
        report.error_details["state_file"] = str(e)
        return report

    # Check each thread
    for thread_file in thread_files:
        topic = thread_file.stem
        topic_state = topic_states.get(topic)

        if not topic_state:
            report.stale_threads.append(topic)
            continue

        status = topic_state.get("status", "ok")
        if status == "ok":
            report.synced_threads += 1
        elif status == "error":
            report.error_threads += 1
            report.error_details[topic] = topic_state.get("error_message", "Unknown error")
        elif status == "pending":
            report.pending_threads += 1

    report.healthy = (
        report.error_threads == 0
        and report.pending_threads == 0
        and len(report.stale_threads) == 0
    )

    return report


def reconcile_graph(
    threads_dir: Path,
    topics: Optional[List[str]] = None,
    generate_summaries: bool = False,
) -> Dict[str, bool]:
    """Reconcile graph with markdown files.

    Rebuilds graph nodes/edges for specified topics or all stale/error topics.

    Args:
        threads_dir: Threads directory
        topics: Specific topics to reconcile (or None for all stale/error)
        generate_summaries: Whether to generate LLM summaries

    Returns:
        Dict mapping topic to success/failure
    """
    results: Dict[str, bool] = {}

    if topics is None:
        # Find all stale/error topics
        health = check_graph_health(threads_dir)
        topics = health.stale_threads + list(health.error_details.keys())

    for topic in topics:
        success = sync_thread_to_graph(threads_dir, topic, generate_summaries)
        results[topic] = success

    return results
