import asyncio
import pytest
from unittest.mock import AsyncMock

from core.brain import GroqBrain
from core.config import EngineConfig

class MockAsyncGroq:
    def __init__(self, *args, **kwargs):
        # Setup a mock for client.chat.completions.create
        self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": AsyncMock()})()})()

@pytest.mark.asyncio
async def test_check_connection_uses_correct_model(monkeypatch):
    """
    Test that check_connection() dynamically respects the ping_model 
    or self.model rather than using a hardcoded string.
    """
    monkeypatch.setenv("GROQ_API_KEY", "test_key")
    
    # CASE 1: No ping_model defined, should fallback to self.model (brain_models[0])
    config_no_ping = EngineConfig(brain_models=["primary-model"])
    config_no_ping.ping_model = None
    
    brain1 = GroqBrain(config=config_no_ping)
    brain1.client = MockAsyncGroq()
    
    await brain1.check_connection()
    call_args1 = brain1.client.chat.completions.create.call_args[1]
    assert call_args1["model"] == "primary-model", f"Expected primary-model, got {call_args1['model']}"

    # CASE 2: ping_model defined, should use it
    config_with_ping = EngineConfig(brain_models=["primary-model"])
    config_with_ping.ping_model = "test-ping-model"
    
    brain2 = GroqBrain(config=config_with_ping)
    brain2.client = MockAsyncGroq()
    
    await brain2.check_connection()
    call_args2 = brain2.client.chat.completions.create.call_args[1]
    assert call_args2["model"] == "test-ping-model", f"Expected test-ping-model, got {call_args2['model']}"
