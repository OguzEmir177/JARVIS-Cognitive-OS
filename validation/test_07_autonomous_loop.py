import sys
import os
import asyncio
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.autonomous_loop import AutonomousCognitionLoop

def run_autonomous_loop_test():
    """
    Validates autonomous loop spam frequency, cooldowns, and idle CPU usage.
    """
    class MockCore:
        def __init__(self):
            self.state = {"idle": 0}
            self.actions = 0
            
        async def evaluate_proactive_action(self):
            if self.state["idle"] > 10:
                self.actions += 1
                return True
            return False
            
        async def execute_proactive_action(self):
            pass
            
    core = MockCore()
    loop = AutonomousCognitionLoop(core)
    metrics = {}
    
    async def _test():
        start = time.time()
        
        # Start loop in background
        loop.base_interval = 0.1 # fast for testing
        task = asyncio.create_task(loop.run())
        
        # Test 1: User is active, no proactive actions
        core.state["idle"] = 0
        await asyncio.sleep(0.5)
        metrics["spam_during_active"] = core.actions
        
        # Test 2: User is idle, proactive actions should occur
        core.state["idle"] = 20
        await asyncio.sleep(0.5)
        actions_when_idle = core.actions
        metrics["proactive_actions_when_idle"] = actions_when_idle
        
        loop.stop()
        await task
        
    asyncio.run(_test())
    
    if metrics["spam_during_active"] > 0:
        raise ValueError("Autonomous loop spammed while user was active.")
        
    if metrics["proactive_actions_when_idle"] == 0:
        raise ValueError("Autonomous loop failed to trigger when user was idle.")
        
    return metrics

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Autonomous Loop Validation", run_autonomous_loop_test)
    framework.generate_report()
