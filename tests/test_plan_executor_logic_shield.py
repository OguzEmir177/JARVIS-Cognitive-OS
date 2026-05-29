import pytest
from unittest.mock import MagicMock, AsyncMock
from core.plan_executor import PlanExecutor
from core.planner import ExecutionPlan, PlanNode

@pytest.fixture
def plan_executor():
    return PlanExecutor(
        brain=MagicMock(),
        memory=MagicMock(),
        executor=MagicMock(),
        state_manager=MagicMock(),
        io_bridge=MagicMock(),
        config=MagicMock()
    )

@pytest.mark.asyncio
async def test_logic_shield_vision_before_search(plan_executor):
    """Scenario 1: If VISION comes BEFORE SEARCH (legitimate scenario).
    The user wants to look at the screen, take notes, research and send.
    VISION should not be skipped."""
    plan_executor.execute_node = AsyncMock(return_value=True)
    task_state = MagicMock()
    task_state.is_active.return_value = True
    
    plan = ExecutionPlan(
        original_request="Test task",
        steps=[
            PlanNode(step_number=1, protocol_tag="VISION", argument="Test vision"),
            PlanNode(step_number=2, protocol_tag="GOOGLE_SEARCH", argument="Test search"),
            PlanNode(step_number=3, protocol_tag="WHATSAPP_MESSAGE", argument="Test message")
        ]
    )
    
    await plan_executor.execute_plan(task_state, plan)
    
    assert plan_executor.execute_node.call_count == 3
    called_tags = [call.args[1].protocol_tag for call in plan_executor.execute_node.call_args_list]
    assert called_tags == ["VISION", "GOOGLE_SEARCH", "WHATSAPP_MESSAGE"]

@pytest.mark.asyncio
async def test_logic_shield_vision_after_search(plan_executor):
    """Scenario 2: If VISION comes AFTER SEARCH (redundant scenario).
    Research has been done, VISION has been added unnecessarily.
    The old behavior should be kept and VISION should be skipped."""
    plan_executor.execute_node = AsyncMock(return_value=True)
    task_state = MagicMock()
    task_state.is_active.return_value = True
    
    plan = ExecutionPlan(
        original_request="Test task",
        steps=[
            PlanNode(step_number=1, protocol_tag="GOOGLE_SEARCH", argument="Test search"),
            PlanNode(step_number=2, protocol_tag="VISION", argument="Test vision"),
            PlanNode(step_number=3, protocol_tag="WHATSAPP_MESSAGE", argument="Test message")
        ]
    )
    
    await plan_executor.execute_plan(task_state, plan)
    
    assert plan_executor.execute_node.call_count == 2
    called_tags = [call.args[1].protocol_tag for call in plan_executor.execute_node.call_args_list]
    assert called_tags == ["GOOGLE_SEARCH", "WHATSAPP_MESSAGE"]

@pytest.mark.asyncio
async def test_logic_shield_no_whatsapp(plan_executor):
    """Scenario 3: If there is no WHATSAPP, VISION should not be skipped.
    Even if research has been done, if there is no WhatsApp message, VISION is legitimate."""
    plan_executor.execute_node = AsyncMock(return_value=True)
    task_state = MagicMock()
    task_state.is_active.return_value = True
    
    plan = ExecutionPlan(
        original_request="Test task",
        steps=[
            PlanNode(step_number=1, protocol_tag="GOOGLE_SEARCH", argument="Test search"),
            PlanNode(step_number=2, protocol_tag="VISION", argument="Test vision")
        ]
    )
    
    await plan_executor.execute_plan(task_state, plan)
    
    assert plan_executor.execute_node.call_count == 2
    called_tags = [call.args[1].protocol_tag for call in plan_executor.execute_node.call_args_list]
    assert called_tags == ["GOOGLE_SEARCH", "VISION"]
