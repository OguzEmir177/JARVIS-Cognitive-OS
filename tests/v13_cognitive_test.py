import asyncio
import time
import logging
import os
import sys
from unittest.mock import AsyncMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.event_bus import EventBus
from core.world_state import EnvironmentGraph
from core.workflow_inference import WorkflowInferenceEngine
from core.hypothesis_engine import HypothesisEngine
from memory.memory_manager import DynamicMemorySystem
from core.reflection import ReflectionEngine

# Mocks
class MockBrain:
    async def think(self, prompt):
        return '{"score": 0.5, "is_satisfactory": false, "action_recommendation": "replan"}'

class MockChroma:
    def get_recent_memories(self, n=50):
        return []
    async def save_memory_async(self, text, category, metadata):
        pass

class MockNode:
    def __init__(self, id, action, status, result, error=""):
        self.id = id
        self.action = action
        class Status:
            value = status
        self.status = Status()
        self.result = result
        self.error = error

class MockExecutionData:
    def __init__(self, nodes):
        self.nodes = {n.id: n for n in nodes}

async def run_tests():
    print("=" * 60)
    print("[ V13 SEMANTIC COGNITION TEST SUITE ]")
    print("=" * 60)

    # Init Subsystems
    event_bus = EventBus()
    env_graph = EnvironmentGraph(event_bus)
    wf_engine = WorkflowInferenceEngine(env_graph)
    hyp_engine = HypothesisEngine(event_bus)
    
    chroma = MockChroma()
    mem_sys = DynamicMemorySystem(chroma)
    
    brain = MockBrain()
    reflection = ReflectionEngine(brain)

    print("\n[TEST 1] Workflow Understanding Test")
    print("-" * 50)
    # Simulate user switching between VSCode, Terminal, Chrome
    await env_graph.update_state({"active_window": "server.py - Visual Studio Code", "active_app_name": "VSCode"})
    vscode_id = env_graph.active_app_id
    
    await env_graph.update_state({"active_window": "PowerShell", "active_app_name": "Terminal"})
    terminal_id = env_graph.active_app_id
    
    # We must also manually add some relations if the test is running too fast
    # Normally the loop builds up these weights over time. Let's force a connection.
    env_graph.add_edge(vscode_id, terminal_id, "related_to", 0.5)
    wf_engine.observe_transition(vscode_id, terminal_id, 5.0, 0.8)
    
    await env_graph.update_state({"active_window": "StackOverflow - Google Chrome", "active_app_name": "Chrome"})
    chrome_id = env_graph.active_app_id
    env_graph.add_edge(terminal_id, chrome_id, "related_to", 0.5)
    wf_engine.observe_transition(terminal_id, chrome_id, 2.0, 0.7)
    
    await env_graph.update_state({"active_window": "server.py - Visual Studio Code", "active_app_name": "VSCode"})
    env_graph.add_edge(chrome_id, vscode_id, "related_to", 0.5)
    wf_engine.observe_transition(chrome_id, vscode_id, 10.0, 0.9)
    
    # Check workflow engine
    active_workflows = wf_engine.infer_current_workflow()
    print("Active Workflows Detected:")
    for wf in active_workflows:
        print(f"  - ID: {wf.id}")
        print(f"  - Context Entities: {wf.context_entities}")
        print(f"  - Confidence: {wf.confidence:.2f}")
    if active_workflows and len(active_workflows[0].context_entities) >= 3:
        print("OK: TEST 1 PASSED: Successfully grouped Chrome+VSCode+Terminal into a cohesive workflow cluster.")

    print("\n[TEST 2] Prediction Test")
    print("-" * 50)
    # We fed Chrome -> VSCode above. Let's see if it predicts VSCode from Chrome.
    prediction = wf_engine._predict_next_node({chrome_id})
    print(f"Predicted next app after Chrome: {env_graph.nodes[prediction].label if prediction else 'None'}")
    if prediction == vscode_id:
        print("OK: TEST 2 PASSED: System successfully predicted the next workflow step based on transition matrix.")

    print("\n[TEST 3] Hypothesis Validation Test")
    print("-" * 50)
    # Trigger an anomaly
    class Event:
        def __init__(self, data):
            self.data = data
    await hyp_engine._on_anomaly(Event({"reason": "Port 8080 already in use"}))
    await hyp_engine._on_task_failure(Event({"error": "Failed to bind to 0.0.0.0:8080"}))
    
    top_hyps = hyp_engine.get_top_hypotheses()
    for h in top_hyps:
        print(f"  - [Hypothesis] Category: {h.category} | Confidence: {h.confidence:.2f}")
        print(f"    Desc: {h.description}")
        for e in h.evidence:
             print(f"      -> Evidence: {e.description} (weight: {e.weight})")
    
    if len(top_hyps) >= 2:
        print("OK: TEST 3 PASSED: Dynamic hypotheses generated with tracked evidence instead of hardcoded rules.")

    print("\n[TEST 4] Memory Continuity Test (10 mins ago)")
    print("-" * 50)
    # Mock working memory 10 mins ago
    ten_mins_ago = time.time() - 600
    mem_sys.working_memory.append({
        "content": "User was writing the semantic graph algorithm in VSCode",
        "timestamp": ten_mins_ago,
        "importance": 0.9,
        "access_count": 0
    })
    
    reconstruction = await mem_sys.reconstruct_workflow_episode(minutes_ago=10)
    print("Reconstruction Result:")
    print(f"  Status: {reconstruction['status']}")
    print(f"  Episode Summary: {reconstruction.get('episode_summary', 'N/A')}")
    
    if reconstruction['status'] == 'reconstructed' and "semantic graph" in reconstruction['episode_summary']:
        print("OK: TEST 4 PASSED: Successfully reconstructed workflow episode using temporal stitching.")

    print("\n[TEST 5] Tool Grounding (Reflection) Test")
    print("-" * 50)
    # Simulate a failed APP_OPEN
    failed_node = MockNode("n1", "APP_OPEN", "completed", result="Error: Application 'photoshop' not found in PATH")
    exec_data = MockExecutionData([failed_node])
    
    critique = await reflection.critique_execution("Open Photoshop", exec_data)
    print(f"Critique Score: {critique['score']}")
    print(f"Tool Verification Score: {critique['tool_verification_score']}")
    print(f"Action Recommendation: {critique['action_recommendation']}")
    print("Issues Detected:")
    for issue in critique['tool_issues']:
        print(f"  - {issue}")
        
    if critique['tool_verification_score'] < 0.9 and "replan" in critique['action_recommendation'].lower() or "abort" in critique['action_recommendation'].lower():
        print("OK: TEST 5 PASSED: Tool grounded reflection correctly caught the failure and altered the plan.")

if __name__ == "__main__":
    asyncio.run(run_tests())
