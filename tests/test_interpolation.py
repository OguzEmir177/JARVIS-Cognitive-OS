import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from core.executor import Executor
from tools.base_tool import ToolResult

@pytest.mark.asyncio
async def test_interpolation_logic():
    # Setup
    mock_brain = MagicMock()
    executor = Executor(brain=mock_brain)
    
    # Mock context containing results from previous steps
    context = {
        "step_results": {
            "GOOGLE_SEARCH": "Python is a programming language.",
            "APP_OPEN": "WhatsApp is open."
        }
    }
    
    # 1. Test case: Full replacement
    arg1 = "Search result is: [PROTOCOL: GOOGLE_SEARCH]"
    interpolated1 = executor._interpolate_argument(arg1, context)
    assert interpolated1 == "Search result is: Python is a programming language."
    
    # 2. Test case: Multiple replacements
    arg2 = "From [PROTOCOL: GOOGLE_SEARCH] to [PROTOCOL: APP_OPEN]"
    interpolated2 = executor._interpolate_argument(arg2, context)
    assert interpolated2 == "From Python is a programming language. to WhatsApp is open."
    
    # 3. Test case: Unknown tag (should remain untouched)
    arg3 = "Result: [PROTOCOL: UNKNOWN_TOOL]"
    interpolated3 = executor._interpolate_argument(arg3, context)
    assert interpolated3 == "Result: [PROTOCOL: UNKNOWN_TOOL]"
    
    # 4. Test case: Empty or None context
    assert executor._interpolate_argument(arg1, {}) == arg1
    assert executor._interpolate_argument(arg1, None) == arg1

@pytest.mark.asyncio
async def test_integration_through_execute_tool():
    # Setup
    mock_brain = MagicMock()
    executor = Executor(brain=mock_brain)
    
    # Register a dummy tool that just echoes its argument
    mock_tool = MagicMock()
    mock_tool.protocol_tag = "ECHO_TOOL"
    mock_tool.name = "echo"
    mock_tool.parameters = {"text": {"type": "string"}}
    mock_tool.execute = AsyncMock(side_effect=lambda p, c: ToolResult(success=True, message=p["text"]))
    
    executor.registry.register(mock_tool)
    
    context = {
        "step_results": {
            "PREV_STEP": "Decoded Context"
        }
    }
    
    # Run execute_tool with a placeholder
    result = await executor.execute_tool(
        protocol_tag="ECHO_TOOL",
        argument="Pass: [PROTOCOL: PREV_STEP]",
        engine_context=context
    )
    
    assert result.success
    assert result.message == "Pass: Decoded Context"
