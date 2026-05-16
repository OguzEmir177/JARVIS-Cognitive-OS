import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.reflection import ReflectionEngine
from core.state_manager import TaskState

def run_reflection_validation():
    """
    Validates Reflection engine hallucination detection and replanning.
    """
    # Simple mock objects for test
    class MockBrain:
        async def evaluate_task(self, text):
            # Mock LLM evaluation
            if "hallucination" in text.lower():
                return {"hallucination": True, "success": False, "critique": "Failed due to fake data"}
            return {"hallucination": False, "success": True, "critique": "All good"}
            
    class MockMemory:
        async def store_reflection(self, *args, **kwargs): pass
        
    engine = ReflectionEngine(memory=MockMemory(), brain=MockBrain())
    metrics = {}
    
    # 1. Hallucination Detection
    task1 = TaskState(task_id="t1", goal="Check weather")
    task1.tool_history = ["get_weather"]
    task1.result = "I found hallucination in the data."
    task1.status = "completed"
    
    # Mocking async run
    async def _test():
        res1 = await engine.reflect(task1)
        metrics["detected_hallucination"] = res1.get("hallucination", False)
        
        # 2. Workflow Consistency
        task2 = TaskState(task_id="t2", goal="Open Spotify")
        task2.tool_history = ["open_app"]
        task2.result = "Spotify opened successfully."
        task2.status = "completed"
        
        res2 = await engine.reflect(task2)
        metrics["false_reflection_rate"] = 1.0 if res2.get("hallucination", False) else 0.0
        
    asyncio.run(_test())
    
    if not metrics.get("detected_hallucination"):
        raise ValueError("Reflection failed to catch obvious hallucination.")
        
    if metrics.get("false_reflection_rate", 1.0) > 0.0:
        raise ValueError("Reflection engine triggered false positive on valid result.")
        
    return metrics

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Reflection Engine Validation", run_reflection_validation)
    framework.generate_report()
