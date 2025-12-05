"""Export baseline graph to JSONL format.

Produces graph files suitable for loading into graph databases or
the Watercooler dashboard knowledge graph view.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .parser import ParsedThread, ParsedEntry, iter_threads
from .summarizer import SummarizerConfig

logger = logging.getLogger(__name__)

# Regex patterns for cross-reference extraction
FILE_REF_RE = re.compile(r"`([a-zA-Z0-9_/.-]+\.[a-zA-Z0-9]+)`")
PR_REF_RE = re.compile(r"#(\d+)")
COMMIT_REF_RE = re.compile(r"\b([a-fA-F0-9]{8,40})\b")  # Min 8 chars to reduce false positives


def _is_safe_path(path: str) -> bool:
    """Check if a path reference is safe (no traversal or absolute paths).

    Args:
        path: Path string to validate

    Returns:
        True if path is safe, False if it contains traversal or is absolute
    """
    # Reject absolute paths
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        return False
    # Reject path traversal
    if ".." in path:
        return False
    return True


def _extract_file_refs(text: str) -> List[str]:
    """Extract file path references from text.

    Filters out paths with traversal sequences or absolute paths for security.
    """
    refs = FILE_REF_RE.findall(text)
    return list(set(ref for ref in refs if _is_safe_path(ref)))


def _extract_pr_refs(text: str) -> List[int]:
    """Extract PR number references from text."""
    return [int(n) for n in set(PR_REF_RE.findall(text))]


def _extract_commit_refs(text: str) -> List[str]:
    """Extract commit SHA references from text."""
    return list(set(COMMIT_REF_RE.findall(text)))


def thread_to_node(thread: ParsedThread) -> Dict[str, Any]:
    """Convert ParsedThread to graph node.

    Args:
        thread: Parsed thread

    Returns:
        Node dict for JSONL export
    """
    return {
        "id": f"thread:{thread.topic}",
        "type": "thread",
        "topic": thread.topic,
        "title": thread.title,
        "status": thread.status,
        "ball": thread.ball,
        "last_updated": thread.last_updated,
        "summary": thread.summary,
        "entry_count": thread.entry_count,
    }


def entry_to_node(entry: ParsedEntry, topic: str) -> Dict[str, Any]:
    """Convert ParsedEntry to graph node.

    Args:
        entry: Parsed entry
        topic: Parent thread topic

    Returns:
        Node dict for JSONL export
    """
    return {
        "id": f"entry:{entry.entry_id}",
        "type": "entry",
        "entry_id": entry.entry_id,
        "thread_topic": topic,
        "index": entry.index,
        "agent": entry.agent,
        "role": entry.role,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "timestamp": entry.timestamp,
        "summary": entry.summary,
        "file_refs": _extract_file_refs(entry.body),
        "pr_refs": _extract_pr_refs(entry.body),
        "commit_refs": _extract_commit_refs(entry.body),
    }


def generate_edges(thread: ParsedThread) -> Iterator[Dict[str, Any]]:
    """Generate edges for a thread.

    Creates edges for:
    - Thread contains entries
    - Entry follows entry (sequential)
    - Cross-references between entries (if detected)

    Args:
        thread: Parsed thread

    Yields:
        Edge dicts for JSONL export
    """
    thread_id = f"thread:{thread.topic}"

    prev_entry_id = None
    for entry in thread.entries:
        entry_id = f"entry:{entry.entry_id}"

        # Thread contains entry
        yield {
            "source": thread_id,
            "target": entry_id,
            "type": "contains",
        }

        # Sequential entry relationship
        if prev_entry_id:
            yield {
                "source": prev_entry_id,
                "target": entry_id,
                "type": "followed_by",
            }

        prev_entry_id = entry_id


def export_thread_graph(
    thread: ParsedThread,
    output_dir: Path,
    append: bool = True,
) -> Tuple[int, int]:
    """Export a single thread to JSONL files.

    Args:
        thread: Parsed thread
        output_dir: Output directory for JSONL files
        append: Append to existing files (default) or overwrite

    Returns:
        Tuple of (nodes_written, edges_written)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    nodes_file = output_dir / "nodes.jsonl"
    edges_file = output_dir / "edges.jsonl"

    mode = "a" if append else "w"
    nodes_written = 0
    edges_written = 0

    # Write nodes
    with open(nodes_file, mode, encoding="utf-8") as f:
        # Thread node
        f.write(json.dumps(thread_to_node(thread)) + "\n")
        nodes_written += 1

        # Entry nodes
        for entry in thread.entries:
            f.write(json.dumps(entry_to_node(entry, thread.topic)) + "\n")
            nodes_written += 1

    # Write edges
    with open(edges_file, mode, encoding="utf-8") as f:
        for edge in generate_edges(thread):
            f.write(json.dumps(edge) + "\n")
            edges_written += 1

    return nodes_written, edges_written


def export_all_threads(
    threads_dir: Path,
    output_dir: Path,
    config: Optional[SummarizerConfig] = None,
    skip_closed: bool = False,
) -> Dict[str, Any]:
    """Export all threads to JSONL graph format.

    Args:
        threads_dir: Path to threads directory
        output_dir: Output directory for JSONL files
        config: Summarizer configuration
        skip_closed: Skip closed threads

    Returns:
        Export statistics
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Clear existing files
    nodes_file = output_dir / "nodes.jsonl"
    edges_file = output_dir / "edges.jsonl"

    if nodes_file.exists():
        nodes_file.unlink()
    if edges_file.exists():
        edges_file.unlink()

    total_threads = 0
    total_entries = 0
    total_nodes = 0
    total_edges = 0

    for thread in iter_threads(threads_dir, config, generate_summaries=True, skip_closed=skip_closed):
        nodes, edges = export_thread_graph(thread, output_dir, append=True)
        total_threads += 1
        total_entries += thread.entry_count
        total_nodes += nodes
        total_edges += edges
        logger.info(f"Exported thread '{thread.topic}': {nodes} nodes, {edges} edges")

    # Write manifest
    manifest = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_dir": str(threads_dir),
        "threads_exported": total_threads,
        "entries_exported": total_entries,
        "nodes_written": total_nodes,
        "edges_written": total_edges,
        "files": {
            "nodes": "nodes.jsonl",
            "edges": "edges.jsonl",
        },
    }

    manifest_file = output_dir / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def load_nodes(nodes_file: Path) -> Iterator[Dict[str, Any]]:
    """Load nodes from JSONL file.

    Args:
        nodes_file: Path to nodes.jsonl

    Yields:
        Node dicts

    Raises:
        json.JSONDecodeError: If a line contains invalid JSON (with line number context)
    """
    with open(nodes_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    raise json.JSONDecodeError(
                        f"Invalid JSON at line {line_num} in {nodes_file}: {e.msg}",
                        e.doc,
                        e.pos,
                    ) from e


def load_edges(edges_file: Path) -> Iterator[Dict[str, Any]]:
    """Load edges from JSONL file.

    Args:
        edges_file: Path to edges.jsonl

    Yields:
        Edge dicts

    Raises:
        json.JSONDecodeError: If a line contains invalid JSON (with line number context)
    """
    with open(edges_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    raise json.JSONDecodeError(
                        f"Invalid JSON at line {line_num} in {edges_file}: {e.msg}",
                        e.doc,
                        e.pos,
                    ) from e


def load_graph(graph_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load complete graph from directory.

    Args:
        graph_dir: Directory containing nodes.jsonl and edges.jsonl

    Returns:
        Tuple of (nodes_list, edges_list)
    """
    nodes = list(load_nodes(graph_dir / "nodes.jsonl"))
    edges = list(load_edges(graph_dir / "edges.jsonl"))
    return nodes, edges
