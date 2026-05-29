import pytest
import pytest_asyncio
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from core.engine import ExecutionEngine
from core.config import EngineConfig
from core.planner import PlanNode, ExecutionPlan
from core.state_manager import TaskState
from tools.base_tool import ToolResult
from errors import ToolExecutionError

@pytest.fixture
def mock_brain():
    brain = MagicMock()
    brain.think = AsyncMock()
    brain.check_connection = AsyncMock(return_value=True)
    brain.client = MagicMock()
    brain.client.chat.completions.create = AsyncMock()
    return brain

@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.save_memory_async = AsyncMock()
    memory.save_memory = MagicMock()
    return memory

@pytest.fixture
def mock_executor():
    executor = MagicMock()
    executor.execute_tool = AsyncMock()
    executor.cleanup = AsyncMock()
    executor.registry = MagicMock()
    executor.registry.smart_aliases = {}
    executor.registry.is_registered.return_value = True
    return executor

@pytest_asyncio.fixture
async def engine(mock_brain, mock_memory, mock_executor):
    config = EngineConfig(max_replan_attempts=2, tool_timeout_seconds=2.0)
    eng = ExecutionEngine(config=config)
    
    # [V8.1] Initialize components manually for test (simulating initialize())
    from core.io_bridge import IOBridge
    from core.plan_executor import PlanExecutor
    from core.state_manager import StateManager
    
    eng.brain = mock_brain
    eng.memory = mock_memory
    eng.executor = mock_executor
    eng.state_manager = StateManager()
    
    eng.io_bridge = IOBridge(config=eng.config)
    eng.io_bridge.speak = AsyncMock()
    eng.io_bridge.get_input = AsyncMock(return_value="test input")
    eng.io_bridge.update_gui = MagicMock()
    
    eng.plan_executor = PlanExecutor(
        brain=eng.brain,
        memory=eng.memory,
        executor=eng.executor,
        state_manager=eng.state_manager,
        io_bridge=eng.io_bridge,
        config=eng.config
    )
    
    eng.reflector = MagicMock()
    eng.reflector.reflect = AsyncMock(return_value={"summary": "Mock bug summary"})
    
    yield eng
    await eng.shutdown()

@pytest.mark.asyncio
async def test_e2e_successful_replanning_flow(engine, mock_brain, mock_executor):
    user_input = "python ac discord gir"
    first_response = '```json\n{"hedef": "test", "alt_gorevler": [{"protocol": "GOOGLE_SEARCH", "arg": "python"}, {"protocol": "APP_OPEN", "arg": "discord"}]}\n```'
    replan_response = '```json\n{"hedef": "kurtarma", "alt_gorevler": [{"protocol": "WEB_OPEN", "arg": "discord.com"}]}\n```'
    
    mock_brain.think.side_effect = [first_response, replan_response]
    
    async def mock_execute(protocol_tag, argument, engine_context):
        if protocol_tag == "GOOGLE_SEARCH":
            return ToolResult(success=True, message="Bulundu")
        elif protocol_tag == "APP_OPEN":
            return ToolResult(success=False, message="Discord not found")
        elif protocol_tag == "WEB_OPEN":
            return ToolResult(success=True, message="opened")
        return ToolResult(success=True)

    mock_executor.execute_tool.side_effect = mock_execute
    
    # [V8.1] Public method is process_input
    await engine.process_input(user_input)
    
    assert mock_brain.think.call_count == 2
    assert mock_executor.execute_tool.call_count == 3
    
    tasks = engine.state_manager.get_all_tasks()
    state = tasks[0] if isinstance(tasks, list) else next(iter(tasks.values()))
    # In V8.1, execute_plan handles completion
    assert state.status == "completed"

@pytest.mark.asyncio
async def test_e2e_graceful_fallback_timeout(engine, mock_brain, mock_executor):
    mock_brain.think.return_value = "[PLAN]\n1. GOOGLE_SEARCH test\n[/PLAN]"
    
    async def mock_timeout_execute(protocol_tag, argument, engine_context):
        await asyncio.sleep(0.1) # Small sleep for test
        return ToolResult(success=False, message="Timeout")
    
    mock_executor.execute_tool.side_effect = mock_timeout_execute
    await engine.process_input("Hadi test")
    
    tasks = engine.state_manager.get_all_tasks()
    state = tasks[0] if isinstance(tasks, list) and tasks else next(iter(tasks.values()), None)
    assert state is not None
    assert state.status == "failed"

@pytest.mark.asyncio
async def test_e2e_graceful_fallback_garbage_llm(engine, mock_brain):
    mock_brain.think.return_value = "A meaningless text"
    await engine.process_input("test")
    engine.io_bridge.speak.assert_called_with("A meaningless text")

@pytest.mark.asyncio
async def test_vision_condition_node(engine, mock_brain, mock_executor):
    response = "[PLAN]\n1. VISION_INTERPRET Check display status\n[/PLAN]"
    mock_brain.think.return_value = response
    
    mock_executor.execute_tool.return_value = ToolResult(
        success=True, 
        message="Ekran okundu.",
        next_action="VISION_INTERPRET"
    )
    
    # [V8.1] Handler is on plan_executor
    with patch.object(engine.plan_executor, '_handle_vision_interpret', new_callable=AsyncMock) as mocked_handler:
        await engine.process_input("vision_test")
        mocked_handler.assert_called_once()

@pytest.mark.asyncio
async def test_engine_shutdown(engine):
    await engine.shutdown()
    assert not engine._running
    engine.executor.cleanup.assert_called_once()
