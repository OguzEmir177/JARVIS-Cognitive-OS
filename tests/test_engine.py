"""
[V8.0] J.A.R.V.I.S. Engine & State Manager Test Suite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Async engine, state transitions, task queue, ve reflector testleri.
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from core.state_manager import TaskState, StateManager
from core.task_queue import TaskQueue, TaskPriority
from core.reflector import Reflector
from core.config import EngineConfig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STATE MANAGER TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestStateManager:
    """StateManager lifecycle ve transition testleri."""

    def test_create_task(self, state_manager):
        """create_task → running durumunda bir TaskState döner."""
        task = state_manager.create_task("t1", "Google arat")

        assert task.id == "t1"
        assert task.goal == "Google arat"
        assert task.status == "running"
        assert task.start_time is not None
        assert task.retries == 0

    def test_complete_task(self, state_manager):
        """running → completed geçişi."""
        state_manager.create_task("t1", "test")
        state_manager.complete_task("t1")

        task = state_manager.get_task("t1")
        assert task.status == "completed"
        assert task.end_time is not None

    def test_fail_task(self, state_manager):
        """running → failed geçişi."""
        state_manager.create_task("t1", "test")
        state_manager.fail_task("t1", "timeout")

        task = state_manager.get_task("t1")
        assert task.status == "failed"
        assert task.last_error == "timeout"

    def test_invalid_transition_blocked(self, state_manager):
        """completed → failed geçişi engellenmeli."""
        state_manager.create_task("t1", "test")
        state_manager.complete_task("t1")
        state_manager.fail_task("t1", "should not work")

        task = state_manager.get_task("t1")
        assert task.status == "completed"  # Değişmemeli

    def test_retry_task(self, state_manager):
        """failed → pending geçişi (retry)."""
        state_manager.create_task("t1", "test")
        state_manager.fail_task("t1", "error")

        success = state_manager.retry_task("t1")
        assert success is True

        task = state_manager.get_task("t1")
        assert task.status == "pending"
        assert task.retries == 1
        assert task.last_error is None

    def test_get_all_tasks(self, state_manager):
        """Tüm görevlerin listesi döner."""
        state_manager.create_task("t1", "A")
        state_manager.create_task("t2", "B")

        tasks = state_manager.get_all_tasks()
        assert len(tasks) == 2

    def test_get_metrics(self, state_manager):
        """Metrikler doğru hesaplanmalı."""
        state_manager.create_task("t1", "A")
        state_manager.complete_task("t1")
        state_manager.create_task("t2", "B")
        state_manager.fail_task("t2", "err")

        metrics = state_manager.get_metrics()
        assert metrics["total"] == 2
        assert metrics["completed"] == 1
        assert metrics["failed"] == 1
        assert metrics["success_rate"] == 0.5

    def test_nonexistent_task_no_crash(self, state_manager):
        """Olmayan task_id ile çağrı → sessiz log, crash yok."""
        state_manager.complete_task("nonexistent")
        state_manager.fail_task("nonexistent", "err")
        assert state_manager.get_task("nonexistent") is None

    def test_clear(self, state_manager):
        """clear() tüm görevleri siler."""
        state_manager.create_task("t1", "A")
        state_manager.create_task("t2", "B")
        state_manager.clear()

        assert len(state_manager.get_all_tasks()) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TASK STATE TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTaskState:
    """TaskState dataclass property testleri."""

    def test_elapsed_ms_running(self):
        """Çalışan görevin süresi pozitif olmalı."""
        ts = TaskState(id="x", goal="test", start_time=time.monotonic() - 1.0)
        assert ts.elapsed_ms > 0

    def test_elapsed_ms_no_start(self):
        """start_time None → elapsed_ms = 0."""
        ts = TaskState(id="x", goal="test")
        assert ts.elapsed_ms == 0

    def test_elapsed_ms_completed(self):
        """Tamamlanan görev için sabit süre."""
        start = time.monotonic()
        ts = TaskState(
            id="x", goal="test",
            start_time=start,
            end_time=start + 1.5,
        )
        assert 1400 <= ts.elapsed_ms <= 1600

    def test_is_terminal(self):
        """completed ve failed terminal durumlar."""
        assert TaskState(id="x", goal="", status="completed").is_terminal
        assert TaskState(id="x", goal="", status="failed").is_terminal
        assert not TaskState(id="x", goal="", status="running").is_terminal
        assert not TaskState(id="x", goal="", status="pending").is_terminal


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TASK QUEUE TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTaskQueue:
    """AsyncIO TaskQueue testleri."""

    @pytest.mark.asyncio
    async def test_put_and_get(self, task_queue):
        """Basit put → get döngüsü."""
        await task_queue.put("task1")
        result = await task_queue.get(timeout=1.0)
        assert result == "task1"

    @pytest.mark.asyncio
    async def test_priority_ordering(self, task_queue):
        """Yüksek öncelikli görev önce gelir."""
        await task_queue.put("low", priority=TaskPriority.LOW)
        await task_queue.put("critical", priority=TaskPriority.CRITICAL)
        await task_queue.put("normal", priority=TaskPriority.NORMAL)

        first = await task_queue.get(timeout=1.0)
        second = await task_queue.get(timeout=1.0)
        third = await task_queue.get(timeout=1.0)

        assert first == "critical"
        assert second == "normal"
        assert third == "low"

    @pytest.mark.asyncio
    async def test_get_timeout(self, task_queue):
        """Boş queue'da get → TimeoutError."""
        with pytest.raises(asyncio.TimeoutError):
            await task_queue.get(timeout=0.1)

    @pytest.mark.asyncio
    async def test_cancel_all(self, task_queue):
        """cancel_all tüm görevleri temizler."""
        await task_queue.put("a")
        await task_queue.put("b")
        await task_queue.put("c")

        cancelled = await task_queue.cancel_all()
        assert cancelled == 3
        assert task_queue.is_empty
        assert task_queue.is_cancelled

    @pytest.mark.asyncio
    async def test_put_after_cancel_raises(self, task_queue):
        """Cancel sonrası put → RuntimeError."""
        await task_queue.cancel_all()
        with pytest.raises(RuntimeError):
            await task_queue.put("should_fail")

    @pytest.mark.asyncio
    async def test_reset(self, task_queue):
        """reset() sonrası queue tekrar kullanılabilir."""
        await task_queue.cancel_all()
        task_queue.reset()
        assert not task_queue.is_cancelled
        await task_queue.put("new_task")
        result = await task_queue.get(timeout=1.0)
        assert result == "new_task"

    def test_properties(self, task_queue):
        """size, is_empty, is_full property'leri."""
        assert task_queue.size == 0
        assert task_queue.is_empty
        assert not task_queue.is_full


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REFLECTOR TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestReflector:
    """Kural-tabanlı reflection engine testleri."""

    @pytest.mark.asyncio
    async def test_successful_task_reflection(self, reflector, sample_task_state):
        """Başarılı görev → outcome=success."""
        result = await reflector.reflect(sample_task_state)

        assert result is not None
        assert result["outcome"] == "success"
        assert result["task_type"] == "web"
        assert "GOOGLE_SEARCH" in result["tool_used"]
        assert "[NE YAPTIM]" in result["summary"]

    @pytest.mark.asyncio
    async def test_failed_task_reflection(self, reflector, failed_task_state):
        """Başarısız görev → outcome=failure."""
        result = await reflector.reflect(failed_task_state)

        assert result is not None
        assert result["outcome"] == "failure"
        assert result["task_type"] == "desktop"
        assert "APP_KILL" in result["tool_used"]
        assert "Process bulunamadı" in result["summary"]

    @pytest.mark.asyncio
    async def test_partial_outcome(self, reflector):
        """Karışık başarı/başarısızlık → outcome=partial."""
        ts = TaskState(
            id="t3", goal="çoklu görev", status="failed",
            start_time=time.monotonic() - 2, end_time=time.monotonic(),
            tool_history=[
                {"tool": "GOOGLE_SEARCH", "success": True, "duration_ms": 1000},
                {"tool": "APP_KILL", "success": False, "duration_ms": 2000},
            ],
        )
        result = await reflector.reflect(ts)

        assert result is not None
        assert result["outcome"] == "partial"
        assert result["task_type"] == "mixed"

    @pytest.mark.asyncio
    async def test_no_reflection_for_running_task(self, reflector):
        """Running durumdaki görev için reflection üretilmez."""
        ts = TaskState(id="t4", goal="test", status="running")
        result = await reflector.reflect(ts)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_reflection_for_empty_history(self, reflector):
        """Tool kullanılmamış görev (saf sohbet) → reflection yok."""
        ts = TaskState(
            id="t5", goal="merhaba", status="completed",
            start_time=time.monotonic() - 1, end_time=time.monotonic(),
            tool_history=[],
        )
        result = await reflector.reflect(ts)
        assert result is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENGINE CONFIG TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestEngineConfig:
    """EngineConfig default değerler testleri."""

    def test_default_values(self):
        """Default config Groq free tier'a uygun olmalı."""
        config = EngineConfig()

        assert config.tool_timeout_seconds == 30.0
        assert config.brain_timeout_seconds == 10.0
        assert config.max_replan_attempts == 2
        assert config.brain_connect_retries == 5
        assert len(config.brain_models) >= 2

    def test_custom_values(self, engine_config):
        """Custom config fixture'ı doğru override etmeli."""
        assert engine_config.tool_timeout_seconds == 5.0
        assert engine_config.max_replan_attempts == 1
