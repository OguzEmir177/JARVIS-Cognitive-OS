"""[V8.2] J.A.R.V.I.S. Task State Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Central state repository that manages the lifecycle of each task.

Responsibilities:
    - Creating and updating TaskState
    - Status transition control (pending → running → completed/failed)
    - Metric query (all tasks, success rate)

Design Decisions:
    - In-memory dict-based store (SQLite/Redis overkill)
    - It is not thread-safe because it works in a single asyncio event loop
    - TaskState is not immutable — the engine can update the field directly
      (like tool_history.append) but status transitions
      Must be done via StateManager (consistency)

Edge Cases:
    - If create_task is called with the same task_id → log warning, overwrite
    - Silent log instead of fail/complete → KeyError with non-existent task_id
    - elapsed_ms account: returns 0 if start_time is None"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("JARVIS.StateManager")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TASK STATE — Individual Task Status Object
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class TaskState:
    """Lifecycle data of a single task.

    Status Transitions:
        pending → running → completed
                         ↘ failed

    Attributes:
        id: Unique task ID (abbreviation uuid)
        goal: User's original request
        status: Current status (pending/running/failed/completed)
        retries: How many times has it been retried
        last_error: Last error message (No error if None)
        tool_history: Record of used tools
        outputs: Task outputs
        start_time: Task start time (monotonic)
        end_time: Task end time (monotonic)
        created_at: Task creation time (for wall clock, logs)
        _step_results: {TAG: metin} repository for context transfer between steps
                       (hidden from repr, used for interpolation only)"""

    id: str
    goal: str
    status: str = "pending"
    retries: int = 0
    last_error: Optional[str] = None
    tool_history: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Any] = field(default_factory=list)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    _step_results: Dict[str, str] = field(default_factory=dict, repr=False)

    # ── PLAN EXECUTOR API ────────────────────────────────────────────────

    def is_active(self) -> bool:
        """Is the task still processable?

        plan_executor.execute_plan() checks this before each step;
        If the task is failed/completed externally, the loop is broken.

        Returns:
            True → pending or running: continue step execution
            False → completed or failed: break the loop"""
        return self.status in ("pending", "running")

    def add_tool_call(self, tag: str, arg: str, result_dict: dict) -> None:
        self.tool_history.append({
            "tool":        tag,
            "arg":         arg,
            "result":      result_dict,
            "success":     result_dict.get("success", False),
            "duration_ms": result_dict.get("duration_ms", 0),
        })

        data = result_dict.get("data", {}) or {}
        
        # 🛡️ V8.2 FIX: ACTUAL DATA SHOULD BE PRIORITY! (In the past, 'speak' was the priority)
        interpolation_text = (
            str(data.get("summary", ""))
            or str(data.get("result", ""))
            or str(data.get("content", ""))
            or result_dict.get("message", "")
            or result_dict.get("speak", "")
        )

        if tag and interpolation_text:
            if tag in self._step_results:
                # If the same tool was used again, do not delete the old data, add it next to it!
                self._step_results[tag] += f"\n\n--- ADDITIONAL RESULT ---\n{interpolation_text}"
            else:
                self._step_results[tag] = interpolation_text
            logger.debug(
                f"[StateManager] _step_results['{tag}'] updated"
                f"({len(interpolation_text)} karakter)"
            )

    def get_results(self) -> dict:
        """Returns the {TAG: metin} dictionary that executor._interpolate_argument expects.

        A copy is returned: the internal store is preserved even if the calling code mutates the dictionary.

        Returns:
            Example: {"GOOGLE_SEARCH": "Messi Arjantin milli takımında...",
                    "WEB_OPEN": "Sayfa açıldı."}"""
        return dict(self._step_results)

    # ── PROPERTIES ──────────────────────────────────────────────────────

    @property
    def elapsed_ms(self) -> int:
        """Returns the task duration in milliseconds.

        Edge case: if start_time is not set yet → 0
        Edge case: end_time does not exist yet (still working) → time so far"""
        if self.start_time is None:
            return 0
        end = self.end_time if self.end_time is not None else time.monotonic()
        return int((end - self.start_time) * 1000)

    @property
    def is_terminal(self) -> bool:
        """Is the task in terminal state (completed or failed)?"""
        return self.status in ("completed", "failed")

    def __repr__(self) -> str:
        return (
            f"TaskState(id='{self.id}', goal='{self.goal[:40]}...', "
            f"status='{self.status}', retries={self.retries}, "
            f"elapsed={self.elapsed_ms}ms)"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STATE MANAGER — Central Task Repository
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# Valid status transitions — no transitions beyond this
_VALID_TRANSITIONS: Dict[str, set] = {
    "pending":   {"running"},
    "running":   {"completed", "failed"},
    "completed": set(),       # Terminal — no transition
    "failed":    {"pending"},  # In case of retry, it can be put back into pending mode
}


class StateManager:
    """In-memory store that manages task states.

    Usage (compatible with engine.py):
        sm = StateManager()
        task = sm.create_task(task_id="abc123", goal="Search on Google")
        sm.start_task("abc123")
        sm.complete_task("abc123") # or sm.fail_task("abc123", "timeout")

        all_tasks = sm.get_all_tasks()
        metrics = sm.get_metrics()

    Thread Safety:
        Since it works in a single asyncio loop, no lock is required.
        If multi-threading is required in the future, asyncio.Lock can be added."""

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskState] = {}

    # ── LIFECYCLE METHODS ──

    def create_task(self, task_id: str, goal: str) -> TaskState:
        """Creates a new task and puts it in 'running' state.

        engine.py starts processing immediately after calling this,
        so create + start combined."""
        if task_id in self._tasks:
            logger.warning(
                f"Task '{task_id}' already exists, being overwritten."
                f"Eski durum: {self._tasks[task_id].status}"
            )

        task = TaskState(
            id=task_id,
            goal=goal,
            status="running",
            start_time=time.monotonic(),
        )
        self._tasks[task_id] = task

        logger.info(
            f"Task created and started: {task_id} → '{goal[:50]}'"
        )
        return task

    def complete_task(self, task_id: str) -> None:
        """Marks the task as completed successfully."""
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"complete_task: '{task_id}' not found.")
            return

        if not self._can_transition(task, "completed"):
            return

        task.status = "completed"
        task.end_time = time.monotonic()

        logger.info(
            f"Task completed: {task_id}"
            f"(duration: {task.elapsed_ms}ms,"
            f"tools: {len(task.tool_history)})"
        )

    def fail_task(self, task_id: str, reason: str) -> None:
        """Marks the task as failed."""
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"fail_task: '{task_id}' not found.")
            return

        if not self._can_transition(task, "failed"):
            return

        task.status = "failed"
        task.last_error = reason
        task.end_time = time.monotonic()

        logger.error(
            f"Task failed: {task_id} → {reason}"
            f"(duration: {task.elapsed_ms}ms)"
        )

    def retry_task(self, task_id: str) -> bool:
        """Places the failed task on pending for retrying."""
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"retry_task: '{task_id}' not found.")
            return False

        if not self._can_transition(task, "pending"):
            return False

        task.status = "pending"
        task.retries += 1
        task.last_error = None
        task.end_time = None
        task.start_time = None

        logger.info(f"Task retry: {task_id} (deneme #{task.retries})")
        return True

    # ── QUERY METHODS ──

    def get_task(self, task_id: str) -> Optional[TaskState]:
        """Single task query. Returns: TaskState or None."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[TaskState]:
        """Returns the list of all tasks."""
        return list(self._tasks.values())

    def get_active_tasks(self) -> List[TaskState]:
        """Returns tasks that have not yet been completed (running/pending)."""
        return [
            t for t in self._tasks.values()
            if not t.is_terminal
        ]

    def get_metrics(self) -> Dict[str, Any]:
        """Returns summary metrics.

        Returns:
            {
                "total": int,
                "completed": int,
                "failed": int,
                "running": int,
                "success_rate": float (0.0 - 1.0),
                "avg_duration_ms": float,
            }"""
        all_tasks = self.get_all_tasks()
        total = len(all_tasks)
        completed = sum(1 for t in all_tasks if t.status == "completed")
        failed = sum(1 for t in all_tasks if t.status == "failed")
        running = sum(1 for t in all_tasks if t.status == "running")

        terminal_durations = [
            t.elapsed_ms for t in all_tasks if t.is_terminal
        ]
        avg_duration = (
            sum(terminal_durations) / len(terminal_durations)
            if terminal_durations
            else 0.0
        )

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "success_rate": round(completed / max(1, total), 2),
            "avg_duration_ms": round(avg_duration, 1),
        }

    def clear(self) -> None:
        """Clears all task history. For testing and reset."""
        count = len(self._tasks)
        self._tasks.clear()
        logger.info(f"StateManager cleared: Task {count} deleted.")

    # ── INTERNAL ──

    def _can_transition(self, task: TaskState, target_status: str) -> bool:
        """Status checks whether the transition is valid."""
        valid_targets = _VALID_TRANSITIONS.get(task.status, set())
        if target_status not in valid_targets:
            logger.warning(
                f"Invalid transition: {task.id}"
                f"'{task.status}' → '{target_status}' "
                f"(izin verilen: {valid_targets})"
            )
            return False
        return True