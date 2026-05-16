import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.recovery import RecoverySystem

def run_recovery_system_validation():
    """
    Validates automatic recovery, fallback routing, and retry logic.
    """
    class MockEngine:
        async def evaluate_recovery(self, *args, **kwargs):
            return "retry"
            
    system = RecoverySystem(brain=MockEngine(), memory=None)
    metrics = {}
    
    async def _test():
        # 1. Tool crash
        strategy = await system.handle_failure("task1", "FileNotFoundError: no such file", {"goal": "read file"})
        metrics["tool_crash_strategy"] = strategy
        
        # 2. Timeout failure
        timeout_strategy = await system.handle_failure("task2", "TimeoutError: connection lost", {"goal": "fetch data"})
        metrics["timeout_strategy"] = timeout_strategy
        
        # 3. Validation
        if not strategy:
            raise ValueError("Recovery system failed to propose a strategy.")
            
    asyncio.run(_test())
    return metrics

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Recovery System Validation", run_recovery_system_validation)
    framework.generate_report()
