"""[V8.0] J.A.R.V.I.S. Tool System Test Suite
━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━
Tools, registry, metadata and fallback tests.

Test Categories:
    - BaseTool + ToolResult build tests
    - ToolRegistry: register, alias, fallback, best_tool
    - Browser tools: mock Playwright
    - Desktop tools: mock pywinauto
    - System tools: mock skills wrappers
    - Executor integration: async execute + fallback"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from tools.base_tool import BaseTool, ToolResult
from tools.tool_registry import ToolRegistry, SMART_ALIASES, FALLBACK_CHAINS


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOOL RESULT TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestToolResult:
    """ToolResult dataclass testleri."""

    def test_success_result(self):
        result = ToolResult(success=True, message="OK")
        assert result.success is True
        assert result.message == "OK"
        assert result.speak == ""
        assert result.data == {}
        assert result.next_action is None

    def test_full_result(self):
        result = ToolResult(
            success=True,
            message="Done",
            speak="completed",
            data={"key": "value"},
            next_action="VISION_INTERPRET",
        )
        assert result.speak == "completed"
        assert result.data["key"] == "value"
        assert result.next_action == "VISION_INTERPRET"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TOOL REGISTRY TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class _DummyTool(BaseTool):
    """Simple tool for testing."""
    name = "dummy"
    description = "Test tool"
    protocol_tag = "DUMMY"
    parameters = {"input": {"type": "string"}}
    domain = "system"
    latency_ms = 100
    reliability_score = 0.99

    async def execute(self, params, engine_context=None):
        return ToolResult(
            success=True,
            message=f"Dummy executed: {params.get('input', '')}",
        )


class _WebTool(BaseTool):
    """Web domain test tool."""
    name = "web_test"
    description = "Web test"
    protocol_tag = "WEB_TEST"
    parameters = {}
    domain = "web"
    latency_ms = 2000
    reliability_score = 0.90

    async def execute(self, params, engine_context=None):
        return ToolResult(success=True, message="web ok")


class _WebTool2(BaseTool):
    """Low reliability web tool."""
    name = "web_test_2"
    description = "Web test 2"
    protocol_tag = "WEB_TEST_2"
    parameters = {}
    domain = "web"
    latency_ms = 1000
    reliability_score = 0.70

    async def execute(self, params, engine_context=None):
        return ToolResult(success=True, message="web2 ok")


class TestToolRegistry:
    """ToolRegistry register, lookup, metadata testleri."""

    def test_register_and_lookup(self):
        registry = ToolRegistry()
        registry.register(_DummyTool())

        tool = registry.get_by_protocol("DUMMY")
        assert tool is not None
        assert tool.name == "dummy"

    def test_unknown_tag_returns_none(self):
        registry = ToolRegistry()
        assert registry.get_by_protocol("NONEXISTENT") is None

    def test_smart_alias_resolution(self):
        registry = ToolRegistry()
        tool = _DummyTool()
        tool.protocol_tag = "GOOGLE_SEARCH"
        registry.register(tool)

        # "GOOGLE" alias → GOOGLE_SEARCH
        resolved = registry.get_by_protocol("GOOGLE")
        assert resolved is not None
        assert resolved.protocol_tag == "GOOGLE_SEARCH"

    def test_get_best_tool(self):
        """The tool with the highest reliability in the domain should be selected."""
        registry = ToolRegistry()
        registry.register(_WebTool())
        registry.register(_WebTool2())

        best = registry.get_best_tool("web")
        assert best is not None
        assert best.protocol_tag == "WEB_TEST"  # 0.90 > 0.70

    def test_get_best_tool_empty_domain(self):
        registry = ToolRegistry()
        assert registry.get_best_tool("desktop") is None

    def test_get_fallback_chain(self):
        """YT_PLAY → [YT_SEARCH] fallback zinciri."""
        registry = ToolRegistry()

        # Save YT_SEARCH so fallback works
        yt_search = _DummyTool()
        yt_search.protocol_tag = "YT_SEARCH"
        yt_search.name = "yt_search"
        registry.register(yt_search)

        chain = registry.get_fallback_chain("YT_PLAY")
        assert len(chain) == 1
        assert chain[0].protocol_tag == "YT_SEARCH"

    def test_get_fallback_chain_empty(self):
        """Undefined fallback → empty list."""
        registry = ToolRegistry()
        chain = registry.get_fallback_chain("NONEXISTENT")
        assert chain == []

    def test_register_override_warning(self):
        """When the same tag is saved again, it is overwritten."""
        registry = ToolRegistry()
        tool1 = _DummyTool()
        tool1.name = "first"
        tool2 = _DummyTool()
        tool2.name = "second"

        registry.register(tool1)
        registry.register(tool2)

        assert registry.get_by_protocol("DUMMY").name == "second"

    def test_export_schemas(self):
        registry = ToolRegistry()
        registry.register(_DummyTool())
        schema = registry.export_schemas()
        assert "DUMMY" in schema
        assert "Test tool" in schema

    def test_count_and_all_tags(self):
        registry = ToolRegistry()
        registry.register(_DummyTool())
        registry.register(_WebTool())

        assert registry.count == 2
        assert "DUMMY" in registry.all_tags
        assert "WEB_TEST" in registry.all_tags

    def test_get_tools_by_domain(self):
        registry = ToolRegistry()
        registry.register(_WebTool())
        registry.register(_WebTool2())
        registry.register(_DummyTool())

        web_tools = registry.get_tools_by_domain("web")
        assert len(web_tools) == 2
        # Sort by: reliability decreasing
        assert web_tools[0].reliability_score >= web_tools[1].reliability_score


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BROWSER TOOLS TESTS (Playwright mock)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestBrowserTools:
    """Test browser tools with mock Playwright."""

    @pytest.mark.asyncio
    async def test_google_search_empty_query(self):
        """Empty query → success=False."""
        from tools.browser_tool import GoogleSearchTool
        tool = GoogleSearchTool()
        result = await tool.execute({"query": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_google_search_fallback(self):
        """Chrome paths yoksa webbrowser fallback."""
        from tools.browser_tool import GoogleSearchTool
        tool = GoogleSearchTool()

        with patch("os.path.exists", return_value=False):
            with patch("webbrowser.open") as mock_open:
                result = await tool.execute({"query": "test"})
                assert result.success is True
                mock_open.assert_called_once()

    @pytest.mark.asyncio
    async def test_web_open_adds_https(self):
        """https:// should be added to the protocol-free URL."""
        from tools.browser_tool import WebOpenTool
        tool = WebOpenTool()

        with patch("tools.browser_tool._playwright_available", False):
            with patch("os.path.exists", return_value=False):
                with patch("webbrowser.open") as mock_open:
                    result = await tool.execute({"url": "google.com"})
                    assert result.success is True
                    mock_open.assert_called_with("https://google.com")

    @pytest.mark.asyncio
    async def test_web_open_empty_url(self):
        """Empty URL → success=False."""
        from tools.browser_tool import WebOpenTool
        tool = WebOpenTool()
        result = await tool.execute({"url": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_youtube_search_fallback(self):
        """YouTube arama webbrowser fallback."""
        from tools.browser_tool import YouTubeSearchTool
        tool = YouTubeSearchTool()

        with patch("tools.browser_tool._playwright_available", False):
            with patch("webbrowser.open") as mock_open:
                result = await tool.execute({"query": "lofi"})
                assert result.success is True
                assert "lofi" in result.message

    @pytest.mark.asyncio
    async def test_youtube_play_empty_query(self):
        """Empty query → success=False."""
        from tools.browser_tool import YouTubePlayTool
        tool = YouTubePlayTool()
        result = await tool.execute({"query": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_youtube_play_fallback(self):
        """YouTube play webbrowser fallback."""
        from tools.browser_tool import YouTubePlayTool
        tool = YouTubePlayTool()

        with patch("tools.browser_tool._playwright_available", False):
            with patch("webbrowser.open") as mock_open:
                result = await tool.execute({"query": "lofi beats"})
                assert result.success is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DESKTOP TOOLS TESTS (pywinauto mock)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestDesktopTools:
    """Test desktop tools with mocks."""

    @pytest.mark.asyncio
    async def test_app_open_empty_name(self):
        """Empty application name → success=False."""
        from tools.desktop_tool import AppOpenTool
        tool = AppOpenTool()
        result = await tool.execute({"app_name": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_app_open_known_app(self):
        """Open via familiar application (notepad) → NativeOps.open_app."""
        from tools.desktop_tool import AppOpenTool
        tool = AppOpenTool()

        with patch("tools.utils.native_ops.NativeOps.open_app",
                    return_value="SUCCESSFUL: notepad started.") as mock_open:
            result = await tool.execute({"app_name": "notepad"})
            assert result.success is True
            mock_open.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_kill_empty_name(self):
        """Empty application name → success=False."""
        from tools.desktop_tool import AppKillTool
        tool = AppKillTool()
        result = await tool.execute({"app_name": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_app_kill_self_preservation(self):
        """Protected process (python) → cannot be closed."""
        from tools.desktop_tool import AppKillTool
        tool = AppKillTool()
        result = await tool.execute({"app_name": "python"})
        assert result.success is False
        assert "protected" in result.message.lower()

    @pytest.mark.asyncio
    async def test_app_kill_web_app_detection(self):
        """Web application (youtube) → CONFIRM_BROWSER_KILL."""
        from tools.desktop_tool import AppKillTool
        tool = AppKillTool()
        result = await tool.execute({"app_name": "youtube"})
        assert result.success is False
        assert result.next_action == "CONFIRM_BROWSER_KILL"

    @pytest.mark.asyncio
    async def test_app_open_metadata(self):
        """Tool metadata accuracy."""
        from tools.desktop_tool import AppOpenTool
        tool = AppOpenTool()
        assert tool.domain == "desktop"
        assert tool.latency_ms == 3000
        assert 0.0 <= tool.reliability_score <= 1.0

    @pytest.mark.asyncio
    async def test_app_kill_metadata(self):
        """Tool metadata accuracy."""
        from tools.desktop_tool import AppKillTool
        tool = AppKillTool()
        assert tool.domain == "desktop"
        assert tool.protocol_tag == "APP_KILL"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SYSTEM TOOLS TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSystemTools:
    """System tool wrapper testleri."""

    @pytest.mark.asyncio
    async def test_whatsapp_empty_target(self):
        """Empty target → success=False."""
        from tools.system_tool import WhatsAppTool
        tool = WhatsAppTool()
        result = await tool.execute({"target": ""})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_whatsapp_dictation_mode(self):
        """Sadece isim → START_DICTATION tetiklenmeli."""
        from tools.system_tool import WhatsAppTool
        tool = WhatsAppTool()
        result = await tool.execute({"target": "Ablam"})
        assert result.success is True
        assert result.next_action == "START_DICTATION"
        assert result.data["recipient"] == "Ablam"

    @pytest.mark.asyncio
    async def test_whatsapp_delete_no_last(self):
        """Son mesaj yoksa → success=False."""
        from tools.system_tool import WhatsAppDeleteTool
        tool = WhatsAppDeleteTool()
        result = await tool.execute({}, engine_context={})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_whatsapp_delete_too_old(self):
        """5 dakikadan eski mesaj → silinmez."""
        from tools.system_tool import WhatsAppDeleteTool
        tool = WhatsAppDeleteTool()
        ctx = {
            "last_whatsapp_num": "+905551234567",
            "last_whatsapp_time": time.time() - 600,  # 10 minutes ago
        }
        result = await tool.execute({}, engine_context=ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_vision_tool_metadata(self):
        """Vision tool metadata accuracy."""
        from tools.system_tool import VisionTool
        tool = VisionTool()
        assert tool.domain == "system"
        assert tool.protocol_tag == "VISION"
        assert tool.latency_ms == 5000

    @pytest.mark.asyncio
    async def test_stress_test_tool(self):
        """Stres testi → RUN_STRESS_TEST sinyali."""
        from tools.system_tool import StressTestTool
        tool = StressTestTool()
        result = await tool.execute({})
        assert result.success is True
        assert result.next_action == "RUN_STRESS_TEST"

    @pytest.mark.asyncio
    async def test_tab_kill_tool(self):
        """Tab kapatma — pyautogui mock."""
        from tools.system_tool import TabKillTool
        tool = TabKillTool()

        with patch("pyautogui.hotkey") as mock_hotkey:
            result = await tool.execute({})
            assert result.success is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DEFAULT REGISTRY TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestDefaultRegistry:
    """create_default_registry() entegrasyon testi."""

    def test_creates_with_tools(self):
        """The default registry should register at least a few tools."""
        from tools.tool_registry import create_default_registry
        registry = create_default_registry()

        assert registry.count >= 5
        assert "GOOGLE_SEARCH" in registry.all_tags
        assert "APP_OPEN" in registry.all_tags

    def test_all_tools_have_metadata(self):
        """Each registered tool must have a domain/latency/reliability."""
        from tools.tool_registry import create_default_registry
        registry = create_default_registry()

        for tag in registry.all_tags:
            tool = registry.get_by_protocol(tag)
            assert tool.domain in ("web", "desktop", "system", "filesystem"), \
                f"{tag}: invalid domain '{tool.domain}'"
            assert tool.latency_ms > 0, \
                f"{tag}: latency_ms = {tool.latency_ms}"
            assert 0.0 <= tool.reliability_score <= 1.0, \
                f"{tag}: reliability = {tool.reliability_score}"

    def test_tool_schema_export(self):
        """Every tool should be exportable with to_schema()."""
        from tools.tool_registry import create_default_registry
        registry = create_default_registry()

        for tag in registry.all_tags:
            tool = registry.get_by_protocol(tag)
            schema = tool.to_schema()
            assert "name" in schema
            assert "protocol_tag" in schema
            assert "domain" in schema
            assert schema["protocol_tag"] == tag
