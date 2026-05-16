import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.world_state import EnvironmentGraph, GraphNode, GraphEdge
import random
import threading
import time

def run_environment_graph_stress_test():
    graph = EnvironmentGraph()
    metrics = {}
    
    node_ids = []
    
    # 1. Stress Test: Node Injection
    for i in range(1000):
        # We enforce some sleep if needed, but since label changes it should be fine.
        node = graph.add_node("entity", f"node_{i}", {"value": i})
        node_ids.append(node.id)
        
    metrics["nodes_after_injection"] = len(graph.nodes)
    
    if len(graph.nodes) != 1000:
        raise ValueError(f"Graph failed to inject 1000 nodes correctly. Only has {len(graph.nodes)}")

    # 2. Stress Test: Edge Mutation
    for i in range(999):
        graph.add_edge(node_ids[i], node_ids[i+1], "connects_to")
        
    metrics["edges_after_mutation"] = len(graph.edges)
    
    # 3. Concurrent Updates
    def update_graph(start, end):
        for i in range(start, end):
            n_id = node_ids[i]
            node = graph.nodes.get(n_id)
            if node:
                node.properties = getattr(node, 'properties', {})
                node.properties["updated"] = True
                random_target = node_ids[random.randint(0, 999)]
                graph.add_edge(n_id, random_target, "random_link")
                
    threads = []
    for i in range(10):
        t = threading.Thread(target=update_graph, args=(i*100, (i+1)*100))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    # Verify graph consistency
    orphan_count = 0
    for node_id, node in graph.nodes.items():
        connected = False
        for edge in graph.edges:
            if edge.source_id == node_id or edge.target_id == node_id:
                connected = True
                break
        if not connected:
            orphan_count += 1
            
    metrics["orphan_nodes"] = orphan_count
    metrics["total_edges_final"] = len(graph.edges)
    
    if orphan_count > 0:
        raise ValueError(f"Graph corruption detected: {orphan_count} orphan nodes.")
        
    # Check dangling references
    dangling = 0
    for edge in graph.edges:
        if edge.source_id not in graph.nodes or edge.target_id not in graph.nodes:
            dangling += 1
            
    metrics["dangling_edges"] = dangling
    if dangling > 0:
        raise ValueError(f"Graph corruption detected: {dangling} dangling edges.")
        
    return metrics

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Environment Graph Integrity Test", run_environment_graph_stress_test)
    framework.generate_report()
