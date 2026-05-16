"""
J.A.R.V.I.S. V13 — Automated Stress Test Suite
================================================
Çalıştır: python auto_stress_tests.py
Hiçbir manuel adım gerekmez.
Sonuç: validation_report.json + validation_report.html
"""

import asyncio
import time
import json
import sys
import os
import math
import random
import traceback
import threading
import gc
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any

# ── Project root'u path'e ekle ──
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

RESULTS: Dict[str, Any] = {}

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

# ══════════════════════════════════════════════════════
# TEST 1 — HYPOTHESIS ENGINE: Bayesian Calibration
# ══════════════════════════════════════════════════════
async def test_hypothesis_engine():
    log("TEST 1 — Hypothesis Engine Calibration...")
    result = {"name": "Hypothesis Engine", "status": "UNKNOWN", "details": {}}
    try:
        from core.event_bus import EventBus
        from core.hypothesis_engine import HypothesisEngine

        bus = EventBus()
        engine = HypothesisEngine(bus)

        # Create 10 hypotheses with known truth values
        ids = []
        for i in range(10):
            h_id = engine.create_hypothesis(
                category="intent",
                description=f"User is doing task_{i}",
                base_probability=0.3 + (i * 0.05)
            )
            ids.append(h_id)

        # Reinforce first 5 strongly
        for i in range(5):
            engine.reinforce_hypothesis(ids[i], 0.8, f"evidence_{i}", "test")

        time.sleep(0.1)

        # Check decay on non-reinforced
        later_conf = []
        for i in range(5, 10):
            h = engine.hypotheses.get(ids[i])
            if h:
                later_conf.append(h.confidence)

        # Check reinforced are higher
        reinforced_conf = []
        for i in range(5):
            h = engine.hypotheses.get(ids[i])
            if h:
                reinforced_conf.append(h.confidence)

        avg_reinforced = sum(reinforced_conf) / max(len(reinforced_conf), 1)
        avg_unreinforced = sum(later_conf) / max(len(later_conf), 1)

        # Test hypothesis pruning (max_active=50)
        overflow_ids = []
        for i in range(60):
            h_id = engine.create_hypothesis("state", f"overflow_hyp_{i}", 0.5)
            overflow_ids.append(h_id)
        engine._prune_old_hypotheses()
        active_count = len([h for h in engine.hypotheses.values() if not h.resolved])

        # Test contradiction: resolve a hypothesis as False
        engine.resolve_hypothesis(ids[0], truth_value=False)
        h0 = engine.hypotheses.get(ids[0])
        refuted_conf = h0.confidence if h0 else -1

        result["details"] = {
            "avg_reinforced_confidence": round(avg_reinforced, 3),
            "avg_unreinforced_confidence": round(avg_unreinforced, 3),
            "reinforcement_effect": round(avg_reinforced - avg_unreinforced, 3),
            "active_after_prune": active_count,
            "prune_under_50": active_count <= 50,
            "refuted_confidence": round(refuted_conf, 3),
            "refuted_is_zero": refuted_conf == 0.0,
        }

        passed = (
            avg_reinforced > avg_unreinforced and
            active_count <= 50 and
            refuted_conf == 0.0
        )
        result["status"] = "PASS" if passed else "PARTIAL"
        result["score"] = round(
            (0.4 * (avg_reinforced > avg_unreinforced)) +
            (0.3 * (active_count <= 50)) +
            (0.3 * (refuted_conf == 0.0)), 2
        )

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0
        log(f"  ❌ ERROR: {e}")

    RESULTS["hypothesis_engine"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 2 — WORKFLOW INFERENCE: Accuracy & Cold Start
# ══════════════════════════════════════════════════════
async def test_workflow_inference():
    log("TEST 2 — Workflow Inference Engine...")
    result = {"name": "Workflow Inference", "status": "UNKNOWN", "details": {}}
    try:
        from core.event_bus import EventBus
        from core.world_state import EnvironmentGraph
        from core.workflow_inference import WorkflowInferenceEngine

        bus = EventBus()
        graph = EnvironmentGraph(bus)
        wf = WorkflowInferenceEngine(graph)

        # Simulate coding workflow: VSCode → Terminal → Chrome (StackOverflow) → VSCode
        apps = [
            ("VSCode", "main.py - VSCode", 300),
            ("Terminal", "PowerShell", 60),
            ("Chrome", "StackOverflow - Chrome", 90),
            ("VSCode", "main.py - VSCode", 480),
            ("Terminal", "PowerShell", 45),
            ("VSCode", "main.py - VSCode", 200),
        ]

        node_ids = {}
        prev_id = None
        for app_name, title, duration in apps:
            await graph.update_state({"active_window": title, "active_app_name": app_name})
            cur_id = graph.active_app_id
            node_ids[app_name] = cur_id
            if prev_id and prev_id != cur_id:
                graph.add_edge(prev_id, cur_id, "related_to", weight=0.5)
                wf.observe_transition(prev_id, cur_id, float(duration), context_overlap=0.7)
            prev_id = cur_id

        # Cold start check: workflows should form
        cold_workflows = wf.infer_current_workflow()
        cold_detected = len(cold_workflows) > 0

        # Prediction accuracy
        chrome_id = node_ids.get("Chrome")
        vscode_id = node_ids.get("VSCode")
        predicted = wf._predict_next_node({chrome_id}) if chrome_id else None
        prediction_correct = (predicted == vscode_id)

        # Simulate comm workflow interruption
        for comm_app, title, dur in [
            ("Discord", "General - Discord", 30),
            ("Spotify", "Spotify", 60),
        ]:
            await graph.update_state({"active_window": title, "active_app_name": comm_app})
            comm_id = graph.active_app_id
            if prev_id and prev_id != comm_id:
                graph.add_edge(prev_id, comm_id, "related_to", weight=0.1)
                wf.observe_transition(prev_id, comm_id, float(dur), 0.1)
            prev_id = comm_id

        # After interruption, return to coding
        await graph.update_state({"active_window": "main.py - VSCode", "active_app_name": "VSCode"})
        cur_id = graph.active_app_id
        if prev_id and prev_id != cur_id:
            graph.add_edge(prev_id, cur_id, "related_to", weight=0.5)
            wf.observe_transition(prev_id, cur_id, 10.0, 0.9)

        post_workflows = wf.infer_current_workflow()
        # Check if dev workflow still detectable
        dev_still_active = any(
            vscode_id in wf_obj.context_entities
            for wf_obj in post_workflows
        ) if vscode_id else False

        result["details"] = {
            "cold_start_detected_workflows": len(cold_workflows),
            "cold_detection": cold_detected,
            "prediction_correct": prediction_correct,
            "predicted_app": str(predicted)[:20] if predicted else "None",
            "dev_workflow_survives_interruption": dev_still_active,
            "post_interrupt_workflows": len(post_workflows),
        }

        score = (
            0.3 * cold_detected +
            0.4 * prediction_correct +
            0.3 * dev_still_active
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.6 else ("PARTIAL" if score >= 0.3 else "FAIL")

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["workflow_inference"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 3 — ENVIRONMENT GRAPH: Integrity Under Stress
# ══════════════════════════════════════════════════════
async def test_environment_graph():
    log("TEST 3 — Environment Graph Integrity...")
    result = {"name": "Environment Graph", "status": "UNKNOWN", "details": {}}
    try:
        from core.event_bus import EventBus
        from core.world_state import EnvironmentGraph

        bus = EventBus()
        graph = EnvironmentGraph(bus)

        # Inject 50 rapid app switches
        apps = [f"App_{i}" for i in range(50)]
        start = time.time()
        for app in apps:
            await graph.update_state({
                "active_window": f"{app} - Window",
                "active_app_name": app
            })
        rapid_time = time.time() - start

        node_count = len(graph.nodes)

        # Check for orphan nodes (nodes with no edges)
        # Build edge set
        edge_sources = {e.source_id for e in graph.edges}
        edge_targets = {e.target_id for e in graph.edges}
        all_edged = edge_sources | edge_targets
        orphans = [nid for nid in graph.nodes if nid not in all_edged]
        # Some orphans expected if only 1 transition happened — check ratio
        orphan_ratio = len(orphans) / max(node_count, 1)

        # Add 100 edges rapidly (concurrent-like)
        node_ids = list(graph.nodes.keys())
        edge_errors = 0
        for i in range(min(100, len(node_ids) - 1)):
            try:
                graph.add_edge(node_ids[i], node_ids[i+1], "related_to", 0.5)
            except Exception:
                edge_errors += 1

        # Check for duplicate edges (bad graph state)
        edge_pairs = [(e.source_id, e.target_id, e.relation_type) for e in graph.edges]
        unique_pairs = set(edge_pairs)
        duplicate_edges = len(edge_pairs) - len(unique_pairs)

        # Verify node types
        type_counts = defaultdict(int)
        for node in graph.nodes.values():
            type_counts[node.type] += 1

        result["details"] = {
            "rapid_switch_time_ms": round(rapid_time * 1000),
            "node_count": node_count,
            "orphan_count": len(orphans),
            "orphan_ratio": round(orphan_ratio, 3),
            "edge_errors": edge_errors,
            "duplicate_edges": duplicate_edges,
            "node_types": dict(type_counts),
            "graph_consistent": duplicate_edges == 0 and edge_errors == 0,
        }

        score = (
            0.4 * (duplicate_edges == 0) +
            0.3 * (edge_errors == 0) +
            0.2 * (orphan_ratio < 0.5) +
            0.1 * (rapid_time < 2.0)
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "FAIL")

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["environment_graph"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 4 — EVENT STORM: Queue Resilience
# ══════════════════════════════════════════════════════
async def test_event_storm():
    log("TEST 4 — Event Storm Simulation...")
    result = {"name": "Event Storm", "status": "UNKNOWN", "details": {}}
    try:
        from core.event_bus import EventBus

        bus = EventBus()
        received = []
        errors = []

        def handler(data):
            received.append(data)

        def bad_handler(data):
            raise RuntimeError("Simulated handler crash")

        bus.subscribe("WORLD_STATE_UPDATED", handler)
        bus.subscribe("WORLD_STATE_UPDATED", bad_handler)  # Should not break bus
        bus.subscribe("ANOMALY_DETECTED", handler)

        start = time.time()
        storm_count = 500

        # Fire 500 events rapidly
        for i in range(storm_count):
            bus.publish("WORLD_STATE_UPDATED", {"i": i, "app": f"App_{i % 20}"})
            if i % 10 == 0:
                bus.publish("ANOMALY_DETECTED", {"type": "rapid_switch", "i": i})

        storm_time = time.time() - start

        # Bus should still be functional after storm
        bus.publish("WORLD_STATE_UPDATED", {"i": 9999, "marker": "post_storm"})
        post_storm_received = any(d.get("marker") == "post_storm" for d in received)

        result["details"] = {
            "events_fired": storm_count,
            "events_received": len(received),
            "storm_time_ms": round(storm_time * 1000),
            "bus_functional_after_storm": post_storm_received,
            "bad_handler_didnt_crash_bus": post_storm_received,
            "events_per_second": round(storm_count / max(storm_time, 0.001)),
        }

        score = (
            0.4 * post_storm_received +
            0.3 * (len(received) > 450) +
            0.3 * (storm_time < 2.0)
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "FAIL")

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["event_storm"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 5 — MEMORY SYSTEM: Decay, Reinforcement, Contradiction
# ══════════════════════════════════════════════════════
async def test_memory_system():
    log("TEST 5 — Memory System Validation...")
    result = {"name": "Memory System", "status": "UNKNOWN", "details": {}}
    try:
        from memory.memory_manager import DynamicMemorySystem

        class MockChroma:
            def __init__(self):
                self._store = []
            def get_recent_memories(self, n=50):
                return self._store[-n:]
            async def save_memory_async(self, text, category, metadata):
                self._store.append({"content": text, "category": category, "metadata": metadata})
            def query_memories(self, text, n=5):
                return [m for m in self._store if text[:10].lower() in m["content"].lower()][:n]

        mem = DynamicMemorySystem(MockChroma())

        # Store 20 items
        items = [f"User typically does task {i} in the morning" for i in range(20)]
        for item in items:
            await mem.store(item, "semantic")

        # Working memory should cap at _max_working (20)
        wm_count = len(mem.working_memory)
        wm_capped = wm_count <= mem._max_working

        # Contradiction detection
        await mem.store("User prefers dark mode", "semantic", importance=0.8)
        contradiction = mem._check_contradiction("User prefers light mode")
        contradiction_detected = contradiction is not None

        # Importance scoring — longer content should score higher
        short_imp = mem._score_importance("x")
        long_imp = mem._score_importance(
            "User always opens VSCode before Chrome when starting a development session and typically checks emails first"
        )
        importance_scales = long_imp > short_imp

        # Consolidation log should exist
        has_consolidation = hasattr(mem, '_consolidation_log')

        result["details"] = {
            "working_memory_count": wm_count,
            "working_memory_capped": wm_capped,
            "contradiction_detected": contradiction_detected,
            "importance_scales_with_content": importance_scales,
            "short_importance": round(short_imp, 3),
            "long_importance": round(long_imp, 3),
            "has_consolidation_log": has_consolidation,
        }

        score = (
            0.3 * wm_capped +
            0.3 * contradiction_detected +
            0.2 * importance_scales +
            0.2 * has_consolidation
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "FAIL")

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["memory_system"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 6 — SELF MODEL: Metric Convergence
# ══════════════════════════════════════════════════════
async def test_self_model():
    log("TEST 6 — Self-Model Validation...")
    result = {"name": "Self-Model", "status": "UNKNOWN", "details": {}}
    try:
        from core.self_model import SelfModel, MetricTracker

        # Use temp path to avoid polluting production data
        sm = SelfModel(storage_path="/tmp/jarvis_validation/self_model_test.json")

        # Record 30 successes, 10 failures for planning
        for _ in range(30):
            sm.record_outcome("planning", True)
        for _ in range(10):
            sm.record_outcome("planning", False)

        planning_acc = sm.metrics["planning"].overall_accuracy
        planning_recent = sm.metrics["planning"].recent_accuracy
        converged = abs(planning_acc - 0.75) < 0.1  # Should be ~0.75

        # Record tool reliability
        for _ in range(20):
            sm.record_tool_outcome("APP_OPEN", True)
        for _ in range(5):
            sm.record_tool_outcome("APP_OPEN", False)

        tool_rel = sm.tool_reliability.get("APP_OPEN")
        tool_acc = tool_rel.overall_accuracy if tool_rel else -1

        # Hallucination tracking
        for _ in range(100):
            sm.total_responses += 1
        for _ in range(5):
            sm.hallucination_count += 1
        hal_rate = sm.hallucination_rate

        # Persistence test
        sm.save()
        sm2 = SelfModel(storage_path="/tmp/jarvis_validation/self_model_test.json")
        persisted_acc = sm2.metrics["planning"].overall_accuracy
        persistence_works = abs(persisted_acc - planning_acc) < 0.05

        result["details"] = {
            "planning_accuracy": round(planning_acc, 3),
            "accuracy_converged_to_075": converged,
            "planning_recent_accuracy": round(planning_recent, 3),
            "tool_app_open_accuracy": round(tool_acc, 3),
            "hallucination_rate": round(hal_rate, 3),
            "persistence_works": persistence_works,
        }

        score = (
            0.3 * converged +
            0.2 * (abs(tool_acc - 0.80) < 0.15) +
            0.2 * (hal_rate == 0.05) +
            0.3 * persistence_works
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "FAIL")

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["self_model"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 7 — GOAL MANAGER: Persistence & Autonomy
# ══════════════════════════════════════════════════════
async def test_goal_manager():
    log("TEST 7 — Goal Manager Validation...")
    result = {"name": "Goal Manager", "status": "UNKNOWN", "details": {}}
    try:
        from core.goals import GoalManager, Goal

        gm = GoalManager(storage_path="/tmp/jarvis_validation/goals_test.json")

        # Add 10 goals
        ids = []
        for i in range(10):
            gid = gm.add_goal(
                title=f"Test Goal {i}",
                priority=i % 3 + 1,
                autonomous=(i % 2 == 0)
            )
            ids.append(gid)

        # Test priority ordering
        next_goal = gm.get_next_actionable_goal()
        highest_priority = next_goal.priority if next_goal else -1

        # Test stale detection (staleness_hours)
        g = gm.goals.get(ids[0])
        staleness = g.staleness_hours if g else -1

        # Test completion
        gm.mark_completed(ids[0])
        completed = gm.goals.get(ids[0])
        completion_works = completed.status == "completed" if completed else False

        # Test persistence
        gm.save_goals()
        gm2 = GoalManager(storage_path="/tmp/jarvis_validation/goals_test.json")
        persisted_count = len(gm2.goals)
        persistence_works = persisted_count == len(gm.goals)

        # Test autonomous filter
        autonomous_goals = [g for g in gm.goals.values() if g.autonomous]
        autonomous_count = len(autonomous_goals)

        result["details"] = {
            "goals_added": len(ids),
            "next_goal_priority": highest_priority,
            "staleness_tracked": staleness >= 0,
            "completion_works": completion_works,
            "persistence_works": persistence_works,
            "persisted_count": persisted_count,
            "autonomous_goals": autonomous_count,
        }

        score = (
            0.3 * completion_works +
            0.3 * persistence_works +
            0.2 * (staleness >= 0) +
            0.2 * (autonomous_count >= 4)
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "FAIL")

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["goal_manager"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 8 — MEMORY GROWTH: Long-Session Proxy
# ══════════════════════════════════════════════════════
async def test_memory_growth():
    log("TEST 8 — Memory Growth (Long-Session Proxy)...")
    result = {"name": "Memory Growth", "status": "UNKNOWN", "details": {}}
    try:
        import tracemalloc
        from core.event_bus import EventBus
        from core.world_state import EnvironmentGraph
        from core.workflow_inference import WorkflowInferenceEngine
        from core.hypothesis_engine import HypothesisEngine

        tracemalloc.start()
        bus = EventBus()
        graph = EnvironmentGraph(bus)
        wf = WorkflowInferenceEngine(graph)
        hyp = HypothesisEngine(bus)

        snapshot1 = tracemalloc.take_snapshot()

        # Simulate 200 cycles (proxy for long session)
        apps = ["VSCode", "Chrome", "Terminal", "Discord", "Spotify", "Slack", "Notion"]
        prev_id = None
        hyp_ids = []

        for cycle in range(200):
            app = apps[cycle % len(apps)]
            await graph.update_state({
                "active_window": f"{app} - Cycle {cycle}",
                "active_app_name": app
            })
            cur_id = graph.active_app_id
            if prev_id and prev_id != cur_id:
                graph.add_edge(prev_id, cur_id, "related_to", 0.5)
                wf.observe_transition(prev_id, cur_id, float(cycle % 60 + 1), 0.5)
            prev_id = cur_id

            # Create + auto-prune hypotheses
            hid = hyp.create_hypothesis("intent", f"hypothesis_{cycle}", 0.4)
            hyp_ids.append(hid)
            if cycle % 50 == 0:
                hyp._prune_old_hypotheses()

            # Clean up workflow events buffer
            if len(wf._recent_events) > wf._max_events:
                wf._recent_events = wf._recent_events[-wf._max_events:]

        snapshot2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot2.compare_to(snapshot1, 'lineno')
        total_growth_kb = sum(s.size_diff for s in stats) / 1024

        # Check bounded structures
        wf_events_bounded = len(wf._recent_events) <= wf._max_events
        hyp_bounded = len(hyp.hypotheses) <= hyp._max_active + 20
        graph_nodes = len(graph.nodes)

        result["details"] = {
            "cycles_simulated": 200,
            "memory_growth_kb": round(total_growth_kb, 1),
            "growth_acceptable": total_growth_kb < 5000,
            "workflow_events_bounded": wf_events_bounded,
            "hypothesis_pool_bounded": hyp_bounded,
            "graph_nodes_after_200_cycles": graph_nodes,
            "graph_nodes_bounded": graph_nodes <= 50,
        }

        score = (
            0.4 * (total_growth_kb < 5000) +
            0.2 * wf_events_bounded +
            0.2 * hyp_bounded +
            0.2 * (graph_nodes <= 50)
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "FAIL")

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["memory_growth"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 9 — REFLECTION ENGINE
# ══════════════════════════════════════════════════════
async def test_reflection_engine():
    log("TEST 9 — Reflection Engine...")
    result = {"name": "Reflection Engine", "status": "UNKNOWN", "details": {}}
    try:
        from core.reflection import ReflectionEngine

        class MockBrain:
            async def think(self, prompt):
                return '{"score": 0.3, "is_satisfactory": false, "action_recommendation": "replan", "issues": ["tool failed"]}'

        engine = ReflectionEngine(MockBrain())

        # Test 1: Successful tool execution
        class SuccessData:
            class _Node:
                class _Status:
                    value = "completed"
                id = "n1"; type = type('T', (), {'value': 'tool_call'})(); action = "APP_OPEN"; status = _Status()
                result = "Application opened successfully"; error = None
            nodes = {"n1": _Node()}

        success_critique = await engine.critique_execution("Open VSCode", SuccessData())
        success_satisfied = success_critique.get("is_satisfactory", False)

        # Test 2: Failed tool execution
        class FailData:
            class _Node:
                class _Status:
                    value = "failed"
                id = "n1"; type = type('T', (), {'value': 'tool_call'})(); action = "APP_OPEN"; status = _Status()
                result = "Application not found error"; error = "not found"
            nodes = {"n1": _Node()}

        fail_critique = await engine.critique_execution("Open VSCode", FailData())
        fail_caught = not fail_critique.get("is_satisfactory", True)

        # Test 3: History tracking
        history_tracked = len(engine.reflection_history) >= 2

        # Test 4: Tool verification rules exist
        has_rules = len(engine._verification_rules) >= 5

        result["details"] = {
            "success_execution_satisfied": success_satisfied,
            "failure_caught": fail_caught,
            "history_tracked": history_tracked,
            "history_count": len(engine.reflection_history),
            "verification_rules_count": len(engine._verification_rules),
            "has_adequate_rules": has_rules,
        }

        score = (
            0.3 * success_satisfied +
            0.3 * fail_caught +
            0.2 * history_tracked +
            0.2 * has_rules
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.7 else ("PARTIAL" if score >= 0.4 else "FAIL")

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["reflection_engine"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# TEST 10 — TOOL ROUTER (if sentence_transformers available)
# ══════════════════════════════════════════════════════
async def test_tool_router():
    log("TEST 10 — Tool Router Semantic Matching...")
    result = {"name": "Tool Router", "status": "UNKNOWN", "details": {}}
    try:
        from core.tool_router import AutonomousToolRouter

        router = AutonomousToolRouter()

        test_cases = [
            ("haritada İstanbul'u göster", "MAP_SHOW"),
            ("grafik çiz veri görselleştir", "CHART_SHOW"),
            ("web'de ara haber bul", "WEB_SEARCH"),
            ("müzik çal Spotify aç", "APP_OPEN"),
        ]

        correct = 0
        details = []
        for query, expected in test_cases:
            matches = router.route(query, context={})
            top_match = matches[0].tool_tag if matches else "NONE"
            ok = top_match == expected
            if ok:
                correct += 1
            details.append({"query": query, "expected": expected, "got": top_match, "ok": ok})

        accuracy = correct / len(test_cases)

        # Test profile persistence
        router.record_outcome("MAP_SHOW", True, 120)
        router.record_outcome("MAP_SHOW", False, 80)
        profile = router._profiles.get("MAP_SHOW")
        profile_tracked = profile is not None and profile.total_calls >= 2

        result["details"] = {
            "routing_accuracy": round(accuracy, 2),
            "correct_routes": correct,
            "total_cases": len(test_cases),
            "profile_tracking": profile_tracked,
            "cases": details,
        }

        score = (
            0.7 * accuracy +
            0.3 * profile_tracked
        )
        result["score"] = round(score, 2)
        result["status"] = "PASS" if score >= 0.6 else ("PARTIAL" if score >= 0.3 else "FAIL")

    except ImportError:
        result["status"] = "SKIPPED"
        result["score"] = 0.5
        result["note"] = "sentence_transformers not installed — skipped"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        result["score"] = 0.0

    RESULTS["tool_router"] = result
    log(f"  → {result['status']} | score={result.get('score', 0)}")
    return result


# ══════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════
async def main():
    print("\n" + "=" * 60)
    print("  J.A.R.V.I.S. V13 — AUTOMATED VALIDATION SUITE")
    print("=" * 60 + "\n")

    start_time = time.time()

    tests = [
        test_hypothesis_engine,
        test_workflow_inference,
        test_environment_graph,
        test_event_storm,
        test_memory_system,
        test_self_model,
        test_goal_manager,
        test_memory_growth,
        test_reflection_engine,
        test_tool_router,
    ]

    for test_fn in tests:
        try:
            await test_fn()
        except Exception as e:
            log(f"  ❌ FATAL: {test_fn.__name__} — {e}")
        print()

    total_time = time.time() - start_time

    # ── Summary ──
    print("=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)

    scores = []
    passed = failed = errors = skipped = 0
    for key, res in RESULTS.items():
        status = res.get("status", "?")
        score = res.get("score", 0)
        scores.append(score)
        icon = {"PASS": "✅", "PARTIAL": "⚠️", "FAIL": "❌", "ERROR": "💥", "SKIPPED": "⏭️"}.get(status, "?")
        print(f"  {icon} {res.get('name', key):<30} score={score:.2f}  [{status}]")
        if status == "PASS": passed += 1
        elif status in ("FAIL",): failed += 1
        elif status == "ERROR": errors += 1
        elif status == "SKIPPED": skipped += 1
        else: failed += 1

    avg_score = sum(scores) / max(len(scores), 1)
    print(f"\n  Overall Score: {avg_score:.2f}/1.00")
    print(f"  Pass: {passed}  |  Partial/Fail: {failed}  |  Errors: {errors}  |  Skipped: {skipped}")
    print(f"  Time: {total_time:.1f}s\n")

    # ── Save JSON ──
    report = {
        "timestamp": datetime.now().isoformat(),
        "overall_score": round(avg_score, 3),
        "total_time_s": round(total_time, 1),
        "summary": {"passed": passed, "failed": failed, "errors": errors, "skipped": skipped},
        "tests": RESULTS,
    }

    os.makedirs("validation_output", exist_ok=True)
    json_path = "validation_output/auto_test_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"  📁 JSON report: {json_path}")

    # ── Generate HTML report ──
    _generate_html_report(report)

    return report


def _generate_html_report(report: dict):
    html = f"""<!DOCTYPE html>
<html lang="tr">
<head><meta charset="utf-8">
<title>J.A.R.V.I.S. V13 Validation Report</title>
<style>
  body {{ font-family: system-ui; max-width: 900px; margin: 40px auto; padding: 20px; background: #0a0f1e; color: #c8d8f0; }}
  h1 {{ color: #00c8ff; }} h2 {{ color: #7fc8ff; border-bottom: 1px solid #1a3a5c; padding-bottom: 6px; }}
  .score {{ font-size: 3em; color: #00e87a; font-weight: bold; }}
  .card {{ background: #0e1a2e; border: 1px solid #1a3a5c; border-radius: 8px; padding: 16px; margin: 12px 0; }}
  .PASS {{ color: #00e87a; }} .PARTIAL {{ color: #ffd700; }} .FAIL {{ color: #ff4444; }} .ERROR {{ color: #ff6b35; }} .SKIPPED {{ color: #888; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ padding: 8px 12px; border-bottom: 1px solid #1a3a5c; text-align: left; }}
  th {{ color: #7fc8ff; }}
  pre {{ background: #060b14; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; color: #a0b8d0; }}
  .bar {{ background: #1a3a5c; border-radius: 4px; height: 8px; }}
  .bar-fill {{ background: #00c8ff; border-radius: 4px; height: 8px; }}
</style>
</head>
<body>
<h1>🤖 J.A.R.V.I.S. V13 — Automated Validation Report</h1>
<p>Generated: {report['timestamp']} | Duration: {report['total_time_s']}s</p>
<div class="card">
  <div class="score">{report['overall_score']:.2f}<span style="font-size:.4em; color:#7fc8ff">/1.00</span></div>
  <p>Pass: {report['summary']['passed']} | Fail: {report['summary']['failed']} | Error: {report['summary']['errors']} | Skipped: {report['summary']['skipped']}</p>
</div>
<h2>Test Results</h2>
<table>
<tr><th>Test</th><th>Status</th><th>Score</th><th>Bar</th></tr>
"""
    for key, res in report["tests"].items():
        st = res.get("status", "?")
        sc = res.get("score", 0)
        fill = int(sc * 100)
        html += f"""<tr>
  <td>{res.get('name', key)}</td>
  <td class="{st}">{st}</td>
  <td>{sc:.2f}</td>
  <td><div class="bar"><div class="bar-fill" style="width:{fill}%"></div></div></td>
</tr>"""

    html += "</table>\n<h2>Details</h2>"
    for key, res in report["tests"].items():
        details = res.get("details", {})
        err = res.get("error", "")
        html += f"""<div class="card">
  <h3 class="{res.get('status','?')}">{res.get('name', key)} — {res.get('status','?')}</h3>
  <pre>{json.dumps(details, indent=2, ensure_ascii=False)}</pre>
  {f'<p style="color:#ff4444">Error: {err}</p>' if err else ''}
</div>"""

    html += "</body></html>"

    html_path = "validation_output/auto_test_report.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  📊 HTML report: {html_path}")


if __name__ == "__main__":
    asyncio.run(main())