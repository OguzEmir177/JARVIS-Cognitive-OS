"""
test_brain_protocol_guard.py — GroqBrain protokol filtreleme testleri.

Fix 1: tools_payload'dan PLAN/SCHEDULE filtrelenir.
Fix 2: Bilinmeyen tool_call gelirse metin fallback yapılır.

Tüm Groq API çağrıları mock'lanır.
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from core.brain import GroqBrain


# ─────────────────────────────────────────────────────────────────────────────
#  Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────

def _make_config(**overrides):
    """Minimal GroqBrain config nesnesi oluşturur."""
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
    """Groq API choice nesnesi simülasyonu."""
    message = MagicMock()
    message.tool_calls = tool_calls
    message.content = content
    choice = MagicMock()
    choice.message = message
    return choice


def _make_tool_call(name, arguments_dict):
    """Groq tool_call nesnesi simülasyonu."""
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
    """function_calling_enabled=True ile GroqBrain oluşturur."""
    config = _make_config(function_calling_enabled=True)
    tools = [
        _make_tool("GOOGLE_SEARCH"),
        _make_tool("APP_OPEN"),
        _make_tool("SPEAK"),
        _make_tool("PLAN"),        # Bu filtrelenmeli
        _make_tool("SCHEDULE"),    # Bu da filtrelenmeli
    ]
    registry = _make_registry(*tools)

    with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
        with patch("core.brain.AsyncGroq"):
            brain = GroqBrain(config, tool_registry=registry)
    return brain


# ─────────────────────────────────────────────────────────────────────────────
#  VALID_PROTOCOLS Yapı Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestValidProtocols:
    """VALID_PROTOCOLS set yapısını doğrular."""

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
    """PLAN/SCHEDULE tool_tag'lerinin tools_payload'a eklenmediğini doğrular."""

    @pytest.mark.asyncio
    async def test_plan_excluded_from_tools_payload(self, brain_with_tools):
        """PLAN tag'li tool, Groq API'ye gönderilmemeli."""
        brain = brain_with_tools

        # API'nin döneceği yanıt (basit metin)
        choice = _make_choice(content="[PROTOCOL: SPEAK] Merhaba")
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        await brain.think("test input")

        # API çağrısında tools parametresini kontrol et
        call_kwargs = brain.client.chat.completions.create.call_args[1]
        if "tools" in call_kwargs:
            tool_names = [t["function"]["name"] for t in call_kwargs["tools"]]
            assert "PLAN" not in tool_names
            assert "SCHEDULE" not in tool_names
            assert "GOOGLE_SEARCH" in tool_names
            assert "APP_OPEN" in tool_names

    @pytest.mark.asyncio
    async def test_valid_tools_still_sent(self, brain_with_tools):
        """Geçerli tool'lar hala payload'da olmalı."""
        brain = brain_with_tools

        choice = _make_choice(content="test")
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        await brain.think("test input")

        call_kwargs = brain.client.chat.completions.create.call_args[1]
        if "tools" in call_kwargs:
            tool_names = [t["function"]["name"] for t in call_kwargs["tools"]]
            # 5 tool kayıtlı, 2'si excluded → 3 kalmalı
            assert len(tool_names) == 3


# ─────────────────────────────────────────────────────────────────────────────
#  Fix 2 — Bilinmeyen Tool Call Koruma Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestUnknownToolCallGuard:
    """Bilinmeyen tool_call geldiğinde metin fallback'i doğrular."""

    @pytest.mark.asyncio
    async def test_unknown_tag_with_content_fallback(self, brain_with_tools):
        """Bilinmeyen tag + content varsa → content'e düş."""
        brain = brain_with_tools

        tool_call = _make_tool_call("PLAN", {"steps": "a,b,c"})
        choice = _make_choice(
            tool_calls=[tool_call],
            content="[PLAN]\nGOOGLE_SEARCH test\nSPEAK sonuç\n[/PLAN]"
        )
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        reply = await brain.think("araştır ve söyle")
        assert "[PLAN]" in reply
        assert "[PROTOCOL: PLAN]" not in reply

    @pytest.mark.asyncio
    async def test_unknown_tag_no_content_retries_without_tools(self, brain_with_tools):
        """Bilinmeyen tag + boş content → tools olmadan tekrar çağır."""
        brain = brain_with_tools

        # İlk çağrı: bilinmeyen tool_call, boş content
        tool_call = _make_tool_call("PLAN", {"steps": "a"})
        first_choice = _make_choice(tool_calls=[tool_call], content=None)
        first_response = _make_response(first_choice)

        # Retry çağrısı: düz metin
        retry_choice = _make_choice(content="[PROTOCOL: SPEAK] Plan hazırlanamadı.")
        retry_response = _make_response(retry_choice)

        brain.client.chat.completions.create = AsyncMock(
            side_effect=[first_response, retry_response]
        )

        reply = await brain.think("karmaşık görev")
        # API 2 kez çağrılmalı
        assert brain.client.chat.completions.create.call_count == 2

        # Retry çağrısında tools olmamalı
        retry_kwargs = brain.client.chat.completions.create.call_args[1]
        assert "tools" not in retry_kwargs

        assert "SPEAK" in reply

    @pytest.mark.asyncio
    async def test_valid_tag_processed_normally(self, brain_with_tools):
        """Geçerli tag (GOOGLE_SEARCH) → [PROTOCOL: ...] formatında."""
        brain = brain_with_tools

        tool_call = _make_tool_call("GOOGLE_SEARCH", {"query": "python"})
        choice = _make_choice(tool_calls=[tool_call])
        response = _make_response(choice)
        brain.client.chat.completions.create = AsyncMock(return_value=response)

        reply = await brain.think("python ara")
        assert reply == "[PROTOCOL: GOOGLE_SEARCH] python"

    @pytest.mark.asyncio
    async def test_whatsapp_tag_processed_with_pipe(self, brain_with_tools):
        """WHATSAPP_MESSAGE → kisi|mesaj formatı korunmalı."""
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
#  İmza Sözleşme Testi
# ─────────────────────────────────────────────────────────────────────────────

class TestSignatureContract:
    """think() imzasının değişmediğini doğrular."""

    def test_think_signature(self):
        import inspect
        sig = inspect.signature(GroqBrain.think)
        params = list(sig.parameters.keys())
        assert params == ["self", "user_input"]
        assert sig.return_annotation is str
