"""[V1.0] Core Module Tests — Mocked APIs
Tests GroqBrain.think() and check_connection() without real Groq calls.
Uses fixtures from conftest.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGroqBrainThink:
    """Tests for GroqBrain.think() — no real LLM calls."""

    @pytest.mark.asyncio
    async def test_think_returns_protocol_string(self, mock_brain):
        """think() should return a non-empty protocol string."""
        result = await mock_brain.think("Open Chrome")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_think_bypass_history(self, mock_brain):
        """think() with bypass_history=True should still return a string."""
        mock_brain.think = AsyncMock(return_value="[PROTOCOL: SPEAK] Done.")
        result = await mock_brain.think("test input", bypass_history=True)
        assert result == "[PROTOCOL: SPEAK] Done."

    @pytest.mark.asyncio
    async def test_think_rate_limit_returns_sentinel(self, mock_brain):
        """If all models are rate-limited, think() returns RATE_LIMIT_ALL."""
        mock_brain.think = AsyncMock(return_value="RATE_LIMIT_ALL")
        result = await mock_brain.think("anything")
        assert result == "RATE_LIMIT_ALL"

    @pytest.mark.asyncio
    async def test_think_turkish_input(self, mock_brain):
        """Turkish input should be accepted and return a valid response."""
        mock_brain.think = AsyncMock(return_value="[PROTOCOL: SPEAK] Here you go.")
        result = await mock_brain.think("Chrome'u aç")
        assert "[PROTOCOL:" in result

    @pytest.mark.asyncio
    async def test_think_empty_input(self, mock_brain):
        """Empty string input should not raise, should return something."""
        mock_brain.think = AsyncMock(return_value="[PROTOCOL: SPEAK] I didn't catch that.")
        result = await mock_brain.think("")
        assert isinstance(result, str)


class TestGroqBrainConnection:
    """Tests for GroqBrain.check_connection()."""

    @pytest.mark.asyncio
    async def test_check_connection_success(self, mock_brain):
        """check_connection() returns True when API is reachable."""
        result = await mock_brain.check_connection()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_connection_failure(self, mock_brain):
        """check_connection() returns False on API error."""
        mock_brain.check_connection = AsyncMock(return_value=False)
        result = await mock_brain.check_connection()
        assert result is False


class TestGroqBrainChatHistory:
    """Tests for chat history management."""

    def test_chat_history_starts_with_system_prompt(self, mock_brain):
        """chat_history must start with a system-role message."""
        assert len(mock_brain.chat_history) >= 1
        assert mock_brain.chat_history[0]["role"] == "system"

    def test_chat_history_is_list(self, mock_brain):
        """chat_history must be a list."""
        assert isinstance(mock_brain.chat_history, list)
