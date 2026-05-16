"""
[V13.0] J.A.R.V.I.S. Cognitive Self-Model
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The agent's understanding of its own capabilities, accuracies, and failures.
Tracks:
- Prediction accuracy
- Planning success rate
- Tool reliability
- Hallucination frequency
- Workflow inference correctness

Used to calibrate confidence and decide when to ask the user for help.
"""
import time
import json
import os
import logging
from typing import Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger("JARVIS.SelfModel")

@dataclass
class MetricTracker:
    total_attempts: int = 0
    successes: int = 0
    recent_history: list = field(default_factory=list) # max 50 booleans
    
    @property
    def overall_accuracy(self) -> float:
        if self.total_attempts == 0: return 0.5 # Unknown = 50%
        return self.successes / self.total_attempts
        
    @property
    def recent_accuracy(self) -> float:
        if not self.recent_history: return self.overall_accuracy
        return sum(self.recent_history) / len(self.recent_history)
        
    def record(self, success: bool):
        self.total_attempts += 1
        if success: self.successes += 1
        self.recent_history.append(success)
        if len(self.recent_history) > 50:
            self.recent_history.pop(0)

class SelfModel:
    """Tracks and evaluates the system's own cognitive performance."""
    def __init__(self, storage_path: str = "memory_db/self_model.json"):
        self.storage_path = storage_path
        
        # Core Cognitive Metrics
        self.metrics = {
            "prediction": MetricTracker(),
            "planning": MetricTracker(),
            "workflow_inference": MetricTracker(),
            "hypothesis_accuracy": MetricTracker(),
            "tool_execution": MetricTracker(),
            "reflection_reliability": MetricTracker()
        }
        
        # Tool-specific reliability
        self.tool_reliability: Dict[str, MetricTracker] = {}
        
        # Hallucination tracking
        self.total_responses = 0
        self.hallucination_count = 0
        
        self.load()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

    def load(self):
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    
                for key, m_data in data.get("metrics", {}).items():
                    if key in self.metrics:
                        self.metrics[key] = MetricTracker(**m_data)
                        
                for t_name, t_data in data.get("tools", {}).items():
                    self.tool_reliability[t_name] = MetricTracker(**t_data)
                    
                self.total_responses = data.get("total_responses", 0)
                self.hallucination_count = data.get("hallucination_count", 0)
        except Exception as e:
            logger.warning(f"Failed to load self-model: {e}")

    def save(self):
        self._ensure_dir()
        try:
            data = {
                "metrics": {k: {"total_attempts": v.total_attempts, 
                               "successes": v.successes,
                               "recent_history": v.recent_history} 
                           for k, v in self.metrics.items()},
                "tools": {k: {"total_attempts": v.total_attempts, 
                             "successes": v.successes,
                             "recent_history": v.recent_history} 
                         for k, v in self.tool_reliability.items()},
                "total_responses": self.total_responses,
                "hallucination_count": self.hallucination_count
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save self-model: {e}")

    # ── RECORDING METHODS ──

    def record_prediction(self, predicted: str, actual: str):
        """Record if a cognitive prediction came true."""
        # Simple match for now
        success = (predicted.lower() == actual.lower())
        self.metrics["prediction"].record(success)
        self.save()

    def record_outcome(self, task_type: str, success: bool):
        """Generic outcome recorder for validation tests."""
        if task_type in self.metrics:
            self.metrics[task_type].record(success)
            self.save()

    def record_tool_outcome(self, tool_name: str, success: bool):
        """Generic tool outcome recorder for validation tests."""
        self.record_tool_execution(tool_name, success)

    def record_planning(self, plan_completed: bool):
        self.metrics["planning"].record(plan_completed)
        self.save()

    def record_tool_execution(self, tool_name: str, success: bool):
        self.metrics["tool_execution"].record(success)
        if tool_name not in self.tool_reliability:
            self.tool_reliability[tool_name] = MetricTracker()
        self.tool_reliability[tool_name].record(success)
        self.save()

    def record_hypothesis_resolution(self, confirmed: bool):
        """When a hypothesis is resolved (true or false), did we predict it well?"""
        self.metrics["hypothesis_accuracy"].record(confirmed)
        self.save()

    def record_response_quality(self, has_hallucination: bool):
        self.total_responses += 1
        if has_hallucination:
            self.hallucination_count += 1
        self.save()

    # ── CALIBRATION QUERIES ──

    def get_confidence_modifier(self, cognitive_task: str) -> float:
        """
        Returns a modifier (0.5 to 1.5) based on historical accuracy.
        Used to scale raw confidence scores.
        """
        if cognitive_task not in self.metrics:
            return 1.0
            
        acc = self.metrics[cognitive_task].recent_accuracy
        # Center around 0.75 as "normal" (modifier 1.0)
        # If accuracy is 1.0, modifier is 1.33
        # If accuracy is 0.5, modifier is 0.66
        return max(0.5, min(1.5, acc / 0.75))

    def get_tool_confidence(self, tool_name: str) -> float:
        if tool_name not in self.tool_reliability:
            return 0.5 # Unknown
        return self.tool_reliability[tool_name].recent_accuracy

    @property
    def hallucination_rate(self) -> float:
        if self.total_responses == 0: return 0.0
        return self.hallucination_count / self.total_responses

    def get_profile(self) -> Dict[str, Any]:
        """Returns the agent's understanding of its own strengths/weaknesses."""
        strengths = []
        weaknesses = []
        
        for k, v in self.metrics.items():
            if v.total_attempts > 5:
                if v.recent_accuracy > 0.8: strengths.append(k)
                elif v.recent_accuracy < 0.5: weaknesses.append(k)
                
        return {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "hallucination_rate": f"{self.hallucination_rate*100:.1f}%",
            "overall_tool_accuracy": f"{self.metrics['tool_execution'].recent_accuracy*100:.1f}%",
            "prediction_accuracy": f"{self.metrics['prediction'].recent_accuracy*100:.1f}%"
        }
