"""[V9.2] ScheduleTool Test Suite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dynamic scheduling tool (ScheduleTool) tests.

Test Scenarios:
    1. Valid "minute|message" format → scheduler.add_daily is called
    2. Pipe character is missing → success=False
    3. Negative/zero minutes → success=False
    4. Empty message → success=False
    5. There is no scheduler in the context → success=False
    6. Smart alias resolution (REMINDER → SCHEDULE)
    7. Registry integration — SCHEDULE tag is registered
    8. Non-numeric minute → success=False"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from tools.system_tool import ScheduleTool
from tools.base_tool import ToolResult


class TestScheduleToolValidInput:
    """Valid login scenarios."""

    @pytest.mark.asyncio
    async def test_valid_schedule_calls_add_daily(self):
        """'5|take a break' → scheduler.add_daily() should be called."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "5|mola ver"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is True
        assert "5 dakika sonra" in result.speak
        mock_scheduler.add_daily.assert_called_once()

        # validate add_daily arguments
        call_args = mock_scheduler.add_daily.call_args
        hour, minute, action = call_args[0]
        assert isinstance(hour, int)
        assert isinstance(minute, int)
        assert "[PROTOCOL: SPEAK] mola ver" == action

    @pytest.mark.asyncio
    async def test_valid_schedule_target_time(self):
        """Target hour:minutes must be calculated correctly."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        before = datetime.now()
        result = await tool.execute(
            {"reminder": "drink 10|water"},
            engine_context={"scheduler": mock_scheduler},
        )
        after = datetime.now()

        call_args = mock_scheduler.add_daily.call_args[0]
        target_hour, target_minute = call_args[0], call_args[1]

        # Target time should be around "now + 10min"
        expected_low = before + timedelta(minutes=10)
        expected_high = after + timedelta(minutes=10)

        # Hour:minute interval control (including border crossings)
        assert expected_low.hour <= target_hour <= expected_high.hour or \
               (expected_low.hour == 23 and target_hour == 0)  # midnight pass

    @pytest.mark.asyncio
    async def test_large_minute_value(self):
        """Large minute value (120 min) should be accepted."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "120|meeting"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is True
        mock_scheduler.add_daily.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_with_turkish_chars(self):
        """The message containing Turkish characters must be moved correctly."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "15|get ready for the tea break"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is True
        action = mock_scheduler.add_daily.call_args[0][2]
        assert "get ready for tea break" in action


class TestScheduleToolInvalidInput:
    """Invalid login scenarios."""

    @pytest.mark.asyncio
    async def test_missing_pipe(self):
        """Input without pipe character → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "remind me in 5 minutes"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False
        mock_scheduler.add_daily.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_minutes(self):
        """0 dakika → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "0|test"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_negative_minutes(self):
        """Negatif dakika → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "-5|test"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_non_numeric_minutes(self):
        """Non-numeric minute → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "five|test"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_empty_message(self):
        """Empty message → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "5|"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_empty_params(self):
        """Empty parameter → success=False."""
        tool = ScheduleTool()

        result = await tool.execute({}, engine_context={"scheduler": MagicMock()})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_whitespace_only_message(self):
        """Just blank message → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "5|   "},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False


class TestScheduleToolContext:
    """engine_context access scenarios."""

    @pytest.mark.asyncio
    async def test_no_scheduler_in_context(self):
        """Context'te scheduler yoksa → success=False."""
        tool = ScheduleTool()

        result = await tool.execute(
            {"reminder": "5|test"},
            engine_context={},
        )

        assert result.success is False
        assert "Scheduler not found" in result.message

    @pytest.mark.asyncio
    async def test_none_context(self):
        """engine_context=None → success=False."""
        tool = ScheduleTool()

        result = await tool.execute(
            {"reminder": "5|test"},
            engine_context=None,
        )

        assert result.success is False


class TestScheduleToolMetadata:
    """Tool metadata verification."""

    def test_protocol_tag(self):
        tool = ScheduleTool()
        assert tool.protocol_tag == "SCHEDULE"

    def test_domain(self):
        tool = ScheduleTool()
        assert tool.domain == "system"

    def test_parameters(self):
        tool = ScheduleTool()
        assert "reminder" in tool.parameters

    def test_to_schema(self):
        tool = ScheduleTool()
        schema = tool.to_schema()
        assert schema["protocol_tag"] == "SCHEDULE"
        assert schema["domain"] == "system"


class TestScheduleToolRegistry:
    """Registry entegrasyon testleri."""

    def test_schedule_registered_in_default_registry(self):
        """SCHEDULE tag must be in the default registry."""
        from tools.tool_registry import create_default_registry
        registry = create_default_registry()
        assert "SCHEDULE" in registry.all_tags

    def test_smart_alias_reminder(self):
        """Must resolve to REMINDER alias → SCHEDULE."""
        from tools.tool_registry import create_default_registry, SMART_ALIASES
        assert SMART_ALIASES.get("REMINDER") == "SCHEDULE"

        registry = create_default_registry()
        tool = registry.get_by_protocol("REMINDER")
        assert tool is not None
        assert tool.protocol_tag == "SCHEDULE"

    def test_smart_alias_set_timer(self):
        """SET_TIMER alias → SCHEDULE."""
        from tools.tool_registry import SMART_ALIASES
        assert SMART_ALIASES.get("SET_TIMER") == "SCHEDULE"

    def test_iron_dome_passes_schedule(self):
        """Iron Dome no longer blocks SCHEDULE."""
        from tools.tool_registry import create_default_registry
        registry = create_default_registry()
        assert registry.is_registered("SCHEDULE") is True


class TestScheduleToolBuildContext:
    """PlanExecutor._build_context scheduler enjeksiyonu."""

    def test_context_contains_scheduler(self):
        """_build_context must include the scheduler (if set)."""
        from core.plan_executor import PlanExecutor

        pe = PlanExecutor.__new__(PlanExecutor)
        pe.last_whatsapp_num = None
        pe.last_whatsapp_time = 0
        mock_scheduler = MagicMock()
        pe.scheduler = mock_scheduler

        ctx = pe._build_context({})
        assert "scheduler" in ctx
        assert ctx["scheduler"] is mock_scheduler

    def test_context_without_scheduler(self):
        """If the scheduler is not assigned, it should not be in the context."""
        from core.plan_executor import PlanExecutor

        pe = PlanExecutor.__new__(PlanExecutor)
        pe.last_whatsapp_num = None
        pe.last_whatsapp_time = 0
        # scheduler not assigned

        ctx = pe._build_context({})
        assert "scheduler" not in ctx
