"""Unified search module for baseline graph.

This module provides composable search functionality across threads and entries
stored in the JSONL graph format.

Key capabilities:
- Keyword search (text contains in body/title/summary)
- Time-boxed search (timestamp range)
- Filters by thread_status, role, entry_type, agent
- AND/OR combination of filters
- Similar entry lookup (by entry_id)

Future:
- Semantic search with embeddings (when available)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, List, Literal, Optional

from .reader import get_graph_dir, GraphEntry, GraphThread, _node_to_entry, _node_to_thread

logger = logging.getLogger(__name__)


# ============================================================================
# Search Configuration
# ============================================================================


@dataclass
class SearchQuery:
    """Search query configuration.

    Attributes:
        query: Optional keyword query (searches title, body, summary)
        semantic: If True, use semantic/vector search (requires embeddings)
        start_time: Filter entries after this ISO timestamp
        end_time: Filter entries before this ISO timestamp
        similar_to: Find entries similar to this entry_id
        thread_status: Filter by thread status (OPEN, CLOSED, etc.)
        thread_topic: Filter by specific thread topic
        role: Filter by entry role (planner, implementer, etc.)
        entry_type: Filter by entry type (Note, Plan, Decision, etc.)
        agent: Filter by agent name
        limit: Maximum results to return
        combine: How to combine filters ("AND" or "OR")
        include_threads: Include thread nodes in results
        include_entries: Include entry nodes in results
    """
    query: Optional[str] = None
    semantic: bool = False
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    similar_to: Optional[str] = None
    thread_status: Optional[str] = None
    thread_topic: Optional[str] = None
    role: Optional[str] = None
    entry_type: Optional[str] = None
    agent: Optional[str] = None
    limit: int = 10
    combine: Literal["AND", "OR"] = "AND"
    include_threads: bool = True
    include_entries: bool = True


@dataclass
class SearchResult:
    """A single search result.

    Attributes:
        node_type: "thread" or "entry"
        node_id: Unique identifier (topic for threads, entry_id for entries)
        score: Relevance score (higher is better)
        matched_fields: Which fields matched the query
        thread: GraphThread if node_type is "thread"
        entry: GraphEntry if node_type is "entry"
    """
    node_type: Literal["thread", "entry"]
    node_id: str
    score: float = 1.0
    matched_fields: List[str] = field(default_factory=list)
    thread: Optional[GraphThread] = None
    entry: Optional[GraphEntry] = None


@dataclass
class SearchResults:
    """Container for search results.

    Attributes:
        results: List of SearchResult objects
        total_scanned: Total nodes scanned
        query: The original search query
    """
    results: List[SearchResult] = field(default_factory=list)
    total_scanned: int = 0
    query: Optional[SearchQuery] = None

    @property
    def count(self) -> int:
        """Number of results."""
        return len(self.results)

    def threads(self) -> List[GraphThread]:
        """Get all thread results."""
        return [r.thread for r in self.results if r.thread is not None]

    def entries(self) -> List[GraphEntry]:
        """Get all entry results."""
        return [r.entry for r in self.results if r.entry is not None]


# ============================================================================
# Node Loading
# ============================================================================


def _load_nodes(graph_dir: Path) -> Iterator[dict[str, Any]]:
    """Load all nodes from the graph JSONL file."""
    nodes_file = graph_dir / "nodes.jsonl"
    if not nodes_file.exists():
        return

    with open(nodes_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


# ============================================================================
# Filter Functions
# ============================================================================


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse an ISO timestamp string to datetime."""
    if not ts:
        return None
    try:
        # Handle Z suffix
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _matches_keyword(node: dict[str, Any], query: str) -> tuple[bool, List[str]]:
    """Check if node matches keyword query.

    Returns:
        Tuple of (matches, list of matched field names)
    """
    if not query:
        return True, []

    query_lower = query.lower()
    matched_fields = []

    # Fields to search
    searchable_fields = ["title", "body", "summary", "topic"]

    for field_name in searchable_fields:
        value = node.get(field_name, "")
        if value and query_lower in str(value).lower():
            matched_fields.append(field_name)

    return len(matched_fields) > 0, matched_fields


def _matches_time_range(
    node: dict[str, Any],
    start_time: Optional[str],
    end_time: Optional[str],
) -> bool:
    """Check if node timestamp falls within range."""
    # Get node timestamp
    node_ts = node.get("timestamp") or node.get("last_updated")
    if not node_ts:
        # No timestamp - include by default unless time filter is strict
        return start_time is None and end_time is None

    node_dt = _parse_timestamp(node_ts)
    if not node_dt:
        return True  # Can't parse, include by default

    if start_time:
        start_dt = _parse_timestamp(start_time)
        if start_dt and node_dt < start_dt:
            return False

    if end_time:
        end_dt = _parse_timestamp(end_time)
        if end_dt and node_dt > end_dt:
            return False

    return True


def _matches_filters(
    node: dict[str, Any],
    search_query: SearchQuery,
    combine: str = "AND",
) -> tuple[bool, List[str]]:
    """Check if node matches filters.

    Args:
        node: The node to check
        search_query: Search query with filters
        combine: "AND" requires all filters to match, "OR" requires any filter

    Returns:
        Tuple of (matches, list of matched filter names)
    """
    node_type = node.get("type")
    filter_results: List[tuple[str, bool]] = []

    # Thread-specific filters
    if node_type == "thread":
        if search_query.thread_status:
            status = node.get("status", "").upper()
            matches = status == search_query.thread_status.upper()
            filter_results.append(("thread_status", matches))
        if search_query.thread_topic:
            matches = node.get("topic") == search_query.thread_topic
            filter_results.append(("thread_topic", matches))

    # Entry-specific filters
    if node_type == "entry":
        if search_query.thread_topic:
            matches = node.get("thread_topic") == search_query.thread_topic
            filter_results.append(("thread_topic", matches))
        if search_query.role:
            role = node.get("role", "").lower()
            matches = role == search_query.role.lower()
            filter_results.append(("role", matches))
        if search_query.entry_type:
            entry_type = node.get("entry_type", "")
            matches = entry_type.lower() == search_query.entry_type.lower()
            filter_results.append(("entry_type", matches))
        if search_query.agent:
            agent = node.get("agent", "").lower()
            matches = search_query.agent.lower() in agent
            filter_results.append(("agent", matches))

    # If no filters were specified, return True
    if not filter_results:
        return True, []

    # Combine results based on mode
    matched_filters = [name for name, matches in filter_results if matches]

    if combine == "OR":
        # At least one filter must match
        return len(matched_filters) > 0, matched_filters
    else:
        # All filters must match (AND mode)
        all_match = all(matches for _, matches in filter_results)
        return all_match, matched_filters if all_match else []


# ============================================================================
# Main Search Function
# ============================================================================


def search_graph(
    threads_dir: Path,
    search_query: SearchQuery,
) -> SearchResults:
    """Execute a search against the graph.

    Args:
        threads_dir: Path to threads directory
        search_query: Search configuration

    Returns:
        SearchResults containing matching nodes
    """
    graph_dir = get_graph_dir(threads_dir)
    results = SearchResults(query=search_query)

    if not (graph_dir / "nodes.jsonl").exists():
        logger.debug("No graph available for search")
        return results

    matching_results: List[SearchResult] = []

    for node in _load_nodes(graph_dir):
        results.total_scanned += 1
        node_type = node.get("type")

        # Filter by node type
        if node_type == "thread" and not search_query.include_threads:
            continue
        if node_type == "entry" and not search_query.include_entries:
            continue
        if node_type not in ("thread", "entry"):
            continue

        # Collect filter results
        filter_results = []
        matched_fields: List[str] = []

        # Keyword match
        if search_query.query:
            keyword_match, keyword_fields = _matches_keyword(node, search_query.query)
            filter_results.append(keyword_match)
            matched_fields.extend(keyword_fields)

        # Time range
        if search_query.start_time or search_query.end_time:
            time_match = _matches_time_range(
                node, search_query.start_time, search_query.end_time
            )
            filter_results.append(time_match)
            if time_match and (search_query.start_time or search_query.end_time):
                matched_fields.append("timestamp")

        # Other filters (role, entry_type, agent, thread_status, thread_topic)
        filters_match, filter_fields = _matches_filters(
            node, search_query, search_query.combine
        )
        if filter_fields:
            matched_fields.extend(filter_fields)

        # Add filter results to the overall list
        filter_results.append(filters_match)

        # Combine results
        if search_query.combine == "AND":
            passes = all(filter_results) if filter_results else True
        else:  # OR
            passes = any(filter_results) if filter_results else True

        if not passes:
            continue

        # Build result
        node_id = node.get("topic") if node_type == "thread" else node.get("entry_id", "")

        # Calculate score (simple relevance scoring)
        score = 1.0
        if matched_fields:
            # Boost for title matches
            if "title" in matched_fields:
                score += 0.5
            # Boost for body matches
            if "body" in matched_fields:
                score += 0.3
            score += len(matched_fields) * 0.1

        result = SearchResult(
            node_type=node_type,
            node_id=node_id,
            score=score,
            matched_fields=matched_fields,
        )

        # Attach typed object
        if node_type == "thread":
            result.thread = _node_to_thread(node)
        else:
            result.entry = _node_to_entry(node)

        matching_results.append(result)

    # Sort by score descending
    matching_results.sort(key=lambda r: r.score, reverse=True)

    # Apply limit
    results.results = matching_results[:search_query.limit]

    return results


# ============================================================================
# Convenience Functions
# ============================================================================


def search_entries(
    threads_dir: Path,
    query: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    thread_topic: Optional[str] = None,
    role: Optional[str] = None,
    entry_type: Optional[str] = None,
    agent: Optional[str] = None,
    limit: int = 10,
) -> List[GraphEntry]:
    """Search entries with common filters.

    Args:
        threads_dir: Path to threads directory
        query: Optional keyword search
        start_time: Filter entries after this timestamp
        end_time: Filter entries before this timestamp
        thread_topic: Filter by thread topic
        role: Filter by role
        entry_type: Filter by entry type
        agent: Filter by agent
        limit: Maximum results

    Returns:
        List of matching GraphEntry objects
    """
    search_query = SearchQuery(
        query=query,
        start_time=start_time,
        end_time=end_time,
        thread_topic=thread_topic,
        role=role,
        entry_type=entry_type,
        agent=agent,
        limit=limit,
        include_threads=False,
        include_entries=True,
    )

    results = search_graph(threads_dir, search_query)
    return results.entries()


def search_threads(
    threads_dir: Path,
    query: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10,
) -> List[GraphThread]:
    """Search threads with common filters.

    Args:
        threads_dir: Path to threads directory
        query: Optional keyword search
        status: Filter by thread status
        limit: Maximum results

    Returns:
        List of matching GraphThread objects
    """
    search_query = SearchQuery(
        query=query,
        thread_status=status,
        limit=limit,
        include_threads=True,
        include_entries=False,
    )

    results = search_graph(threads_dir, search_query)
    return results.threads()


def find_similar_entries(
    threads_dir: Path,
    entry_id: str,
    limit: int = 5,
) -> List[GraphEntry]:
    """Find entries similar to a given entry.

    Currently uses simple heuristics (same thread).
    Future: will use vector similarity when embeddings are available.

    Args:
        threads_dir: Path to threads directory
        entry_id: ID of entry to find similar entries to
        limit: Maximum results

    Returns:
        List of similar GraphEntry objects
    """
    graph_dir = get_graph_dir(threads_dir)

    # First, find the source entry
    source_entry = None
    for node in _load_nodes(graph_dir):
        if node.get("type") == "entry" and node.get("entry_id") == entry_id:
            source_entry = node
            break

    if not source_entry:
        return []

    # Find similar entries
    # Heuristic: same thread, different entry
    search_query = SearchQuery(
        thread_topic=source_entry.get("thread_topic"),
        limit=limit + 1,  # +1 to exclude self
        include_threads=False,
        include_entries=True,
    )

    results = search_graph(threads_dir, search_query)

    # Filter out the source entry
    similar = [e for e in results.entries() if e.entry_id != entry_id]

    return similar[:limit]


def search_by_time_range(
    threads_dir: Path,
    start_time: str,
    end_time: Optional[str] = None,
    include_threads: bool = True,
    include_entries: bool = True,
    limit: int = 50,
) -> SearchResults:
    """Search for nodes within a time range.

    Args:
        threads_dir: Path to threads directory
        start_time: ISO timestamp for range start
        end_time: Optional ISO timestamp for range end
        include_threads: Include thread nodes
        include_entries: Include entry nodes
        limit: Maximum results

    Returns:
        SearchResults within the time range
    """
    search_query = SearchQuery(
        start_time=start_time,
        end_time=end_time,
        include_threads=include_threads,
        include_entries=include_entries,
        limit=limit,
    )

    return search_graph(threads_dir, search_query)
