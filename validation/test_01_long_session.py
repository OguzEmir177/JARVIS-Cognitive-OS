import sys
import os
import asyncio
import time
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.engine import ExecutionEngine
from core.config import EngineConfig

class DummyIO:
    def __init__(self):
        self.text_mode = True
        self.shutdown_requested = False
    
    def set_gui_callback(self, *args, **kwargs): pass
    def update_gui(self, *args, **kwargs): pass
    async def get_input(self):
        await asyncio.sleep(1)
        return ""
    async def speak(self, text): pass
    def request_shutdown(self):
        self.shutdown_requested = True

def run_long_session_test(duration_minutes=2):
    """
    Runs the engine in headless mode for a given duration.
    Measures memory and event queue growth.
    """
    
    async def _runner():
        config = EngineConfig()
        config.brain_connect_retries = 1 # Fast fail for test
        engine = ExecutionEngine(config)
        
        # Mock IOBridge to run headlessly
        engine.io_bridge = DummyIO()
        
        await engine.initialize()
        
        # We start it as a task so we can monitor
        engine_task = asyncio.create_task(engine.start())
        
        start_time = time.time()
        target_duration = duration_minutes * 60
        
        metrics = {
            "initial_nodes": len(engine.cognitive_core.perception.environment_graph.nodes) if engine.cognitive_core else 0,
            "max_queue_size": 0
        }
        
        while (time.time() - start_time) < target_duration:
            await asyncio.sleep(5)
            if engine.cognitive_core:
                qsize = engine.cognitive_core.event_bus._queue.qsize() if hasattr(engine.cognitive_core.event_bus, '_queue') else 0
                metrics["max_queue_size"] = max(metrics["max_queue_size"], qsize)
                
        # Shutdown
        engine._running = False
        await engine.shutdown()
        
        if engine.cognitive_core:
            metrics["final_nodes"] = len(engine.cognitive_core.perception.environment_graph.nodes)
            
        return metrics

    # Run the asyncio event loop
    return asyncio.run(_runner())

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=1, help="Duration to run the test in minutes")
    args = parser.add_argument() if not hasattr(parser, "parse_args") else parser.parse_args()
    
    framework = ValidationFramework()
    framework.measure(f"Long Session Stability ({args.minutes}m)", run_long_session_test, args.minutes)
    framework.generate_report()
