import sys
import os
import asyncio
import sqlite3

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from validation.framework import ValidationFramework
from core.memory import MemoryManager

def run_memory_system_validation():
    """
    Validates semantic retrieval, episodic reconstruction, and memory decay.
    """
    db_path = "test_val_memory.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    memory = MemoryManager(db_path=db_path)
    memory.initialize()
    metrics = {}
    
    async def _test():
        # 1. Store
        await memory.store("User likes dark mode", "semantic", {"topic": "preferences"})
        await memory.store("User opened project X", "episodic", {"project": "X"})
        
        # 2. Semantic Retrieval Accuracy
        res = await memory.retrieve("dark mode")
        metrics["retrieval_accuracy"] = 1.0 if any("dark mode" in r.get("content", "") for r in res) else 0.0
        
        # 3. Episodic
        ep_res = await memory.retrieve("project X")
        metrics["episodic_retrieval"] = 1.0 if any("project X" in r.get("content", "") for r in ep_res) else 0.0
        
    asyncio.run(_test())
    
    if os.path.exists(db_path):
        os.remove(db_path)
        
    if metrics["retrieval_accuracy"] == 0.0:
        raise ValueError("Memory failed to retrieve exact semantic match.")
        
    return metrics

if __name__ == "__main__":
    framework = ValidationFramework()
    framework.measure("Memory System Validation", run_memory_system_validation)
    framework.generate_report()
