import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from core.executor import Executor
from tools.base_tool import BaseTool, ToolResult
from errors import ToolExecutionError

class MockTool(BaseTool):
    name = "MockTool"
    protocol_tag = "MOCK_TOOL"
    domain = "test"
    parameters = {"arg": "string"}
    
    def __init__(self, success=True, exception=False, duration=0, returns_none=False):
        self._success = success
        self._exception = exception
        self._duration = duration
        self._returns_none = returns_none

    async def execute(self, params, context):
        if self._duration > 0:
            await asyncio.sleep(self._duration)
        if self._exception:
            raise Exception("Mock error")
        if self._returns_none:
            return None
        return ToolResult(success=self._success, message="Mock result")

@pytest.fixture
def base_executor():
    brain = MagicMock()
    executor = Executor(brain=brain)
    executor.registry = MagicMock()
    return executor

@pytest.mark.asyncio
async def test_execute_tool_success(base_executor):
    tool = MockTool(success=True)
    base_executor.registry.get_by_protocol.return_value = tool
    
    result = await base_executor.execute_tool("MOCK_TOOL", "test_arg")
    assert result.success is True
    assert result.message == "Mock result"
    
@pytest.mark.asyncio
async def test_execute_tool_unknown(base_executor):
    base_executor.registry.get_by_protocol.return_value = None
    
    with pytest.raises(ToolExecutionError) as exc:
        await base_executor.execute_tool("UNKNOWN_TOOL")
    assert "Bilinmeyen protokol" in exc.value.message

@pytest.mark.asyncio
async def test_execute_tool_exception(base_executor):
    tool = MockTool(exception=True)
    base_executor.registry.get_by_protocol.return_value = tool
    
    with pytest.raises(ToolExecutionError) as exc:
        await base_executor.execute_tool("MOCK_TOOL")
    assert "çalıştırılırken hata" in exc.value.message

@pytest.mark.asyncio
async def test_execute_tool_returns_none(base_executor):
    tool = MockTool(returns_none=True)
    base_executor.registry.get_by_protocol.return_value = tool
    
    result = await base_executor.execute_tool("MOCK_TOOL")
    assert result.success is False
    assert "None döndürdü" in result.message

@pytest.mark.asyncio
async def test_try_fallback_success(base_executor):
    tool = MockTool(success=True)
    base_executor.registry.get_fallback_chain.return_value = [tool]
    base_executor.registry.get_by_protocol.return_value = tool
    
    result = await base_executor.try_fallback("FAILING_TOOL")
    assert result is not None
    assert result.success is True

@pytest.mark.asyncio
async def test_try_fallback_fails(base_executor):
    tool = MockTool(success=False)
    base_executor.registry.get_fallback_chain.return_value = [tool]
    base_executor.registry.get_by_protocol.return_value = tool
    
    result = await base_executor.try_fallback("FAILING_TOOL")
    assert result is None

@pytest.mark.asyncio
async def test_try_fallback_exception(base_executor):
    tool = MockTool(exception=True)
    base_executor.registry.get_fallback_chain.return_value = [tool]
    base_executor.registry.get_by_protocol.return_value = tool
    
    result = await base_executor.try_fallback("FAILING_TOOL")
    assert result is None

@pytest.mark.asyncio
async def test_metadata_query(base_executor):
    tool = MockTool()
    base_executor.registry.get_by_protocol.return_value = tool
    
    meta = base_executor.get_tool_metadata("MOCK_TOOL")
    assert meta["domain"] == "test"
    assert "latency_ms" in meta
    
    best = base_executor.get_best_tool_for_domain("test")
    assert base_executor.registry.get_best_tool.called
