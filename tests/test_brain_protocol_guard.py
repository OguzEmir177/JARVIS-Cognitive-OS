"""test_brain_protocol_guard.py — GroqBrain protocol filtering tests.

Fix 1: PLAN/SCHEDULE is filtered from tools_payload.
Fix 2: If an unknown tool_call comes, the text is fallback.

All Groq API calls are mocked."""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from core.brain import GroqBrain


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_config(**overrides):
    """Creates a minimal GroqBrain config object."""
    cfg = MagicMock()
    cfg.brain_models = ["llama-3.3-70b-versatile"]
    cfg.max_tokens = 2048
    cfg.temperature = 0.3
    cfg.function_calling_enabled = overrides.get("function_calling_enabled", True)
    return cfg


def _make_tool(tag, description="test tool", params=None):
    """Sahte tool nesnesi."""
    tool = MagicMock()
    tool.protocol_tag = tag
    tool.description = description
    tool.parameters = params or {"input": {"type": "string", "description": "test"}}
    return tool


def _make_registry(*tools):
    """Sahte tool registry."""
    registry = MagicMock()
    registry.count = len(tools)
    registry._tools = {t.protocol_tag: t for t in tools}
    registry.get_tools_prompt.return_value = "tools prompt"
    return registry


def _make_choice(tool_calls=None, content=None):
    """Groq API choice object simulation."""
    message = MagicMock()
    message.tool_calls = tool_calls
    message.content = content
    choice = MagicMock()
    choice.message = message
    return choice


def _make_tool_call(name, arguments_dict):
    """Groq tool_call object simulation."""
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments_dict)
    return tc


def _make_response(choice):
    """Groq API response wrapper."""
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def brain_with_tools():
    """Creates GroqBrain with function_calling_enabled=True."""
    config = _make_config(function_calling_enabled=True)
    tools = [
        _make_tool("GOOGLE_SEARCH"),
        _make_tool("APP_OPEN"),
        _make_tool("SPEAK"),
        _make_tool("PLAN"),        # This should be filtered
        _make_tool("SCHEDULE"),    # This should also be filtered
    ]
    registry = _make_registry(*tools)

    with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
        with patch("core.brain.AsyncGroq"):
            brain = GroqBrain(config, tool_registry=registry)
    return brain


# ─────────────────────────────────────────────────────────────────────────────
# VALID_PROTOCOLS Build Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestValidProtocols:
    """VALID_PROTOCOLS validates the set structure."""

    def test_contains_all_iron_dome_protocols(self):
        expected = {
            "GOOGLE_SEARCH", "WEB_OPEN", "YT_SEARCH", "YT_PLAY",
            "APP_OPEN", "APP_KILL", "WHATSAPP_MESSAGE", "WHATSAPP_DELETE",
            "VISION", "STRESS_TEST", "TAB_KILL", "SPEAK",
            "FILE_READ", "FILE_SUMMARIZE", "FILE_WRITE",
            "STEAM_LAUNCH", "SYSTEM_POWER",
            "EPIC_LAUNCH", "CLOSE_LAST_TAB",
            "SYSTEM_SHUTDOWN", "SCHEDULE", "WEB_SEARCH",
            "REMEMBER", "MAP_SHOW", "CHART_SHOW",
        }
        assert GroqBrain.VALID_PROTOCOLS == expected

    def test_plan_not_in_valid(self):
        assert "PLAN" not in GroqBrain.VALID_PROTOCOLS

    def test_excluded_tags(self):
        assert "PLAN" in GroqBrain._EXCLUDED_TOOL_TAGS
        assert "SCHEDULE" in GroqBrain._EXCLUDED_TOOL_TAGS


# ─────────────────────────────────────────────────────────────────────────────
#  Fix 1 — tools_payload Filtreleme Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestToolsPayloadFilter:
    """PLAN/SCHEDULE verifies that tool_tags are not added to tools_payload."""

    @pytest.mark.asyncio
    async def test_plan_excluded_from_tools_payload(self, brain_with_tools):
        """Tool with PLAN tag should not be sent to Groq API."""
        brain = brain_with_tools

        # The response the API will return (simple text)
        choice = _make_choice(content="[PROTOCOL: SPEAK] Merhaba")
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        await brain.think("test input")

        # Check the tools parameter in the API call
        call_kwargs = brain.client.chat.completions.create.call_args[1]
        if "tools" in call_kwargs:
            tool_names = [t["function"]["name"] for t in call_kwargs["tools"]]
            assert "PLAN" not in tool_names
            assert "SCHEDULE" not in tool_names
            assert "GOOGLE_SEARCH" in tool_names
            assert "APP_OPEN" in tool_names

    @pytest.mark.asyncio
    async def test_valid_tools_still_sent(self, brain_with_tools):
        """Valid tools must still be in the payload."""
        brain = brain_with_tools

        choice = _make_choice(content="test")
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        await brain.think("test input")

        call_kwargs = brain.client.chat.completions.create.call_args[1]
        if "tools" in call_kwargs:
            tool_names = [t["function"]["name"] for t in call_kwargs["tools"]]
            # 5 tools registered, 2 excluded → 3 should remain
            assert len(tool_names) == 3


# ─────────────────────────────────────────────────────────────────────────────
#  Fix 2 — Bilinmeyen Tool Call Koruma Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestUnknownToolCallGuard:
    """The text confirms the fallback when the unknown tool_call arrives."""

    @pytest.mark.asyncio
    async def test_unknown_tag_with_content_fallback(self, brain_with_tools):
        """If there is unknown tag + content, go to → content."""
        brain = brain_with_tools

        tool_call = _make_tool_call("PLAN", {"steps": "a,b,c"})
        choice = _make_choice(
            tool_calls=[tool_call],
            content="[PLAN]\nGOOGLE_SEARCH test\nSPEAK result\n[/PLAN]"
        )
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        reply = await brain.think("research and tell")
        assert "[PLAN]" in reply
        assert "[PROTOCOL: PLAN]" not in reply

    @pytest.mark.asyncio
    async def test_unknown_tag_no_content_retries_without_tools(self, brain_with_tools):
        """Unknown tag + empty content → call again without tools."""
        brain = brain_with_tools

        # First call: unknown tool_call, empty content
        tool_call = _make_tool_call("PLAN", {"steps": "a"})
        first_choice = _make_choice(tool_calls=[tool_call], content=None)
        first_response = _make_response(first_choice)

        # Retry call: plaintext
        retry_choice = _make_choice(content="[PROTOCOL: SPEAK] The plan could not be prepared.")
        retry_response = _make_response(retry_choice)

        brain.client.chat.completions.create = AsyncMock(
            side_effect=[first_response, retry_response]
        )

        reply = await brain.think("complex task")
        # API must be called 2 times
        assert brain.client.chat.completions.create.call_count == 2

        # There should be no tools in the retry call
        retry_kwargs = brain.client.chat.completions.create.call_args[1]
        assert "tools" not in retry_kwargs

        assert "SPEAK" in reply

    @pytest.mark.asyncio
    async def test_valid_tag_processed_normally(self, brain_with_tools):
        """The current tag is in the format (GOOGLE_SEARCH) → [PROTOCOL: ...]."""
        brain = brain_with_tools

        tool_call = _make_tool_call("GOOGLE_SEARCH", {"query": "python"})
        choice = _make_choice(tool_calls=[tool_call])
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        reply = await brain.think("python ara")
        assert reply == "[PROTOCOL: GOOGLE_SEARCH] python"

    @pytest.mark.asyncio
    async def test_whatsapp_tag_processed_with_pipe(self, brain_with_tools):
        """WHATSAPP_MESSAGE → person|message format must be preserved."""
        brain = brain_with_tools

        tool_call = _make_tool_call("WHATSAPP_MESSAGE", {
            "kisi": "Ablam",
            "mesaj": "Selam"
        })
        choice = _make_choice(tool_calls=[tool_call])
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        reply = await brain.think("ablama selam yaz")
        assert reply == "[PROTOCOL: WHATSAPP_MESSAGE] Ablam|Selam"


# ─────────────────────────────────────────────────────────────────────────────
# Signature Contract Test
# ─────────────────────────────────────────────────────────────────────────────

class TestSignatureContract:
    """Verifies that the think() signature has not changed."""

    def test_think_signature(self):
        import inspect
        sig = inspect.signature(GroqBrain.think)
        params = list(sig.parameters.keys())
        assert params == ["self", "user_input"]
        assert sig.return_annotation is str
