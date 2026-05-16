"""
[V9.2] ScheduleTool Test Suite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dinamik zamanlama aracı (ScheduleTool) testleri.

Test Senaryoları:
    1. Geçerli "dakika|mesaj" formatı → scheduler.add_daily çağrılır
    2. Pipe karakteri eksik → success=False
    3. Negatif/sıfır dakika → success=False
    4. Boş mesaj → success=False
    5. Context'te scheduler yok → success=False
    6. Smart alias çözümleme (REMINDER → SCHEDULE)
    7. Registry entegrasyon — SCHEDULE tag kayıtlı
    8. Sayısal olmayan dakika → success=False
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from tools.system_tool import ScheduleTool
from tools.base_tool import ToolResult


class TestScheduleToolValidInput:
    """Geçerli giriş senaryoları."""

    @pytest.mark.asyncio
    async def test_valid_schedule_calls_add_daily(self):
        """'5|mola ver' → scheduler.add_daily() çağrılmalı."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "5|mola ver"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is True
        assert "5 dakika sonra" in result.speak
        mock_scheduler.add_daily.assert_called_once()

        # add_daily argümanlarını doğrula
        call_args = mock_scheduler.add_daily.call_args
        hour, minute, action = call_args[0]
        assert isinstance(hour, int)
        assert isinstance(minute, int)
        assert "[PROTOCOL: SPEAK] mola ver" == action

    @pytest.mark.asyncio
    async def test_valid_schedule_target_time(self):
        """Hedef saat:dakika doğru hesaplanmalı."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        before = datetime.now()
        result = await tool.execute(
            {"reminder": "10|su iç"},
            engine_context={"scheduler": mock_scheduler},
        )
        after = datetime.now()

        call_args = mock_scheduler.add_daily.call_args[0]
        target_hour, target_minute = call_args[0], call_args[1]

        # Hedef zaman, "şu an + 10dk" civarında olmalı
        expected_low = before + timedelta(minutes=10)
        expected_high = after + timedelta(minutes=10)

        # Saat:dakika aralık kontrolü (sınır geçişleri dahil)
        assert expected_low.hour <= target_hour <= expected_high.hour or \
               (expected_low.hour == 23 and target_hour == 0)  # gece yarısı geçişi

    @pytest.mark.asyncio
    async def test_large_minute_value(self):
        """Büyük dakika değeri (120 dk) kabul edilmeli."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "120|toplantı"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is True
        mock_scheduler.add_daily.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_with_turkish_chars(self):
        """Türkçe karakter içeren mesaj doğru taşınmalı."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "15|çay molası için hazırlan"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is True
        action = mock_scheduler.add_daily.call_args[0][2]
        assert "çay molası için hazırlan" in action


class TestScheduleToolInvalidInput:
    """Geçersiz giriş senaryoları."""

    @pytest.mark.asyncio
    async def test_missing_pipe(self):
        """Pipe karakteri olmayan giriş → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "5 dakika sonra hatırlat"},
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
        """Sayısal olmayan dakika → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "beş|test"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_empty_message(self):
        """Boş mesaj → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "5|"},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_empty_params(self):
        """Boş parametre → success=False."""
        tool = ScheduleTool()

        result = await tool.execute({}, engine_context={"scheduler": MagicMock()})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_whitespace_only_message(self):
        """Sadece boşluk mesajı → success=False."""
        tool = ScheduleTool()
        mock_scheduler = MagicMock()

        result = await tool.execute(
            {"reminder": "5|   "},
            engine_context={"scheduler": mock_scheduler},
        )

        assert result.success is False


class TestScheduleToolContext:
    """engine_context erişim senaryoları."""

    @pytest.mark.asyncio
    async def test_no_scheduler_in_context(self):
        """Context'te scheduler yoksa → success=False."""
        tool = ScheduleTool()

        result = await tool.execute(
            {"reminder": "5|test"},
            engine_context={},
        )

        assert result.success is False
        assert "Scheduler bulunamadı" in result.message

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
    """Tool metadata doğrulama."""

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
        """SCHEDULE tag'i default registry'de olmalı."""
        from tools.tool_registry import create_default_registry
        registry = create_default_registry()
        assert "SCHEDULE" in registry.all_tags

    def test_smart_alias_reminder(self):
        """REMINDER alias → SCHEDULE'a çözümlenmeli."""
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
        """Iron Dome SCHEDULE'ı artık engellemez."""
        from tools.tool_registry import create_default_registry
        registry = create_default_registry()
        assert registry.is_registered("SCHEDULE") is True


class TestScheduleToolBuildContext:
    """PlanExecutor._build_context scheduler enjeksiyonu."""

    def test_context_contains_scheduler(self):
        """_build_context scheduler'ı içermeli (set edilmişse)."""
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
        """scheduler atanmadıysa context'te olmamalı."""
        from core.plan_executor import PlanExecutor

        pe = PlanExecutor.__new__(PlanExecutor)
        pe.last_whatsapp_num = None
        pe.last_whatsapp_time = 0
        # scheduler atanmadı

        ctx = pe._build_context({})
        assert "scheduler" not in ctx
