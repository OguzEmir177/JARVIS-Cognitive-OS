import sys
import os
import time
import math

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.workflow_inference import WorkflowInferenceEngine
from core.world_state import EnvironmentGraph

def run_workflow_inference_test():
    graph = EnvironmentGraph()
    engine = WorkflowInferenceEngine(graph)
    metrics = {}
    
    # Setup graph relations for "Video Editing" workflow
    n_prem = graph.add_node("app", "Premiere Pro").id
    n_phot = graph.add_node("app", "Photoshop").id
    n_ae = graph.add_node("app", "After Effects").id
    n_chr = graph.add_node("app", "Chrome - YouTube").id
    n_slack = graph.add_node("app", "Slack").id
    
    graph.add_edge(n_prem, n_phot, "related_to", 0.8)
    graph.add_edge(n_prem, n_ae, "related_to", 0.7)
    
    # 1. Train Transition Matrix
    # Premiere -> Photoshop -> Premiere
    for _ in range(10):
        engine.observe_transition(n_prem, n_phot, duration=30.0, context_overlap=0.5)
        engine.observe_transition(n_phot, n_prem, duration=120.0, context_overlap=0.8)
        
    # Premiere -> After Effects -> Premiere
    for _ in range(5):
        engine.observe_transition(n_prem, n_ae, duration=45.0, context_overlap=0.6)
        engine.observe_transition(n_ae, n_prem, duration=300.0, context_overlap=0.9)
        
    # 2. Test Inference during a session
    engine.observe_transition(n_prem, n_phot, duration=20.0, context_overlap=0.4)
    
    active_workflows = engine.infer_current_workflow()
    
    if not active_workflows:
        raise ValueError("Failed to infer any active workflow.")
        
    top_workflow = active_workflows[0]
    metrics["top_confidence"] = top_workflow.confidence
    metrics["predicted_next"] = top_workflow.predicted_next_phase
    
    # Wait, if both n_prem and n_phot are in the cluster, they are excluded from the prediction
    # unless predict_next_node predicts something outside the cluster. 
    # But usually, the next *step* is what we want.
    # Let's see what it predicts.
    
    # 3. Simulate an interruption
    engine.observe_transition(n_phot, n_slack, duration=5.0, context_overlap=0.0)
    active_after_interruption = engine.infer_current_workflow()
    metrics["prediction_after_interruption"] = active_after_interruption[0].predicted_next_phase if active_after_interruption else None
    
    return metrics

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Workflow Inference Benchmark", run_workflow_inference_test)
    framework.generate_report()
