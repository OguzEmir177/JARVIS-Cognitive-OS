"""[V8.0] J.A.R.V.I.S. Engine & State Manager Test Suite
━━━━━━━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━━━━━━
Async engine, state transitions, task queue, and reflector tests."""

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
    """StateManager lifecycle and transition tests."""

    def test_create_task(self, state_manager):
        """create_task → returns a TaskState in running state."""
        task = state_manager.create_task("t1", "Google arat")

        assert task.id == "t1"
        assert task.goal == "Google arat"
        assert task.status == "running"
        assert task.start_time is not None
        assert task.retries == 0

    def test_complete_task(self, state_manager):
        """running → completed transition."""
        state_manager.create_task("t1", "test")
        state_manager.complete_task("t1")

        task = state_manager.get_task("t1")
        assert task.status == "completed"
        assert task.end_time is not None

    def test_fail_task(self, state_manager):
        """running → failed transition."""
        state_manager.create_task("t1", "test")
        state_manager.fail_task("t1", "timeout")

        task = state_manager.get_task("t1")
        assert task.status == "failed"
        assert task.last_error == "timeout"

    def test_invalid_transition_blocked(self, state_manager):
        """The completed → failed transition should be blocked."""
        state_manager.create_task("t1", "test")
        state_manager.complete_task("t1")
        state_manager.fail_task("t1", "should not work")

        task = state_manager.get_task("t1")
        assert task.status == "completed"  # Must not change

    def test_retry_task(self, state_manager):
        """failed → pending transition (retry)."""
        state_manager.create_task("t1", "test")
        state_manager.fail_task("t1", "error")

        success = state_manager.retry_task("t1")
        assert success is True

        task = state_manager.get_task("t1")
        assert task.status == "pending"
        assert task.retries == 1
        assert task.last_error is None

    def test_get_all_tasks(self, state_manager):
        """A list of all tasks is returned."""
        state_manager.create_task("t1", "A")
        state_manager.create_task("t2", "B")

        tasks = state_manager.get_all_tasks()
        assert len(tasks) == 2

    def test_get_metrics(self, state_manager):
        """Metrics must be calculated correctly."""
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
        """Call with non-existent task_id → silent log, no crash."""
        state_manager.complete_task("nonexistent")
        state_manager.fail_task("nonexistent", "err")
        assert state_manager.get_task("nonexistent") is None

    def test_clear(self, state_manager):
        """clear() clears all tasks."""
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
        """The duration of the running task must be positive."""
        ts = TaskState(id="x", goal="test", start_time=time.monotonic() - 1.0)
        assert ts.elapsed_ms > 0

    def test_elapsed_ms_no_start(self):
        """start_time None → elapsed_ms = 0."""
        ts = TaskState(id="x", goal="test")
        assert ts.elapsed_ms == 0

    def test_elapsed_ms_completed(self):
        """Fixed time for completed task."""
        start = time.monotonic()
        ts = TaskState(
            id="x", goal="test",
            start_time=start,
            end_time=start + 1.5,
        )
        assert 1400 <= ts.elapsed_ms <= 1600

    def test_is_terminal(self):
        """completed and failed terminal states."""
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
        """Simple put → get loop."""
        await task_queue.put("task1")
        result = await task_queue.get(timeout=1.0)
        assert result == "task1"

    @pytest.mark.asyncio
    async def test_priority_ordering(self, task_queue):
        """The high priority task comes first."""
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
        """get → TimeoutError on empty queue."""
        with pytest.raises(asyncio.TimeoutError):
            await task_queue.get(timeout=0.1)

    @pytest.mark.asyncio
    async def test_cancel_all(self, task_queue):
        """cancel_all clears all tasks."""
        await task_queue.put("a")
        await task_queue.put("b")
        await task_queue.put("c")

        cancelled = await task_queue.cancel_all()
        assert cancelled == 3
        assert task_queue.is_empty
        assert task_queue.is_cancelled

    @pytest.mark.asyncio
    async def test_put_after_cancel_raises(self, task_queue):
        """put → RuntimeError after cancel."""
        await task_queue.cancel_all()
        with pytest.raises(RuntimeError):
            await task_queue.put("should_fail")

    @pytest.mark.asyncio
    async def test_reset(self, task_queue):
        """After reset(), the queue can be used again."""
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
    """Rule-based reflection engine tests."""

    @pytest.mark.asyncio
    async def test_successful_task_reflection(self, reflector, sample_task_state):
        """Successful mission → outcome=success."""
        result = await reflector.reflect(sample_task_state)

        assert result is not None
        assert result["outcome"] == "success"
        assert result["task_type"] == "web"
        assert "GOOGLE_SEARCH" in result["tool_used"]
        assert "[NE YAPTIM]" in result["summary"]

    @pytest.mark.asyncio
    async def test_failed_task_reflection(self, reflector, failed_task_state):
        """Failed mission → outcome=failure."""
        result = await reflector.reflect(failed_task_state)

        assert result is not None
        assert result["outcome"] == "failure"
        assert result["task_type"] == "desktop"
        assert "APP_KILL" in result["tool_used"]
        assert "Process not found" in result["summary"]

    @pytest.mark.asyncio
    async def test_partial_outcome(self, reflector):
        """Mixed success/failure → outcome=partial."""
        ts = TaskState(
            id="t3", goal="multitasking", status="failed",
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
        """No reflection is produced for the task in running state."""
        ts = TaskState(id="t4", goal="test", status="running")
        result = await reflector.reflect(ts)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_reflection_for_empty_history(self, reflector):
        """Task without tools (pure chat) → no reflection."""
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
    """EngineConfig default values ​​tests."""

    def test_default_values(self):
        """Default config must be suitable for Groq free tier."""
        config = EngineConfig()

        assert config.tool_timeout_seconds == 30.0
        assert config.brain_timeout_seconds == 10.0
        assert config.max_replan_attempts == 2
        assert config.brain_connect_retries == 5
        assert len(config.brain_models) >= 2

    def test_custom_values(self, engine_config):
        """The custom config should override the fixture correctly."""
        assert engine_config.tool_timeout_seconds == 5.0
        assert engine_config.max_replan_attempts == 1
