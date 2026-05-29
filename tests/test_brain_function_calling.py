import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from core.brain import GroqBrain
from core.config import EngineConfig
from tools.base_tool import BaseTool
from tools.tool_registry import ToolRegistry

class DummyWhatsAppTool(BaseTool):
    name = "whatsapp_message"
    description = "Sends messages via WhatsApp."
    protocol_tag = "WHATSAPP_MESSAGE"
    parameters = {
        "kisi": {"type": "string", "description": "Buyer"},
        "mesaj": {"type": "string", "description": "Mesaj"},
        "target": {"type": "string", "description": "Recipient|Message or Recipient only (optional fallback)"}
    }
    domain = "system"
    async def execute(self, params, engine_context=None):
        pass

class DummySearchTool(BaseTool):
    name = "google_search"
    description = "searches on Google"
    protocol_tag = "GOOGLE_SEARCH"
    parameters = {"query": {"type": "string", "description": "Aranacak terim"}}
    domain = "web"
    async def execute(self, params, engine_context=None):
        pass

@pytest.fixture
def mock_brain():
    config = EngineConfig(function_calling_enabled=True)
    registry = ToolRegistry()
    registry.register(DummyWhatsAppTool())
    registry.register(DummySearchTool())
    
    with patch("core.brain.AsyncGroq") as mock_groq:
        brain = GroqBrain(config, tool_registry=registry)
        return brain

@pytest.mark.asyncio
async def test_function_calling_whatsapp_args(mock_brain):
    # Mocking choice response for function call
    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "WHATSAPP_MESSAGE"
    mock_tool_call.function.arguments = '{"kisi": "Ablam", "mesaj": "Nasılsın?"}'
    mock_choice.message.tool_calls = [mock_tool_call]
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    mock_brain.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    result = await mock_brain.think("Tell my sister how are you")
    assert result == "[PROTOCOL: WHATSAPP_MESSAGE] My sister|How are you?"

@pytest.mark.asyncio
async def test_function_calling_search_args(mock_brain):
    # Mocking choice response for function call
    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "GOOGLE_SEARCH"
    mock_tool_call.function.arguments = '{"query": "En iyi yemek tarifleri"}'
    mock_choice.message.tool_calls = [mock_tool_call]
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    mock_brain.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    result = await mock_brain.think("Search for recipes")
    assert result == "[PROTOCOL: GOOGLE_SEARCH] The best recipes"

@pytest.mark.asyncio
async def test_fallback_to_text(mock_brain):
    # Mocking choice response for plan block (no tool calls)
    mock_choice = MagicMock()
    mock_choice.message.tool_calls = None
    mock_choice.message.content = "[PLAN]\n1. [PROTOCOL: GOOGLE_SEARCH] Python\n[/PLAN]"
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    mock_brain.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    result = await mock_brain.think("Study Python and do research")
    assert "[PLAN]" in result
    assert "GOOGLE_SEARCH" in result
