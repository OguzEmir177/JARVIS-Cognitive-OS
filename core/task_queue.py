"""[V8.0] J.A.R.V.I.S. Async Task Queue
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task queue built on asyncio.PriorityQueue.

Responsibilities:
    - Priority task ordering
    - Put/get with timeout support
    - CancelledError management
    - Bulk cancellation (cancel_all)

Design Decisions:
    Why asyncio.PriorityQueue?
    → asyncio-native solution instead of threading.Queue.
    → Priority support: urgent tasks (shutdown, error recovery)
      can get in the way of normal tasks.
    → CancelledError works natively with asyncio.

    Why wrapper class?
    → Add timeout, cancel_all, metrics to Raw PriorityQueue
      to add features.
    → Future migration point to Redis/RabbitMQ (extensibility).

Edge Cases:
    - When the queue is full put → asyncio.QueueFull (with maxsize)
    - Cancel → CancelledError propagate during Get
    - new put during cancel_all → accepted after queue is emptied
    - 2 tasks in the same priority → FIFO (insertion order)"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

logger = logging.getLogger("JARVIS.TaskQueue")


class TaskPriority(IntEnum):
    """Task priority levels.
    Low number = high priority (PriorityQueue convention).

    Usage:
        CRITICAL → shutdown, error recovery
        HIGH → tasks that the user is actively waiting for
        NORMAL → standard quests
        LOW → background tasks (reflection, memory write)"""
    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 100


@dataclass(order=True)
class QueueItem:
    """Wrapper to put into PriorityQueue.

    PriorityQueue uses __lt__ for comparison.
    Sorting is done according to the priority field with @dataclass(order=True).
    'payload' is excluded from comparison (compare=False).

    Edge Case:
        FIFO guarantee with 2 items → sequence_number in the same priority.
        Without this, TypeError will be thrown if payload types cannot be compared."""
    priority: int
    sequence_number: int = field(compare=True)
    payload: Any = field(compare=False, default=None)


class TaskQueue:
    """AsyncIO based prioritized task queue.

    API compatible with engine.py:
        queue = TaskQueue(maxsize=50)
        await queue.put(payload, priority=TaskPriority.NORMAL)
        item = await queue.get(timeout=10.0)
        await queue.cancel_all()

    Attributes:
        _queue: asyncio.PriorityQueue instance
        _counter: Monotonically increasing sequence number (FIFO tiebreaker)
        _cancelled: Global cancel flag (to prevent new gets after cancel_all)"""

    def __init__(self, maxsize: int = 50) -> None:
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=maxsize
        )
        self._counter: int = 0
        self._cancelled: bool = False

        logger.info(f"TaskQueue created (maxsize={maxsize})")

    # ── PUT ──

    async def put(
        self,
        payload: Any,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: Optional[float] = None,
    ) -> None:
        """Adds a task to the queue.

        Args:
            payload: Task data (task_id, callable, dict etc.)
            priority: Priority level (low number = high priority)
            timeout: Maximum waiting time if the queue is full (None = infinite)

        Raises:
            asyncio.QueueFull: Timeout has expired and the queue is still full
            RuntimeError: Queue has been canceled

        Edge Case:
            put → RuntimeError after cancel_all() is called.
            Rationale: Should not accept new missions during shutdown."""
        if self._cancelled:
            raise RuntimeError(
                "TaskQueue is canceled, new task cannot be accepted."
            )

        item = QueueItem(
            priority=int(priority),
            sequence_number=self._counter,
            payload=payload,
        )
        self._counter += 1

        if timeout is not None:
            try:
                await asyncio.wait_for(
                    self._queue.put(item), timeout=timeout
                )
            except asyncio.TimeoutError:
                raise asyncio.QueueFull(
                    f"Queue full, timeout after {timeout}s"
                )
        else:
            await self._queue.put(item)

        logger.debug(
            f"Queue put: priority={priority.name}, "
            f"seq={item.sequence_number}, "
            f"qsize={self._queue.qsize()}"
        )

    # ── GET ──

    async def get(self, timeout: Optional[float] = None) -> Any:
        """Retrieves the highest priority task from the queue.

        Args:
            timeout: Maximum waiting time if the queue is empty (None = infinite)

        Returns:
            Payload object (QueueItem wrapper stripped)

        Raises:
            asyncio.TimeoutError: Timeout expired, queue still empty
            asyncio.CancelledError: Task has been canceled (propagate)

        Edge Case:
            CancelledError → is caught by the engine and becomes task failed.
            This is not the queue's responsibility, it just propagates it."""
        try:
            if timeout is not None:
                item: QueueItem = await asyncio.wait_for(
                    self._queue.get(), timeout=timeout
                )
            else:
                item = await self._queue.get()

            self._queue.task_done()

            logger.debug(
                f"Queue get: priority={item.priority}, "
                f"seq={item.sequence_number}, "
                f"qsize={self._queue.qsize()}"
            )
            return item.payload

        except asyncio.CancelledError:
            logger.warning("Queue get canceled (CancelledError)")
            raise

    # ── CANCEL ALL ──

    async def cancel_all(self) -> int:
        """Clears all pending tasks from the queue.
        engine.py calls during shutdown.

        Returns:
            Number of canceled tasks

        Edge Case:
            Callable on empty queue → returns 0, no errors.
            new put → RuntimeError after cancel_all."""
        self._cancelled = True
        cancelled_count = 0

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                cancelled_count += 1
            except asyncio.QueueEmpty:
                break

        logger.info(f"Queue cancel_all: Quest {cancelled_count} has been cancelled.")
        return cancelled_count

    # ── RESET ──

    def reset(self) -> None:
        """Makes the queue reusable.
        For test and recovery scenarios.

        Edge Case:
            If there is still an item in the queue → cancel_all should be called first.
            This method only resets the flag, it does not empty the queue."""
        self._cancelled = False
        self._counter = 0
        logger.info("Queue resetlendi.")

    # ── PROPERTIES ──

    @property
    def size(self) -> int:
        """The current number of tasks in the queue."""
        return self._queue.qsize()

    @property
    def is_empty(self) -> bool:
        """Is the queue empty?"""
        return self._queue.empty()

    @property
    def is_full(self) -> bool:
        """Kuyruk dolu mu?"""
        return self._queue.full()

    @property
    def is_cancelled(self) -> bool:
        """Is the queue canceled?"""
        return self._cancelled
