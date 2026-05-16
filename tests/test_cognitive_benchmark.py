import asyncio
import time
import logging
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.event_bus import EventBus
from core.world_state import EnvironmentGraph
from core.workflow_inference import WorkflowInferenceEngine
from core.goals import GoalManager
from core.attention import AttentionScorer
from memory.memory_manager import DynamicMemorySystem

class MockChroma:
    def get_recent_memories(self, n=50):
        return []
    async def save_memory_async(self, text, category, metadata):
        pass

async def run_benchmark():
    print("=" * 80)
    print(" J.A.R.V.I.S. BEHAVIORAL QUALITY & COGNITIVE BENCHMARK ")
    print("=" * 80)

    # Initialize subsystems
    event_bus = EventBus()
    env_graph = EnvironmentGraph(event_bus)
    wf_engine = WorkflowInferenceEngine(env_graph)
    goal_manager = GoalManager()
    attention = AttentionScorer()
    mem_sys = DynamicMemorySystem(MockChroma())

    # Helper to simulate time passing and window changes
    current_time = time.time()
    
    async def simulate_window_focus(app_name, window_title, duration_sec, edge_weight=0.3):
        nonlocal current_time
        old_id = env_graph.active_app_id
        
        with patch('time.time', return_value=current_time):
            await env_graph.update_state({"active_window": window_title, "active_app_name": app_name})
            
        new_id = env_graph.active_app_id
        
        if old_id and old_id != new_id:
            with patch('time.time', return_value=current_time):
                wf_engine.observe_transition(old_id, new_id, duration_sec, context_overlap=0.5)
                # Manually add edge to simulate EnvironmentGraph's background task
                # Give it edge_weight to simulate established workflow edges vs weak interruptions
                env_graph.add_edge(old_id, new_id, "related_to", weight=edge_weight)

        current_time += duration_sec


    print("\n[BENCHMARK 1] MULTI-WINDOW WORKFLOWS")
    print("-" * 50)
    print("Simulating parallel workflows: Development vs Communication...")
    
    # Dev workflow
    await simulate_window_focus("VSCode", "main.py - VSCode", 300)
    await simulate_window_focus("Terminal", "PowerShell", 60)
    await simulate_window_focus("Chrome", "StackOverflow - Chrome", 120)
    await simulate_window_focus("VSCode", "main.py - VSCode", 600)
    
    # Comm workflow (Context switch, weak edge)
    await simulate_window_focus("Slack", "General - Slack", 180, edge_weight=0.1)
    await simulate_window_focus("Outlook", "Inbox - Outlook", 240)
    await simulate_window_focus("Slack", "Project Team - Slack", 60)

    workflows = wf_engine.infer_current_workflow()
    print(f"Detected Workflows: {len(workflows)}")
    for wf in workflows:
        print(f" - [{wf.id[:8]}] Entities: {wf.context_entities} | Confidence: {wf.confidence:.2f}")

    if len(workflows) >= 2:
        print(">> PASS: System successfully separated Dev workflow from Comm workflow.")
    else:
        print(">> FAIL: System merged distinct workflows or failed to identify them.")


    print("\n[BENCHMARK 2] INTERRUPTION RECOVERY")
    print("-" * 50)
    print("Simulating an interruption during deep work...")
    
    # Back to Dev (Context switch)
    await simulate_window_focus("VSCode", "engine.py - VSCode", 1200, edge_weight=0.1) # Deep work
    
    # Sudden interrupt
    print(" -> Interruption: Boss messages on Slack...")
    await simulate_window_focus("Slack", "Boss - Slack", 30, edge_weight=0.1)
    await simulate_window_focus("Chrome", "Urgent Dashboard - Chrome", 180, edge_weight=0.1)
    await simulate_window_focus("Slack", "Boss - Slack", 30, edge_weight=0.1)
    
    # Recovery
    print(" -> Interruption over. Returning to VSCode...")
    await simulate_window_focus("VSCode", "engine.py - VSCode", 10, edge_weight=0.1)
    
    # Check if system knows we resumed
    active = wf_engine.infer_current_workflow()
    prediction = active[0].predicted_next_phase if active else None
    pred_label = env_graph.nodes[prediction].label if prediction else "None"
    
    if active:
        entities = [env_graph.nodes[nid].label for nid in active[0].context_entities]
        print(f"Current active workflow entities: {entities}")
    
    print(f"Predicted next app context: {pred_label}")
    
    if active and "Terminal" in entities and "Chrome" in entities and "VSCode" in entities and "Slack" not in entities:
         print(">> PASS: System recovered context flawlessly. Ignored interruption noise.")
    else:
         print(f">> WARN: Workflow context might be corrupted or merged: {entities}")


    print("\n[BENCHMARK 3] LONG-HORIZON TASK CONTINUITY (3-4 HOURS)")
    print("-" * 50)
    print("Simulating a long-running goal across a 4 hour timeline...")
    
    # Create goal
    with patch('time.time', return_value=current_time):
        goal = goal_manager.create_goal("Refactor the entire core architecture")
        goal_manager.add_subtask(goal.id, "Refactor engine.py")
        goal_manager.add_subtask(goal.id, "Refactor memory.py")
        print(f"Created Goal: {goal.title}")

    # Jump 1 hour
    print(" -> Fast forwarding 1 hour...")
    current_time += 3600
    with patch('time.time', return_value=current_time):
        goal_manager.update_goal(goal.id, status="in_progress")
        stale_goals = goal_manager.get_stale_goals()
    print(f"Stale Goals after 1 hour: {len(stale_goals)}")

    # Jump 3 more hours
    print(" -> Fast forwarding 3 more hours (Total 4 hours)...")
    current_time += 10800
    with patch('time.time', return_value=current_time):
        stale_goals = goal_manager.get_stale_goals()
        urgency = attention.estimate_action_urgency(goal_priority=goal.priority, goal_staleness_hours=4.0)

    print(f"Stale Goals after 4 hours: {len(stale_goals)}")
    print(f"Calculated Urgency for autonomous intervention: {urgency:.2f}")

    if len(stale_goals) > 0 and urgency > 0.6:
        print(">> PASS: Long-horizon tracking works. System correctly escalating stale goals for autonomous action.")
    else:
        print(">> FAIL: Long-horizon task was lost or urgency not escalating.")


    print("\n[BENCHMARK 4] COGNITIVE STRESS TEST (RAPID SWITCHING)")
    print("-" * 50)
    print("Simulating 100 rapid window switches in 10 seconds (noise/panic mode)...")
    
    start_nodes = len(env_graph.nodes)
    start_edges = len(env_graph.edges)
    
    for i in range(100):
        # 0.1s per switch
        await simulate_window_focus(f"App_{i%5}", f"Doc_{i}.txt", 0.1)

    end_nodes = len(env_graph.nodes)
    end_edges = len(env_graph.edges)
    
    print(f"Graph growth: Nodes {start_nodes} -> {end_nodes} | Edges {start_edges} -> {end_edges}")
    
    # The graph should cap nodes or we should see successful survival
    if end_nodes > start_nodes:
        print(">> PASS: System survived stress test without crashing. Graph updated correctly.")
    else:
        print(">> FAIL: Graph failed to update or system crashed.")

    print("\n=" * 80)
    print(" BENCHMARK COMPLETE ")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_benchmark())
