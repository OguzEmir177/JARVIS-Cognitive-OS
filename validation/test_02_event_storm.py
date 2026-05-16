import sys
import os
import asyncio
import time
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.event_bus import EventBus
from core.world_state import EnvironmentGraph

def run_event_storm_test():
    """
    Simulates rapid asynchronous events targeting the event bus and graph.
    Measures race conditions and deadlocks.
    """
    
    async def _storm():
        bus = EventBus()
        graph = EnvironmentGraph(event_bus=bus)
        
        metrics = {
            "events_emitted": 0,
            "events_processed": 0,
            "errors": 0
        }
        
        # Subscribe a dummy handler
        async def dummy_handler(event):
            metrics["events_processed"] += 1
            await asyncio.sleep(0.001)
            
        bus.subscribe("WINDOW_CHANGED", dummy_handler)
        bus.subscribe("OCR_UPDATED", dummy_handler)
        
        async def emit_windows(count):
            for i in range(count):
                try:
                    await graph.update_state({
                        "active_window": f"Window_{i % 50} - App_{i % 10}"
                    })
                    metrics["events_emitted"] += 1
                except Exception as e:
                    metrics["errors"] += 1
                    
        async def emit_ocr(count):
            for i in range(count):
                try:
                    ui_entities = [{"label": f"btn_{j}", "type": "button"} for j in range(5)]
                    await graph.update_state({
                        "visual_entities": ui_entities
                    })
                    metrics["events_emitted"] += 1
                except Exception as e:
                    metrics["errors"] += 1
                    
        # Run storm
        start = time.time()
        tasks = [
            asyncio.create_task(emit_windows(500)),
            asyncio.create_task(emit_windows(500)),
            asyncio.create_task(emit_ocr(500)),
            asyncio.create_task(emit_ocr(500))
        ]
        
        await asyncio.gather(*tasks)
        
        # Wait for queue to drain
        await asyncio.sleep(1)
        
        metrics["duration"] = time.time() - start
        metrics["final_graph_nodes"] = len(graph.nodes)
        
        if metrics["errors"] > 0:
            raise RuntimeError(f"Event storm caused {metrics['errors']} errors.")
            
        return metrics

    return asyncio.run(_storm())

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Event Storm Validation", run_event_storm_test)
    framework.generate_report()
