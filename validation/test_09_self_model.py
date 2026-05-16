import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.self_model import SelfModel

def run_self_model_validation():
    """
    Validates that confidence scores track actual accuracy over time.
    """
    model = SelfModel(event_bus=None)
    metrics = {}
    
    # 1. Successful tasks increase confidence
    for _ in range(5):
        model.update_metric("task_success", True)
        
    conf1 = model.get_confidence("task_execution")
    metrics["confidence_after_success"] = conf1
    
    # 2. Failed tasks decrease confidence
    for _ in range(3):
        model.update_metric("task_success", False)
        
    conf2 = model.get_confidence("task_execution")
    metrics["confidence_after_failures"] = conf2
    
    if conf2 >= conf1:
        raise ValueError("Confidence did not decrease after task failures.")
        
    # 3. Hallucinations
    for _ in range(2):
        model.update_metric("hallucination", True)
        
    hallucination_rate = model.get_metric("hallucination_rate")
    metrics["hallucination_rate"] = hallucination_rate
    
    if hallucination_rate <= 0.0:
        raise ValueError("Hallucination metric did not update correctly.")
        
    return metrics

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Self-Model Validation", run_self_model_validation)
    framework.generate_report()
