import os
import threading
import asyncio
import pytest
from unittest.mock import AsyncMock

from core.brain import GroqBrain

class DummyConfig:
    brain_models = ["dummy-model"]
    max_tokens = 100
    temperature = 0.5

@pytest.mark.asyncio
async def test_brain_lock_thread_safety(monkeypatch):
    """
    Test that GroqBrain does NOT initialize asyncio.Lock in its __init__,
    allowing it to be safely created from a separate thread (like Tkinter GUI)
    where there is no running event loop.
    """
    # Mock environment variable for __init__
    monkeypatch.setenv("GROQ_API_KEY", "test_key")
    
    brain_instance = None
    init_exception = None

    def thread_process():
        nonlocal brain_instance, init_exception
        try:
            # Ensure there is no event loop in this thread
            try:
                asyncio.get_running_loop()
                pytest.fail("A running event loop should not exist in this thread!")
            except RuntimeError:
                pass # Normal

            brain_instance = GroqBrain(config=DummyConfig())
        except Exception as e:
            init_exception = e

    t = threading.Thread(target=thread_process)
    t.start()
    t.join()

    # Verify no errors happened during init in the thread
    assert init_exception is None, f"Initialization failed with: {init_exception}"
    assert brain_instance is not None
    assert brain_instance._lock is None

    # Now simulate calling think() from the main async loop
    # Mocking completion create return object
    brain_instance.client = AsyncMock()
    mock_choice = type("Choice", (), {"message": type("Message", (), {"content": "test_reply"})()})()
    brain_instance.client.chat.completions.create.return_value.choices = [mock_choice]
    
    # We also need to mock memory_manager retrieved contexts since it involves run_in_executor
    brain_instance.memory_manager = AsyncMock()
    brain_instance.memory_manager.retrieve_context.return_value = ""

    reply = await brain_instance.think("test input")
    
    assert reply == "test_reply"
    # Ensure lock was lazily initialized within think
    assert brain_instance._lock is not None
    assert isinstance(brain_instance._lock, asyncio.Lock)
