"""Tests for baseline graph sync module."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from watercooler.baseline_graph.sync import (
    GraphHealthReport,
    GraphSyncState,
    _atomic_append_jsonl,
    _atomic_write_json,
    check_graph_health,
    get_graph_sync_state,
    reconcile_graph,
    record_graph_sync_error,
    sync_entry_to_graph,
    sync_thread_to_graph,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def threads_dir(tmp_path: Path) -> Path:
    """Create a temporary threads directory with a sample thread."""
    threads = tmp_path / "threads"
    threads.mkdir()
    return threads


@pytest.fixture
def sample_thread(threads_dir: Path) -> Path:
    """Create a sample thread file."""
    thread_content = """# test-topic — Thread
Status: OPEN
Ball: Claude (user)
Topic: test-topic
Created: 2025-01-01T00:00:00Z

---
Entry: Claude (user) 2025-01-01T00:00:00Z
Role: planner
Type: Note
Title: First Entry

This is the first entry body.
<!-- Entry-ID: 01TEST00000000000000000001 -->

---
Entry: Claude (user) 2025-01-01T01:00:00Z
Role: implementer
Type: Note
Title: Second Entry

This is the second entry body.
<!-- Entry-ID: 01TEST00000000000000000002 -->
"""
    thread_path = threads_dir / "test-topic.md"
    thread_path.write_text(thread_content, encoding="utf-8")
    return thread_path


@pytest.fixture
def graph_dir(threads_dir: Path) -> Path:
    """Create graph output directory."""
    gd = threads_dir / "graph" / "baseline"
    gd.mkdir(parents=True)
    return gd


# ============================================================================
# Atomic File Operations Tests
# ============================================================================


def test_atomic_write_json_creates_file(tmp_path: Path):
    """Test atomic JSON write creates file correctly."""
    target = tmp_path / "test.json"
    data = {"key": "value", "number": 42}

    _atomic_write_json(target, data)

    assert target.exists()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == data


def test_atomic_write_json_overwrites(tmp_path: Path):
    """Test atomic JSON write overwrites existing file."""
    target = tmp_path / "test.json"
    target.write_text('{"old": "data"}', encoding="utf-8")

    _atomic_write_json(target, {"new": "data"})

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == {"new": "data"}


def test_atomic_append_jsonl_creates_file(tmp_path: Path):
    """Test atomic JSONL append creates file correctly."""
    target = tmp_path / "test.jsonl"
    items = [{"id": "1", "value": "a"}, {"id": "2", "value": "b"}]

    _atomic_append_jsonl(target, items)

    assert target.exists()
    lines = target.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == "1"
    assert json.loads(lines[1])["id"] == "2"


def test_atomic_append_jsonl_deduplicates(tmp_path: Path):
    """Test atomic JSONL append deduplicates by ID."""
    target = tmp_path / "test.jsonl"

    # First write
    _atomic_append_jsonl(target, [{"id": "1", "value": "a"}])

    # Second write with same ID (should update)
    _atomic_append_jsonl(target, [{"id": "1", "value": "updated"}])

    lines = target.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0])["value"] == "updated"


def test_atomic_append_jsonl_merges_new(tmp_path: Path):
    """Test atomic JSONL append merges new items."""
    target = tmp_path / "test.jsonl"

    # First write
    _atomic_append_jsonl(target, [{"id": "1", "value": "a"}])

    # Second write with new ID
    _atomic_append_jsonl(target, [{"id": "2", "value": "b"}])

    lines = target.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2


# ============================================================================
# Graph Sync State Tests
# ============================================================================


def test_get_graph_sync_state_none_when_missing(threads_dir: Path):
    """Test get_graph_sync_state returns None when no state exists."""
    state = get_graph_sync_state(threads_dir, "nonexistent")
    assert state is None


def test_record_graph_sync_error_creates_state(threads_dir: Path, graph_dir: Path):
    """Test record_graph_sync_error creates error state."""
    record_graph_sync_error(
        threads_dir, "test-topic", "entry123", Exception("Test error")
    )

    state = get_graph_sync_state(threads_dir, "test-topic")
    assert state is not None
    assert state.status == "error"
    assert "Test error" in state.error_message


def test_graph_sync_state_round_trip(threads_dir: Path, graph_dir: Path):
    """Test graph sync state can be written and read."""
    # Record an error first to create state file
    record_graph_sync_error(
        threads_dir, "test-topic", "entry123", Exception("Test error")
    )

    state = get_graph_sync_state(threads_dir, "test-topic")
    assert state.status == "error"
    assert state.error_message == "Test error"


# ============================================================================
# Entry Sync Tests
# ============================================================================


def test_sync_entry_to_graph_creates_nodes(threads_dir: Path, sample_thread: Path):
    """Test sync_entry_to_graph creates nodes and edges."""
    success = sync_entry_to_graph(threads_dir, "test-topic")

    assert success

    # Check nodes file
    nodes_file = threads_dir / "graph" / "baseline" / "nodes.jsonl"
    assert nodes_file.exists()

    nodes = []
    for line in nodes_file.read_text(encoding="utf-8").strip().split("\n"):
        nodes.append(json.loads(line))

    # Should have thread node + entry node (at minimum)
    assert len(nodes) >= 2

    # Check for thread node
    thread_nodes = [n for n in nodes if n.get("type") == "thread"]
    assert len(thread_nodes) >= 1
    assert thread_nodes[0]["topic"] == "test-topic"

    # Check for entry node
    entry_nodes = [n for n in nodes if n.get("type") == "entry"]
    assert len(entry_nodes) >= 1


def test_sync_entry_to_graph_creates_edges(threads_dir: Path, sample_thread: Path):
    """Test sync_entry_to_graph creates edges."""
    sync_entry_to_graph(threads_dir, "test-topic")

    edges_file = threads_dir / "graph" / "baseline" / "edges.jsonl"
    assert edges_file.exists()

    edges = []
    for line in edges_file.read_text(encoding="utf-8").strip().split("\n"):
        edges.append(json.loads(line))

    # Should have at least one "contains" edge
    contains_edges = [e for e in edges if e.get("type") == "contains"]
    assert len(contains_edges) >= 1


def test_sync_entry_to_graph_updates_state(threads_dir: Path, sample_thread: Path):
    """Test sync_entry_to_graph updates sync state."""
    sync_entry_to_graph(threads_dir, "test-topic")

    state = get_graph_sync_state(threads_dir, "test-topic")
    assert state is not None
    assert state.status == "ok"
    assert state.last_synced_entry_id is not None


def test_sync_entry_to_graph_nonexistent_thread(threads_dir: Path):
    """Test sync_entry_to_graph returns False for nonexistent thread."""
    success = sync_entry_to_graph(threads_dir, "nonexistent")
    assert not success


def test_sync_entry_with_specific_entry_id(threads_dir: Path, sample_thread: Path):
    """Test sync_entry_to_graph with specific entry ID."""
    # First sync to create initial state
    sync_thread_to_graph(threads_dir, "test-topic")

    # Sync specific entry
    success = sync_entry_to_graph(
        threads_dir, "test-topic", entry_id="01TEST00000000000000000001"
    )

    assert success


# ============================================================================
# Thread Sync Tests
# ============================================================================


def test_sync_thread_to_graph_full_sync(threads_dir: Path, sample_thread: Path):
    """Test sync_thread_to_graph performs full sync."""
    success = sync_thread_to_graph(threads_dir, "test-topic")

    assert success

    # Check nodes
    nodes_file = threads_dir / "graph" / "baseline" / "nodes.jsonl"
    nodes = []
    for line in nodes_file.read_text(encoding="utf-8").strip().split("\n"):
        nodes.append(json.loads(line))

    # Should have 1 thread + 2 entries = 3 nodes
    assert len(nodes) == 3

    # Check state
    state = get_graph_sync_state(threads_dir, "test-topic")
    assert state.entries_synced == 2


# ============================================================================
# Health Check Tests
# ============================================================================


def test_check_graph_health_no_state(threads_dir: Path, sample_thread: Path):
    """Test check_graph_health reports stale threads when no state."""
    report = check_graph_health(threads_dir)

    assert not report.healthy
    assert report.total_threads == 1
    assert "test-topic" in report.stale_threads


def test_check_graph_health_after_sync(threads_dir: Path, sample_thread: Path):
    """Test check_graph_health reports healthy after sync."""
    sync_thread_to_graph(threads_dir, "test-topic")

    report = check_graph_health(threads_dir)

    assert report.healthy
    assert report.synced_threads == 1
    assert report.error_threads == 0
    assert len(report.stale_threads) == 0


def test_check_graph_health_with_errors(threads_dir: Path, sample_thread: Path):
    """Test check_graph_health reports error threads."""
    # Create graph dir first
    (threads_dir / "graph" / "baseline").mkdir(parents=True)

    # Record an error
    record_graph_sync_error(
        threads_dir, "test-topic", None, Exception("Sync failed")
    )

    report = check_graph_health(threads_dir)

    assert not report.healthy
    assert report.error_threads == 1
    assert "test-topic" in report.error_details


# ============================================================================
# Reconciliation Tests
# ============================================================================


def test_reconcile_graph_fixes_stale(threads_dir: Path, sample_thread: Path):
    """Test reconcile_graph fixes stale threads."""
    # Check health shows stale
    report_before = check_graph_health(threads_dir)
    assert not report_before.healthy

    # Reconcile
    results = reconcile_graph(threads_dir)

    assert results.get("test-topic") is True

    # Check health shows healthy
    report_after = check_graph_health(threads_dir)
    assert report_after.healthy


def test_reconcile_graph_specific_topics(threads_dir: Path, sample_thread: Path):
    """Test reconcile_graph for specific topics."""
    results = reconcile_graph(threads_dir, topics=["test-topic"])

    assert results == {"test-topic": True}


# ============================================================================
# Concurrency Tests
# ============================================================================


def test_concurrent_sync_operations(threads_dir: Path, sample_thread: Path):
    """Test concurrent sync operations don't corrupt JSONL."""
    results = []
    errors = []

    def sync_thread():
        try:
            success = sync_thread_to_graph(threads_dir, "test-topic")
            results.append(success)
        except Exception as e:
            errors.append(e)

    # Run multiple syncs concurrently
    threads = [threading.Thread(target=sync_thread) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All should succeed (atomic writes prevent corruption)
    assert all(results), f"Some syncs failed: {errors}"
    assert len(errors) == 0

    # Verify JSONL is valid
    nodes_file = threads_dir / "graph" / "baseline" / "nodes.jsonl"
    lines = nodes_file.read_text(encoding="utf-8").strip().split("\n")
    for line in lines:
        json.loads(line)  # Should not raise


def test_sync_failure_does_not_block(threads_dir: Path, sample_thread: Path):
    """Test that sync failure is recorded but doesn't raise."""
    # Create graph dir
    (threads_dir / "graph" / "baseline").mkdir(parents=True)

    # Mock parse_thread_file to raise
    with patch(
        "watercooler.baseline_graph.sync.parse_thread_file",
        side_effect=Exception("Parse failed"),
    ):
        success = sync_entry_to_graph(threads_dir, "test-topic")

    # Should return False, not raise
    assert not success

    # Error should be recorded
    state = get_graph_sync_state(threads_dir, "test-topic")
    assert state.status == "error"


# ============================================================================
# Manifest Tests
# ============================================================================


def test_manifest_updated_on_sync(threads_dir: Path, sample_thread: Path):
    """Test manifest is updated after sync."""
    sync_thread_to_graph(threads_dir, "test-topic")

    manifest_path = threads_dir / "graph" / "baseline" / "manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "schema_version" in manifest
    assert "last_updated" in manifest
    assert "test-topic" in manifest.get("topics_synced", {})


def test_manifest_preserves_other_topics(threads_dir: Path, sample_thread: Path):
    """Test manifest preserves data from other topics."""
    # Sync first topic
    sync_thread_to_graph(threads_dir, "test-topic")

    # Create another thread
    (threads_dir / "other-topic.md").write_text(
        """# other-topic — Thread
Status: OPEN
Ball: User
Topic: other-topic
Created: 2025-01-01T00:00:00Z

---
Entry: User 2025-01-01T00:00:00Z
Role: planner
Type: Note
Title: Other Entry

Body text.
<!-- Entry-ID: 01OTHER0000000000000000001 -->
""",
        encoding="utf-8",
    )

    # Sync second topic
    sync_thread_to_graph(threads_dir, "other-topic")

    # Both should be in manifest
    manifest_path = threads_dir / "graph" / "baseline" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    topics_synced = manifest.get("topics_synced", {})
    assert "test-topic" in topics_synced
    assert "other-topic" in topics_synced
