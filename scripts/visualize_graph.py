#!/usr/bin/env python3
"""Interactive graph visualization for Watercooler baseline graph.

Uses pyvis (vis.js wrapper) for force-directed layout with spring-relaxation
physics and interactive exploration.

NOTE: This module uses `from __future__ import annotations` to defer type
annotation evaluation, allowing the module to be imported even when optional
dependencies (networkx, pyvis) are not installed.

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

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Check for optional dependencies
_MISSING_DEPS_ERROR: ImportError | None = None
try:
    import networkx as nx
    from pyvis.network import Network
except ImportError as e:
    _MISSING_DEPS_ERROR = e
    # Define placeholders so module can still be imported for testing
    nx = None  # type: ignore[assignment]
    Network = None  # type: ignore[assignment, misc]

# Flag for tests to check if deps are available
DEPS_AVAILABLE = _MISSING_DEPS_ERROR is None


# Color schemes
COLORS = {
    "thread": {
        "OPEN": "#4CAF50",  # Green
        "CLOSED": "#9E9E9E",  # Gray
        "IN_REVIEW": "#FF9800",  # Orange
        "BLOCKED": "#F44336",  # Red
    },
    "entry": {
        "Note": "#2196F3",  # Blue
        "Plan": "#9C27B0",  # Purple
        "Decision": "#FF5722",  # Deep Orange
        "PR": "#00BCD4",  # Cyan
        "Closure": "#607D8B",  # Blue Gray
    },
    "edge": {
        "contains": "#666666",
        "starts": "#00FF88",  # Bright green for thread-start edges
        "followed_by": "#BBBBBB",
        "references": "#FF00FF",  # Magenta for cross-references
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


def transform_edges_to_starts(
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Transform 'contains' edges to a single 'starts' edge per thread.

    Instead of having all entries connected to their thread via 'contains' edges,
    we only keep the edge from the first entry (entry index 1) to the thread,
    and rename it to 'starts'. This reduces visual clutter significantly.

    The 'followed_by' edges between entries are kept as-is, maintaining the
    sequence chain within each thread.

    Args:
        edges: Original edge list from edges.jsonl

    Returns:
        Transformed edge list with 'starts' edges replacing most 'contains' edges
    """
    transformed = []
    seen_threads = set()

    # Sort edges so we process entry:topic:1 before entry:topic:2, etc.
    # Entry IDs follow pattern "entry:<topic>:<index>"
    def edge_sort_key(e):
        target = e.get("target", "")
        if target.startswith("entry:"):
            parts = target.rsplit(":", 1)
            try:
                return (parts[0], int(parts[1]))
            except (ValueError, IndexError):
                pass
        return (target, 0)

    sorted_edges = sorted(edges, key=edge_sort_key)

    for edge in sorted_edges:
        edge_type = edge.get("type", "")

        if edge_type == "contains":
            # Only keep the first 'contains' edge per thread (becomes 'starts')
            source = edge.get("source", "")  # thread:topic
            if source not in seen_threads:
                seen_threads.add(source)
                # Create a 'starts' edge (reverse direction: entry -> thread)
                transformed.append({
                    **edge,
                    "type": "starts",
                    "source": edge.get("target"),  # entry is now source
                    "target": source,  # thread is now target
                })
        else:
            # Keep all other edges (followed_by, etc.) as-is
            transformed.append(edge)

    return transformed


def build_networkx_graph(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    layout_mode: str = "hanging",
) -> nx.DiGraph:
    """Build NetworkX graph from nodes and edges.

    Args:
        nodes: List of node dicts (each must have 'id' key)
        edges: List of edge dicts (each must have 'source' and 'target' keys)
        layout_mode: "cluster" for original (all contains edges), "hanging" for starts-only

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

    # Transform edges based on layout mode
    if layout_mode == "hanging":
        edges = transform_edges_to_starts(edges)

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
            f"Title: {node.get('title') or '-'}",
            f"Type: {node.get('entry_type') or 'Note'}",
            f"Agent: {node.get('agent') or '-'}",
            f"Role: {node.get('role') or '-'}",
            f"Time: {node.get('timestamp') or '-'}",
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


def generate_detail_panel_css_html(is_dark: bool = True) -> str:
    """Generate CSS and HTML structure for the node detail panel.

    Args:
        is_dark: Whether using dark theme

    Returns:
        HTML string with CSS styles and panel div to inject before </body>
    """
    bg_color = "#1e1e2e" if is_dark else "#f5f5f5"
    text_color = "#cdd6f4" if is_dark else "#333333"
    border_color = "#45475a" if is_dark else "#ddd"
    header_bg = "#313244" if is_dark else "#e8e8e8"
    key_color = "#89b4fa" if is_dark else "#0066cc"
    string_color = "#a6e3a1" if is_dark else "#008800"
    number_color = "#fab387" if is_dark else "#cc6600"

    return f'''
<style>
html, body {{
    height: 100%;
    margin: 0;
    display: flex;
    flex-direction: column;
}}
.card {{
    flex: 0 0 50% !important;
    height: 50vh !important;
    min-height: 350px !important;
    margin: 0 !important;
}}
#mynetwork, #mynetwork.card-body {{
    height: 100% !important;
    min-height: 100% !important;
}}
#detailPanel {{
    background: {bg_color};
    color: {text_color};
    border-top: 2px solid {border_color};
    padding: 0;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    flex: 1 1 50%;
    height: 50vh;
    min-height: 200px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}}
#detailHeader {{
    background: {header_bg};
    padding: 12px 20px;
    font-weight: 600;
    font-size: 14px;
    border-bottom: 1px solid {border_color};
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
}}
#detailHeader .node-type {{
    background: #89b4fa;
    color: #1e1e2e;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    text-transform: uppercase;
}}
#detailHeader .node-type.thread {{ background: #f9e2af; }}
#detailHeader .node-type.entry {{ background: #89b4fa; }}
#detailContent {{
    padding: 16px 20px;
    overflow-y: auto;
    flex-grow: 1;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    grid-auto-rows: min-content;
    align-content: start;
    gap: 8px 20px;
}}
#detailContent .field {{
    display: flex;
    flex-direction: column;
    gap: 2px;
}}
#detailContent .field.wide {{
    grid-column: 1 / -1;
}}
#detailContent .field-key {{
    color: {key_color};
    font-size: 11px;
    text-transform: uppercase;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
#detailContent .field-value {{
    font-size: 13px;
    line-height: 1.5;
    word-break: break-word;
}}
#detailContent .field-value.string {{ color: {string_color}; }}
#detailContent .field-value.number {{ color: {number_color}; }}
#detailContent .field-value.summary {{
    background: {header_bg};
    padding: 10px;
    border-radius: 4px;
    font-size: 12px;
    min-height: 60px;
    max-height: 40vh;
    overflow-y: auto;
    white-space: pre-wrap;
}}
#detailPlaceholder {{
    color: #6c7086;
    padding: 40px;
    text-align: center;
    font-style: italic;
}}
.embedding-vector {{
    cursor: pointer;
    position: relative;
}}
.embedding-vector .embedding-full {{
    display: none;
}}
.embedding-vector.expanded .embedding-preview {{
    display: none;
}}
.embedding-vector.expanded .embedding-full {{
    display: block;
    max-height: 200px;
    overflow-y: auto;
}}
</style>

<div id="detailPanel">
    <div id="detailPlaceholder">Click on a node to view its details</div>
</div>
'''


def generate_detail_panel_js(nodes: List[Dict[str, Any]]) -> str:
    """Generate JavaScript for the node detail panel.

    This JavaScript must be injected INSIDE the pyvis script block
    (after drawGraph();) so it has access to the 'network' variable.

    Args:
        nodes: List of node data dicts

    Returns:
        JavaScript code string (no <script> tags)
    """
    # Serialize nodes to JSON for JavaScript access
    nodes_json = json.dumps({node["id"]: node for node in nodes if "id" in node})

    return f'''
// === Detail Panel JavaScript (injected into pyvis script) ===
var nodeData = {nodes_json};

var displayOrder = ['id', 'type', 'topic', 'title', 'status', 'ball', 'entry_type', 'agent', 'role', 'timestamp', 'entry_count', 'last_updated', 'summary', 'body', 'embedding', 'file_refs', 'pr_refs', 'commit_refs'];
var wideFields = ['summary', 'title', 'body', 'embedding'];
var skipFields = [];  // Show all fields

function formatValue(key, value) {{
    if (value === null || value === undefined) return '<span class="field-value">—</span>';
    if (key === 'embedding' && Array.isArray(value)) {{
        // Show embedding with expandable full vector
        var preview = value.slice(0, 10).map(function(v) {{ return v.toFixed(6); }}).join(', ');
        var remaining = value.length - 10;
        return '<span class="field-value summary embedding-vector" title="Click to expand" onclick="this.classList.toggle(\\'expanded\\')">' +
            '<span class="embedding-preview">[' + preview + (remaining > 0 ? ', ... +' + remaining + ' more' : '') + ']</span>' +
            '<span class="embedding-full">[' + value.map(function(v) {{ return v.toFixed(6); }}).join(', ') + ']</span>' +
            ' <em>(' + value.length + ' dims)</em></span>';
    }}
    if (typeof value === 'string') {{
        if (key === 'summary' || key === 'body') {{
            return '<span class="field-value summary">' + escapeHtml(value) + '</span>';
        }}
        return '<span class="field-value string">' + escapeHtml(value) + '</span>';
    }}
    if (typeof value === 'number') return '<span class="field-value number">' + value + '</span>';
    if (Array.isArray(value)) {{
        if (value.length === 0) return '<span class="field-value">[]</span>';
        return '<span class="field-value">[' + value.map(function(v) {{ return escapeHtml(String(v)); }}).join(', ') + ']</span>';
    }}
    return '<span class="field-value">' + escapeHtml(JSON.stringify(value)) + '</span>';
}}

function escapeHtml(text) {{
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}}

function showNodeDetail(nodeId) {{
    var node = nodeData[nodeId];
    if (!node) return;

    var panel = document.getElementById('detailPanel');
    var nodeType = node.type || 'entry';
    var title = node.topic || node.title || nodeId;

    var html = '<div id="detailHeader">' +
        '<span>' + escapeHtml(title) + '</span>' +
        '<span class="node-type ' + nodeType + '">' + nodeType + '</span>' +
        '</div><div id="detailContent">';

    // Show fields in display order
    var shown = {{}};
    displayOrder.forEach(function(key) {{
        if (node.hasOwnProperty(key) && !skipFields.includes(key)) {{
            var isWide = wideFields.includes(key);
            html += '<div class="field' + (isWide ? ' wide' : '') + '">' +
                '<span class="field-key">' + key + '</span>' +
                formatValue(key, node[key]) +
                '</div>';
            shown[key] = true;
        }}
    }});

    // Show any remaining fields not in displayOrder
    Object.keys(node).forEach(function(key) {{
        if (!shown[key] && !skipFields.includes(key)) {{
            var isWide = wideFields.includes(key);
            html += '<div class="field' + (isWide ? ' wide' : '') + '">' +
                '<span class="field-key">' + key + '</span>' +
                formatValue(key, node[key]) +
                '</div>';
        }}
    }});

    html += '</div>';
    panel.innerHTML = html;
}}

// === Semantic Similarity Highlighting ===
// Compute cosine similarity between two embedding vectors
function cosineSimilarity(a, b) {{
    if (!a || !b || a.length !== b.length) return 0;
    var dotProduct = 0, normA = 0, normB = 0;
    for (var i = 0; i < a.length; i++) {{
        dotProduct += a[i] * b[i];
        normA += a[i] * a[i];
        normB += b[i] * b[i];
    }}
    if (normA === 0 || normB === 0) return 0;
    return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}}

// Convert similarity (0-1) to a color gradient with gamma curve for better contrast
function similarityToColor(similarity) {{
    // Threshold: only highlight if similarity > 0.3
    if (similarity < 0.3) return null;  // No highlight

    // Map 0.3-1.0 to 0-1, then apply gamma curve
    var normalized = (similarity - 0.3) / 0.7;  // 0 to 1
    var gamma = 0.4;  // < 1 spreads out lower values for better perceptual distinction
    var curved = Math.pow(normalized, gamma);

    // Hue: cyan (180) -> magenta (320) - vibrant range that contrasts with yellow nodes
    var hue = 180 + curved * 140;  // 180 (cyan) to 320 (magenta/pink)
    var saturation = 100;  // Full saturation for vibrancy
    var lightness = 50 + curved * 10;  // 50% to 60% - brighter for high similarity

    return 'hsl(' + hue + ', ' + saturation + '%, ' + lightness + '%)';
}}

// Store original node colors for reset
var originalNodeColors = {{}};
var similarityHighlightActive = false;

function highlightSimilarNodes(selectedNodeId) {{
    var selectedNode = nodeData[selectedNodeId];
    if (!selectedNode || !selectedNode.embedding) {{
        console.log("Selected node has no embedding");
        return;
    }}

    var selectedEmb = selectedNode.embedding;
    var updates = [];
    var similarities = [];

    // Calculate similarity for all nodes
    Object.keys(nodeData).forEach(function(nodeId) {{
        var node = nodeData[nodeId];
        if (nodeId === selectedNodeId) {{
            // Store original and mark as selected
            if (!originalNodeColors[nodeId]) {{
                var visNode = network.body.data.nodes.get(nodeId);
                if (visNode) originalNodeColors[nodeId] = visNode.color;
            }}
            updates.push({{
                id: nodeId,
                borderWidth: 6,
                color: {{ border: '#00FF00', background: originalNodeColors[nodeId] || '#2196F3' }}
            }});
            return;
        }}

        if (!node.embedding) return;

        var similarity = cosineSimilarity(selectedEmb, node.embedding);
        similarities.push({{ id: nodeId, similarity: similarity }});

        // Store original color if not already stored
        if (!originalNodeColors[nodeId]) {{
            var visNode = network.body.data.nodes.get(nodeId);
            if (visNode) originalNodeColors[nodeId] = visNode.color;
        }}

        var highlightColor = similarityToColor(similarity);
        if (highlightColor) {{
            updates.push({{
                id: nodeId,
                borderWidth: 2 + similarity * 6,
                color: {{ border: highlightColor, background: originalNodeColors[nodeId] || '#2196F3' }}
            }});
        }} else {{
            // Reset to original for low similarity
            updates.push({{
                id: nodeId,
                borderWidth: 2,
                color: originalNodeColors[nodeId] || '#2196F3'
            }});
        }}
    }});

    // Apply all updates at once
    network.body.data.nodes.update(updates);
    similarityHighlightActive = true;

    // Log top 5 similar nodes with titles
    similarities.sort(function(a, b) {{ return b.similarity - a.similarity; }});
    var selectedTitle = selectedNode.title || selectedNode.label || selectedNodeId;
    console.log("Top 5 similar to: " + selectedTitle);
    similarities.slice(0, 5).forEach(function(s, i) {{
        var node = nodeData[s.id];
        var title = node.title || node.label || s.id;
        console.log("  " + (i+1) + ". [" + (s.similarity * 100).toFixed(1) + "%] " + title);
    }});
}}

function resetSimilarityHighlight() {{
    if (!similarityHighlightActive) return;

    var updates = [];
    Object.keys(originalNodeColors).forEach(function(nodeId) {{
        updates.push({{
            id: nodeId,
            borderWidth: 2,
            color: originalNodeColors[nodeId]
        }});
    }});

    if (updates.length > 0) {{
        network.body.data.nodes.update(updates);
    }}
    similarityHighlightActive = false;
}}

// Hook into vis.js click event - 'network' is in scope here
network.on("click", function(params) {{
    if (params.nodes.length > 0) {{
        showNodeDetail(params.nodes[0]);
        highlightSimilarNodes(params.nodes[0]);
    }} else {{
        // Clicked on empty space - reset highlights
        resetSimilarityHighlight();
    }}
}});

// === Pinnable Thread Nodes ===
// When a thread node is dragged, pin it in place
// Entry nodes remain free to move with physics
network.on("dragEnd", function(params) {{
    if (params.nodes.length > 0) {{
        var nodeId = params.nodes[0];
        var node = nodeData[nodeId];
        if (node && node.type === "thread") {{
            // Get current position and fix the node there
            var positions = network.getPositions([nodeId]);
            var pos = positions[nodeId];
            network.body.data.nodes.update({{
                id: nodeId,
                fixed: {{ x: true, y: true }},
                x: pos.x,
                y: pos.y
            }});
            console.log("Pinned thread node:", nodeId, "at", pos);
        }}
    }}
}});

// Double-click to unpin a thread node
network.on("doubleClick", function(params) {{
    if (params.nodes.length > 0) {{
        var nodeId = params.nodes[0];
        var node = nodeData[nodeId];
        if (node && node.type === "thread") {{
            network.body.data.nodes.update({{
                id: nodeId,
                fixed: false,
                physics: true
            }});
            console.log("Unpinned thread node:", nodeId);
        }}
    }}
}});

// === Custom Downward Gravity for Entries ===
// Apply a gentle downward force to entry nodes each physics tick
var GRAVITY_STRENGTH = 0.3;  // Pixels per tick downward
network.on("beforeDrawing", function(ctx) {{
    // Apply gravity to entry nodes only (threads are pinned)
    var nodeIds = network.body.data.nodes.getIds();
    nodeIds.forEach(function(nodeId) {{
        var node = nodeData[nodeId];
        if (node && node.type === "entry") {{
            var bodyNode = network.body.nodes[nodeId];
            if (bodyNode && !bodyNode.options.fixed) {{
                // Apply downward velocity
                bodyNode.vy = (bodyNode.vy || 0) + GRAVITY_STRENGTH;
            }}
        }}
    }});
}});
// === End Detail Panel JavaScript ===
'''


def create_visualization(
    G: nx.DiGraph,
    height: str = "700px",
    width: str = "100%",
    bgcolor: str = "#222222",
    font_color: str = "#FFFFFF",
    layout_mode: str = "hanging",
) -> Network:
    """Create pyvis Network from NetworkX graph.

    Args:
        G: NetworkX graph
        height: Canvas height
        width: Canvas width
        bgcolor: Background color
        font_color: Label font color
        layout_mode: "cluster" (original with central gravity) or "hanging" (threads at top)

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

    # Configure physics based on layout mode
    if layout_mode == "cluster":
        # Original cluster mode: central gravity pulls everything together
        physics_options = """
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
            "font": { "size": 12, "face": "arial" },
            "borderWidth": 2,
            "borderWidthSelected": 4,
            "shadow": true
        },
        "edges": {
            "smooth": { "type": "continuous", "forceDirection": "none" },
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.5 } },
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
    """
    else:
        # Hanging mode: no central gravity, threads pinned at top
        physics_options = """
    {
        "physics": {
            "enabled": true,
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
                "gravitationalConstant": -30,
                "centralGravity": 0.0,
                "springLength": 80,
                "springConstant": 0.04,
                "damping": 0.5,
                "avoidOverlap": 0.5
            },
            "stabilization": false,
            "minVelocity": 0.5,
            "maxVelocity": 20
        },
        "nodes": {
            "font": { "size": 12, "face": "arial" },
            "borderWidth": 2,
            "borderWidthSelected": 4,
            "shadow": true
        },
        "edges": {
            "smooth": { "type": "continuous", "forceDirection": "none" },
            "arrows": { "to": { "enabled": true, "scaleFactor": 0.5 } },
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
    """
    net.set_options(physics_options)

    # Add nodes - positioning depends on layout mode
    if layout_mode == "hanging":
        # Hanging mode: threads pinned in a row at top, entries below
        threads = [nid for nid in G.nodes() if G.nodes[nid].get("type") == "thread"]
        thread_count = len(threads)
        thread_spacing = 150  # pixels between threads
        thread_y = -300  # threads at top

        # Map thread topic to x position
        thread_x_map = {}
        start_x = -((thread_count - 1) * thread_spacing) // 2
        for i, thread_id in enumerate(sorted(threads)):
            thread_x_map[thread_id] = start_x + i * thread_spacing
            topic = G.nodes[thread_id].get("topic", "")
            if topic:
                thread_x_map[f"topic:{topic}"] = thread_x_map[thread_id]

        for node_id in G.nodes():
            node_data = G.nodes[node_id]
            node_type = node_data.get("type", "entry")

            if node_type == "thread":
                x_pos = thread_x_map.get(node_id, 0)
                net.add_node(
                    node_id,
                    label=get_node_label(node_data),
                    title=get_node_title(node_data),
                    color=get_node_color(node_data),
                    size=get_node_size(node_data),
                    shape="diamond",
                    group="thread",
                    x=x_pos,
                    y=thread_y,
                    fixed=True,
                    physics=False,
                )
            else:
                # Entry: positioned below thread
                parts = node_id.split(":")
                topic = parts[1] if len(parts) > 1 else ""
                try:
                    entry_idx = int(parts[2]) if len(parts) > 2 else 1
                except ValueError:
                    entry_idx = 1

                x_pos = thread_x_map.get(f"topic:{topic}", 0)
                y_pos = thread_y + 100 + (entry_idx * 30)

                net.add_node(
                    node_id,
                    label=get_node_label(node_data),
                    title=get_node_title(node_data),
                    color=get_node_color(node_data),
                    size=get_node_size(node_data),
                    shape="dot",
                    group="entry",
                    x=x_pos,
                    y=y_pos,
                )
    else:
        # Cluster mode: all nodes free, physics determines positions
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

        # Style edges based on type:
        # - "starts": thick solid green line (entry -> thread anchor)
        # - "followed_by": thin dashed gray line (entry -> entry sequence)
        # - "contains": medium solid gray (legacy, if still present)
        if edge_type == "starts":
            width = 3
            dashes = False
        elif edge_type == "followed_by":
            width = 1
            dashes = True
        else:
            width = 2
            dashes = False

        net.add_edge(
            source,
            target,
            color=get_edge_color(edge_data),
            width=width,
            dashes=dashes,
            title=f"Type: {edge_type}",
        )

    return net


def main() -> int:
    """Main entry point for graph visualization.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Check for missing dependencies
    if _MISSING_DEPS_ERROR is not None:
        print(
            "Error: Missing required dependencies for graph visualization.",
            file=sys.stderr,
        )
        print(
            "Install with: pip install pyvis networkx",
            file=sys.stderr,
        )
        print(f"Details: {_MISSING_DEPS_ERROR}", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        description="Interactive visualization for baseline graph"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Path to graph directory (contains nodes.jsonl, edges.jsonl)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="graph.html",
        help="Output HTML file (default: graph.html)",
    )
    parser.add_argument(
        "--open", action="store_true", help="Open in browser after generating"
    )
    parser.add_argument(
        "--height", type=str, default="900px", help="Canvas height (default: 900px)"
    )
    parser.add_argument(
        "--width", type=str, default="100%", help="Canvas width (default: 100%%)"
    )
    parser.add_argument(
        "--light", action="store_true", help="Use light theme instead of dark"
    )
    parser.add_argument(
        "--layout",
        type=str,
        choices=["cluster", "hanging"],
        default="hanging",
        help="Layout mode: 'cluster' (original with all edges, central gravity) or 'hanging' (threads at top, entries hang down). Default: hanging",
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

    print(f"Building NetworkX graph (layout: {args.layout})...")
    G = build_networkx_graph(nodes, edges, layout_mode=args.layout)

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
        layout_mode=args.layout,
    )

    output_path = Path(args.output).resolve()

    # Validate output directory exists
    output_dir = output_path.parent
    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}", file=sys.stderr)
        return 1
    if not output_dir.is_dir():
        print(f"Error: Output path parent is not a directory: {output_dir}", file=sys.stderr)
        return 1

    print(f"Writing to {output_path}...")

    try:
        net.write_html(str(output_path))

        # Post-process HTML to add features
        html_content = output_path.read_text(encoding="utf-8")

        # Hide loading bar (since stabilization is disabled, it never completes)
        html_content = html_content.replace(
            "</style>", "#loadingBar { display: none !important; }</style>"
        )

        # Add detail panel CSS and HTML before closing body tag
        is_dark = not args.light
        detail_css_html = generate_detail_panel_css_html(is_dark=is_dark)
        html_content = html_content.replace("</body>", f"{detail_css_html}</body>")

        # Inject detail panel JavaScript INSIDE the pyvis script block
        # The JS needs access to 'network' variable which is scoped to pyvis's script
        # Inject after 'drawGraph();' which is typically near the end of pyvis script
        detail_js = generate_detail_panel_js(nodes)
        if "drawGraph();" in html_content:
            html_content = html_content.replace(
                "drawGraph();",
                f"drawGraph();\n{detail_js}"
            )
        else:
            # Fallback: inject before </script> (last one in the pyvis block)
            # Find the last </script> before </body> and inject before it
            print("Warning: Could not find 'drawGraph();' marker, using fallback injection",
                  file=sys.stderr)
            # Wrap in script tags since we're adding after pyvis script closes
            html_content = html_content.replace(
                "</body>",
                f"<script>{detail_js}</script></body>"
            )

        output_path.write_text(html_content, encoding="utf-8")
    except PermissionError as e:
        print(
            f"Error: Permission denied writing to {output_path}: {e}", file=sys.stderr
        )
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
