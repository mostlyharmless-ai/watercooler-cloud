#!/usr/bin/env python3
"""Test querying the LeanRAG graph via Phase 2 backend."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from watercooler_memory.backends.leanrag import LeanRAGBackend, LeanRAGConfig


def main():
    """Test basic LeanRAG backend queries."""
    # Initialize backend with test-run database
    config = LeanRAGConfig(
        work_dir=Path.home() / ".watercooler/leanrag/test-run",
        leanrag_path=project_root / "external/LeanRAG",
    )

    backend = LeanRAGBackend(config)

    print("=" * 60)
    print("Testing LeanRAG Backend Queries")
    print("=" * 60)

    # Test 1: Search for nodes related to "Graphiti"
    print("\n1. Searching nodes: 'Graphiti'")
    print("-" * 60)
    try:
        nodes = backend.search_nodes(query="Graphiti", max_results=5)
        print(f"Found {len(nodes)} nodes:")
        for i, node in enumerate(nodes, 1):
            print(f"\n  Node {i}:")
            print(f"    ID: {node.get('id')}")
            print(f"    Name: {node.get('name')}")
            print(f"    Score: {node.get('score'):.3f}")
            summary = node.get('summary', '')
            if summary:
                print(f"    Summary: {summary[:100]}...")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    # Test 2: Search for nodes related to "memory backend"
    print("\n2. Searching nodes: 'memory backend'")
    print("-" * 60)
    try:
        nodes = backend.search_nodes(query="memory backend", max_results=5)
        print(f"Found {len(nodes)} nodes:")
        for i, node in enumerate(nodes, 1):
            print(f"\n  Node {i}:")
            print(f"    ID: {node.get('id')}")
            print(f"    Name: {node.get('name')}")
            print(f"    Score: {node.get('score'):.3f}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    # Test 3: Search for facts/relationships
    print("\n3. Searching facts: 'LeanRAG integration'")
    print("-" * 60)
    try:
        facts = backend.search_facts(query="LeanRAG integration", max_results=5)
        print(f"Found {len(facts)} facts:")
        for i, fact in enumerate(facts, 1):
            print(f"\n  Fact {i}:")
            print(f"    ID: {fact.get('id')}")
            print(f"    Source: {fact.get('source_node_id')}")
            print(f"    Target: {fact.get('target_node_id')}")
            print(f"    Fact: {fact.get('fact')}")
            print(f"    Score: {fact.get('score'):.3f}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    # Test 4: Get specific node (if we found any)
    print("\n4. Testing get_node() with entity name")
    print("-" * 60)
    try:
        # Try getting a node we found in search
        nodes = backend.search_nodes(query="Graphiti", max_results=1)
        if nodes:
            node_id = nodes[0].get('id')
            print(f"Entity ID from search: {repr(node_id)}")
            print(f"Type: {type(node_id)}")
            print(f"Getting node with ID: {node_id}")
            node = backend.get_node(node_id)
            if node:
                print(f"  ✓ Retrieved node:")
                print(f"    ID: {node.get('id')}")
                print(f"    Name: {node.get('name')}")
                print(f"    Summary: {node.get('summary', '')[:100]}...")
            else:
                print(f"  ❌ Node not found with ID: {repr(node_id)}")
        else:
            print("  ⚠️  No nodes found in search to test get_node()")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    # Test 5: Get edge (if we found any)
    print("\n5. Testing get_edge() with SOURCE||TARGET format")
    print("-" * 60)
    try:
        facts = backend.search_facts(query="backend", max_results=1)
        if facts:
            edge_id = facts[0].get('id')
            print(f"Getting edge: {edge_id}")
            edge = backend.get_edge(edge_id)
            if edge:
                print(f"  ✓ Retrieved edge:")
                print(f"    ID: {edge.get('id')}")
                print(f"    Source: {edge.get('source_node_id')}")
                print(f"    Target: {edge.get('target_node_id')}")
                print(f"    Fact: {edge.get('fact')}")
            else:
                print(f"  ❌ Edge not found")
        else:
            print("  ⚠️  No facts found in search to test get_edge()")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    # Test 6: Verify capabilities
    print("\n6. Testing get_capabilities()")
    print("-" * 60)
    try:
        caps = backend.get_capabilities()
        print(f"Supports nodes: {caps.supports_nodes}")
        print(f"Supports facts: {caps.supports_facts}")
        print(f"Supports episodes: {caps.supports_episodes}")
        print(f"Supports chunks: {caps.supports_chunks}")
        print(f"Node ID type: {caps.node_id_type}")
        print(f"Edge ID type: {caps.edge_id_type}")
        print(f"Embeddings: {caps.embeddings}")
        print(f"Entity extraction: {caps.entity_extraction}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

    # Test 7: Verify search_episodes raises UnsupportedOperationError
    print("\n7. Testing search_episodes() (should raise error)")
    print("-" * 60)
    try:
        episodes = backend.search_episodes(query="test", max_results=5)
        print(f"  ❌ Expected UnsupportedOperationError but got {len(episodes)} results")
    except Exception as e:
        if "UnsupportedOperationError" in str(type(e).__name__):
            print(f"  ✓ Correctly raised UnsupportedOperationError:")
            print(f"    {e}")
        else:
            print(f"  ❌ Unexpected error: {e}")

    print("\n" + "=" * 60)
    print("Query testing complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
