#!/usr/bin/env python3
"""Interactive graph visualization for Watercooler baseline graph.

Uses pyvis (vis.js wrapper) for force-directed layout with spring-relaxation
physics and interactive exploration.

Graph Format (Baseline Graph):
    The baseline graph is a JSONL-based representation of Watercooler threads
    produced by the memory pipeline. It consists of two files:

    nodes.jsonl - One JSON object per line, each with:
        - id: Unique identifier (e.g., "thread:feature-auth", "entry:topic:1")
        - type: "thread" or "entry"
        - For threads: topic, status, title, ball, entry_count, last_updated, summary
        - For entries: entry_id, title, entry_type, agent, role, timestamp, summary

    edges.jsonl - One JSON object per line, each with:
        - source: Source node ID
        - target: Target node ID
        - type: "contains" (thread→entry) or "followed_by" (entry→entry)

Usage:
    python scripts/visualize_graph.py --input /path/to/graph/baseline
    python scripts/visualize_graph.py --input /tmp/baseline-graph-full --open

Requirements:
    pip install pyvis networkx
    # Or: pip install watercooler-cloud[visualization]
"""

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Check for optional dependencies
try:
    import networkx as nx
    from pyvis.network import Network
except ImportError as e:
    print(
        "Error: Missing required dependencies for graph visualization.",
        file=sys.stderr,
    )
    print(
        "Install with: pip install pyvis networkx",
        file=sys.stderr,
    )
    print(f"Details: {e}", file=sys.stderr)
    sys.exit(1)


# Color schemes
COLORS = {
    "thread": {
        "OPEN": "#4CAF50",      # Green
        "CLOSED": "#9E9E9E",    # Gray
        "IN_REVIEW": "#FF9800", # Orange
        "BLOCKED": "#F44336",   # Red
    },
    "entry": {
        "Note": "#2196F3",      # Blue
        "Plan": "#9C27B0",      # Purple
        "Decision": "#FF5722", # Deep Orange
        "PR": "#00BCD4",        # Cyan
        "Closure": "#607D8B",   # Blue Gray
    },
    "edge": {
        "contains": "#666666",
        "followed_by": "#BBBBBB",
    },
}

# Node sizes
SIZES = {
    "thread": 30,
    "entry": 15,
}


def load_graph(
    graph_dir: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load nodes and edges from JSONL files.

    Args:
        graph_dir: Directory containing nodes.jsonl and edges.jsonl

    Returns:
        Tuple of (nodes_list, edges_list)

    Raises:
        FileNotFoundError: If graph directory doesn't exist
        json.JSONDecodeError: If JSONL files contain invalid JSON
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    nodes_file = graph_dir / "nodes.jsonl"
    edges_file = graph_dir / "edges.jsonl"

    if nodes_file.exists():
        with open(nodes_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        nodes.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(
                            f"Warning: Skipping malformed JSON in nodes.jsonl "
                            f"line {line_num}: {e}",
                            file=sys.stderr,
                        )

    if edges_file.exists():
        with open(edges_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        edges.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(
                            f"Warning: Skipping malformed JSON in edges.jsonl "
                            f"line {line_num}: {e}",
                            file=sys.stderr,
                        )

    return nodes, edges


def build_networkx_graph(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> nx.DiGraph:
    """Build NetworkX graph from nodes and edges.

    Args:
        nodes: List of node dicts (each must have 'id' key)
        edges: List of edge dicts (each must have 'source' and 'target' keys)

    Returns:
        NetworkX DiGraph
    """
    G = nx.DiGraph()

    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            print(f"Warning: Skipping node without 'id': {node}", file=sys.stderr)
            continue
        G.add_node(node_id, **node)

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            print(
                f"Warning: Skipping edge without 'source' or 'target': {edge}",
                file=sys.stderr,
            )
            continue
        G.add_edge(source, target, **edge)

    return G


def get_node_color(node: Dict[str, Any]) -> str:
    """Get color for a node based on type and status."""
    node_type = node.get("type", "entry")

    if node_type == "thread":
        status = node.get("status", "OPEN").upper()
        return COLORS["thread"].get(status, COLORS["thread"]["OPEN"])
    else:
        entry_type = node.get("entry_type", "Note")
        return COLORS["entry"].get(entry_type, COLORS["entry"]["Note"])


def get_node_size(node: Dict[str, Any]) -> int:
    """Get size for a node based on type."""
    node_type = node.get("type", "entry")
    base_size = SIZES.get(node_type, 15)

    # Threads with more entries are larger
    if node_type == "thread":
        entry_count = node.get("entry_count", 1)
        return base_size + min(entry_count * 2, 30)

    return base_size


def get_node_label(node: Dict[str, Any]) -> str:
    """Get display label for a node."""
    node_type = node.get("type", "entry")

    if node_type == "thread":
        topic = node.get("topic", "?")
        status = node.get("status", "?")
        return f"{topic}\n[{status}]"
    else:
        title = node.get("title", "")
        if title:
            # Truncate long titles
            if len(title) > 25:
                title = title[:22] + "..."
            return title
        return node.get("entry_id", "?")


def get_node_title(node: Dict[str, Any]) -> str:
    """Get hover tooltip for a node (plain text with newlines)."""
    node_type = node.get("type", "entry")

    if node_type == "thread":
        parts = [
            f"═══ Thread: {node.get('topic', '?')} ═══",
            f"Title: {node.get('title', '-')}",
            f"Status: {node.get('status', '-')}",
            f"Ball: {node.get('ball', '-')}",
            f"Entries: {node.get('entry_count', 0)}",
            f"Updated: {node.get('last_updated', '-')}",
        ]
        summary = node.get("summary", "")
        if summary:
            if len(summary) > 200:
                summary = summary[:197] + "..."
            parts.append(f"───────────────────")
            parts.append(f"Summary: {summary}")
        return "\n".join(parts)
    else:
        parts = [
            f"═══ Entry: {node.get('entry_id', '?')} ═══",
            f"Title: {node.get('title', '-')}",
            f"Type: {node.get('entry_type', '-')}",
            f"Agent: {node.get('agent', '-')}",
            f"Role: {node.get('role', '-')}",
            f"Time: {node.get('timestamp', '-')}",
        ]
        summary = node.get("summary", "")
        if summary:
            if len(summary) > 200:
                summary = summary[:197] + "..."
            parts.append(f"───────────────────")
            parts.append(f"Summary: {summary}")

        # Show file/PR refs if any
        file_refs = node.get("file_refs", [])
        if file_refs:
            parts.append(f"Files: {', '.join(file_refs[:5])}")
        pr_refs = node.get("pr_refs", [])
        if pr_refs:
            parts.append(f"PRs: {', '.join(f'#{n}' for n in pr_refs)}")

        return "\n".join(parts)


def get_edge_color(edge: Dict[str, Any]) -> str:
    """Get color for an edge based on type."""
    edge_type = edge.get("type", "contains")
    return COLORS["edge"].get(edge_type, "#999999")


def create_visualization(
    G: nx.DiGraph,
    height: str = "900px",
    width: str = "100%",
    bgcolor: str = "#222222",
    font_color: str = "#FFFFFF",
) -> Network:
    """Create pyvis Network from NetworkX graph.

    Args:
        G: NetworkX graph
        height: Canvas height
        width: Canvas width
        bgcolor: Background color
        font_color: Label font color

    Returns:
        Configured pyvis Network
    """
    # Create network with physics enabled
    net = Network(
        height=height,
        width=width,
        bgcolor=bgcolor,
        font_color=font_color,
        directed=True,
        notebook=False,
        select_menu=False,
        filter_menu=False,
    )

    # Configure physics (force-directed with spring relaxation)
    # Use barnesHut which is faster for large graphs
    # Disable stabilization to show graph immediately (settles live)
    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "solver": "barnesHut",
            "barnesHut": {
                "gravitationalConstant": -2000,
                "centralGravity": 0.5,
                "springLength": 100,
                "springConstant": 0.05,
                "damping": 0.15,
                "avoidOverlap": 0.2
            },
            "stabilization": false,
            "minVelocity": 1.0,
            "maxVelocity": 30
        },
        "nodes": {
            "font": {
                "size": 12,
                "face": "arial"
            },
            "borderWidth": 2,
            "borderWidthSelected": 4,
            "shadow": true
        },
        "edges": {
            "smooth": {
                "type": "continuous",
                "forceDirection": "none"
            },
            "arrows": {
                "to": {
                    "enabled": true,
                    "scaleFactor": 0.5
                }
            },
            "shadow": false
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 100,
            "hideEdgesOnDrag": true,
            "multiselect": true,
            "navigationButtons": true
        }
    }
    """)

    # Add nodes
    for node_id in G.nodes():
        node_data = G.nodes[node_id]
        net.add_node(
            node_id,
            label=get_node_label(node_data),
            title=get_node_title(node_data),
            color=get_node_color(node_data),
            size=get_node_size(node_data),
            shape="dot" if node_data.get("type") == "entry" else "diamond",
            group=node_data.get("type", "entry"),
        )

    # Add edges
    for source, target in G.edges():
        edge_data = G.edges[source, target]
        edge_type = edge_data.get("type", "contains")

        net.add_edge(
            source,
            target,
            color=get_edge_color(edge_data),
            width=2 if edge_type == "contains" else 1,
            dashes=edge_type == "followed_by",
            title=f"Type: {edge_type}",
        )

    return net


def main() -> int:
    """Main entry point for graph visualization.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="Interactive visualization for baseline graph"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="Path to graph directory (contains nodes.jsonl, edges.jsonl)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="graph.html",
        help="Output HTML file (default: graph.html)"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open in browser after generating"
    )
    parser.add_argument(
        "--height",
        type=str,
        default="900px",
        help="Canvas height (default: 900px)"
    )
    parser.add_argument(
        "--width",
        type=str,
        default="100%",
        help="Canvas width (default: 100%%)"
    )
    parser.add_argument(
        "--light",
        action="store_true",
        help="Use light theme instead of dark"
    )

    args = parser.parse_args()

    # Validate input path
    graph_dir = Path(args.input).resolve()
    if not graph_dir.exists():
        print(f"Error: Graph directory not found: {graph_dir}", file=sys.stderr)
        return 1
    if not graph_dir.is_dir():
        print(f"Error: Not a directory: {graph_dir}", file=sys.stderr)
        return 1

    print(f"Loading graph from {graph_dir}...")
    nodes, edges = load_graph(graph_dir)
    print(f"  Loaded {len(nodes)} nodes, {len(edges)} edges")

    print("Building NetworkX graph...")
    G = build_networkx_graph(nodes, edges)

    # Theme
    if args.light:
        bgcolor = "#FFFFFF"
        font_color = "#333333"
    else:
        bgcolor = "#1a1a2e"
        font_color = "#EAEAEA"

    print("Creating visualization...")
    net = create_visualization(
        G,
        height=args.height,
        width=args.width,
        bgcolor=bgcolor,
        font_color=font_color,
    )

    output_path = Path(args.output).resolve()
    print(f"Writing to {output_path}...")

    try:
        net.write_html(str(output_path))

        # Hide loading bar (since stabilization is disabled, it never completes)
        html_content = output_path.read_text(encoding="utf-8")
        html_content = html_content.replace(
            "</style>",
            "#loadingBar { display: none !important; }</style>"
        )
        output_path.write_text(html_content, encoding="utf-8")
    except PermissionError as e:
        print(f"Error: Permission denied writing to {output_path}: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: Failed to write output file: {e}", file=sys.stderr)
        return 1

    print(f"Graph visualization saved to: {output_path}")

    if args.open:
        print("Opening in browser...")
        webbrowser.open(f"file://{output_path.absolute()}")

    return 0


if __name__ == "__main__":
    exit(main())
