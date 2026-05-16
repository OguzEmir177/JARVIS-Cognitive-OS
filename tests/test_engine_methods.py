import pytest
import pytest_asyncio
import asyncio
from unittest.mock import MagicMock, AsyncMock

from core.engine import ExecutionEngine
from core.config import EngineConfig
from core.state_manager import TaskState
from tools.base_tool import ToolResult

@pytest_asyncio.fixture
def base_engine():
    brain = MagicMock()
    brain.think = AsyncMock()
    brain.check_connection = AsyncMock(return_value=True)
    brain.client = MagicMock()
    
    eng = ExecutionEngine(config=EngineConfig())
    eng.brain = brain
    eng.state_manager = MagicMock()
    
    # [V8.1] Manual dependency injection for test
    from core.plan_executor import PlanExecutor
    bridge = MagicMock()
    bridge.speak = AsyncMock()
    eng.plan_executor = PlanExecutor(
        brain=eng.brain,
        memory=MagicMock(),
        executor=MagicMock(),
        state_manager=eng.state_manager,
        io_bridge=bridge,
        config=eng.config
    )
    
    task_state = TaskState(id="1", goal="test")
    eng.state_manager.create_task.return_value = task_state
    
    return eng

@pytest.mark.asyncio
async def test_engine_single_protocol_execution(base_engine):
    task_state = TaskState(id="1", goal="test")
    # [V8.1] Moved to plan_executor
    await base_engine.plan_executor.execute_single(task_state, "[PROTOCOL: GOOGLE_SEARCH] args")
    base_engine.plan_executor.executor.execute_tool.assert_called_once()
    
@pytest.mark.asyncio
async def test_engine_next_action_routing(base_engine):
    # Test handle_next_action
    result = ToolResult(success=True, message="mock", next_action="START_DICTATION", data={"recipient": "Babam"})
    
    base_engine.plan_executor._handle_dictation = AsyncMock()
    await base_engine.plan_executor.handle_next_action(result)
    
    base_engine.plan_executor._handle_dictation.assert_called_once()

@pytest.mark.asyncio
async def test_engine_replan_success(base_engine):
    task_state = TaskState(id="1", goal="test")
    plan = MagicMock()
    plan.get_context_summary.return_value = "step 1"
    
    node = MagicMock()
    node.protocol_tag = "TEST"
    
    base_engine.brain.think = AsyncMock(return_value="[PLAN]\n1. SUCCESS test\n[/PLAN]")
    
    # [V8.1] Moved to plan_executor
    new_plan = await base_engine.plan_executor.replan(task_state, plan, node, "error")
    assert new_plan is not None
    assert new_plan.steps[0].protocol_tag == "SUCCESS"

@pytest.mark.asyncio
async def test_engine_detect_plan_fallback(base_engine):
    # [V8.1] Moved to plan_executor
    plan = await base_engine.plan_executor.detect_and_parse_plan("[PLAN] 1. TEST t [/PLAN]", "t")
    assert plan is not None
    assert plan.steps[0].protocol_tag == "TEST"

@pytest.mark.asyncio
async def test_handle_stress_test(base_engine):
    base_engine.brain.think = AsyncMock(return_value="1. test\n2. test2")
    base_engine.brain.think.side_effect = ["1. deneme", "[PROTOCOL: APP_OPEN]"]
    
    result = ToolResult(success=True, message="mock")
    # [V8.1] Moved to plan_executor
    await base_engine.plan_executor._handle_stress_test(result)
    base_engine.plan_executor.io_bridge.speak.assert_called()
