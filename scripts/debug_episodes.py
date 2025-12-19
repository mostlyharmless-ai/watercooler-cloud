#!/usr/bin/env python3
"""Debug script to investigate get_episodes issue."""

import asyncio
import os
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from watercooler_memory.backends.graphiti import GraphitiBackend, GraphitiConfig


async def main():
    # Create config
    config = GraphitiConfig(
        openai_api_key=os.environ["OPENAI_API_KEY"],
        falkordb_host="localhost",
        falkordb_port=6379,
        reranker="rrf",
    )
    
    backend = GraphitiBackend(config)
    
    # Test 1: List available graphs
    import redis
    r = redis.Redis(host="localhost", port=6379)
    graph_list = r.execute_command('GRAPH.LIST')
    print(f"Available graphs: {graph_list}")
    
    # Test 2: Get effective group_ids
    effective = backend._get_effective_group_ids(None)
    print(f"Effective group_ids: {effective}")
    
    # Test 3: Get sanitized group_ids
    if effective:
        sanitized = [backend._sanitize_thread_id(gid) for gid in effective]
        print(f"Sanitized group_ids: {sanitized}")
    
    # Test 4: Try to get episodes directly
    print("\n=== Trying get_episodes with no filter ===")
    result = await asyncio.to_thread(backend.get_episodes, group_ids=None, max_episodes=5)
    print(f"Result count: {len(result)}")
    if result:
        print(f"First episode: {result[0]}")
    
    # Test 5: Try with explicit group_id
    print("\n=== Trying get_episodes with explicit group_id ===")
    result2 = await asyncio.to_thread(backend.get_episodes, group_ids=["memory-backend-contract"], max_episodes=5)
    print(f"Result count: {len(result2)}")
    if result2:
        print(f"First episode: {result2[0]}")
    
    # Test 5b: Try search_() directly to see if it returns episodes
    print("\n=== Testing search_() directly for episodes ===")
    search_config = backend._get_search_config()
    search_results = await graphiti.search_(
        query="graphiti",
        config=search_config,
        group_ids=["memory-backend-contract"],
    )
    print(f"Search returned {len(search_results.episodes)} episodes")
    if search_results.episodes:
        print(f"First episode UUID: {search_results.episodes[0].uuid}")
        print(f"First episode name: {search_results.episodes[0].name}")
    
    # Test 6: Query the database directly
    print("\n=== Querying database directly ===")
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client import OpenAIClient
    from graphiti_core.llm_client.config import LLMConfig
    
    falkor_driver = FalkorDriver(host="localhost", port=6379, username="", password="")
    llm_config = LLMConfig(api_key=config.openai_api_key, model="gpt-4o-mini")
    llm_client = OpenAIClient(config=llm_config, reasoning=None, verbosity=None)
    graphiti = Graphiti(graph_driver=falkor_driver, llm_client=llm_client)
    
    from graphiti_core.nodes import EpisodicNode
    
    # Try with "memory-backend-contract"
    episodes = await EpisodicNode.get_by_group_ids(
        graphiti.driver,
        ["memory-backend-contract"],
        limit=5
    )
    print(f"Direct query result count: {len(episodes)}")
    if episodes:
        print(f"First episode UUID: {episodes[0].uuid}")
        print(f"First episode group_id: {episodes[0].group_id}")


if __name__ == "__main__":
    asyncio.run(main())
