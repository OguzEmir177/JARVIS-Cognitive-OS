"""
[V8.0] J.A.R.V.I.S. Async Task Queue
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
asyncio.PriorityQueue üzerine kurulu görev kuyruğu.

Sorumluluklar:
    - Öncelikli görev sıralaması
    - Timeout destekli put/get
    - CancelledError yönetimi
    - Toplu iptal (cancel_all)

Tasarım Kararları:
    Neden asyncio.PriorityQueue?
    → threading.Queue yerine asyncio-native çözüm.
    → Priority desteği: acil görevler (shutdown, error recovery)
      normal görevlerin önüne geçebilir.
    → CancelledError doğal olarak asyncio ile çalışır.

    Neden wrapper class?
    → Raw PriorityQueue'ya timeout, cancel_all, metrics gibi
      özellikler eklemek için.
    → İleride Redis/RabbitMQ'ya geçiş noktası (genişletilebilirlik).

Edge Cases:
    - Queue full iken put → asyncio.QueueFull (maxsize ile)
    - Get sırasında cancel → CancelledError propagate
    - cancel_all sırasında yeni put → queue boşaltıldıktan sonra kabul
    - Aynı priority'de 2 görev → FIFO (insertion order)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

logger = logging.getLogger("JARVIS.TaskQueue")


class TaskPriority(IntEnum):
    """
    Görev öncelik seviyeleri.
    Düşük sayı = yüksek öncelik (PriorityQueue convention).

    Kullanım:
        CRITICAL → shutdown, error recovery
        HIGH     → kullanıcının aktif beklediği görevler
        NORMAL   → standart görevler
        LOW      → arka plan görevleri (reflection, memory write)
    """
    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 100


@dataclass(order=True)
class QueueItem:
    """
    PriorityQueue'ya konulacak sarmalayıcı.

    PriorityQueue karşılaştırma için __lt__ kullanır.
    @dataclass(order=True) ile priority alanına göre sıralama yapılır.
    'payload' karşılaştırma dışı bırakılır (compare=False).

    Edge Case:
        Aynı priority'de 2 item → sequence_number ile FIFO garantisi.
        Bu olmadan, payload türleri karşılaştırılamaz ise TypeError fırlar.
    """
    priority: int
    sequence_number: int = field(compare=True)
    payload: Any = field(compare=False, default=None)


class TaskQueue:
    """
    AsyncIO tabanlı öncelikli görev kuyruğu.

    engine.py ile uyumlu API:
        queue = TaskQueue(maxsize=50)
        await queue.put(payload, priority=TaskPriority.NORMAL)
        item = await queue.get(timeout=10.0)
        await queue.cancel_all()

    Attributes:
        _queue:     asyncio.PriorityQueue instance
        _counter:   Monoton artan sequence numarası (FIFO tiebreaker)
        _cancelled: Global cancel flag (cancel_all sonrası yeni get engellemek için)
    """

    def __init__(self, maxsize: int = 50) -> None:
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=maxsize
        )
        self._counter: int = 0
        self._cancelled: bool = False

        logger.info(f"TaskQueue oluşturuldu (maxsize={maxsize})")

    # ── PUT ──

    async def put(
        self,
        payload: Any,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: Optional[float] = None,
    ) -> None:
        """
        Kuyruğa görev ekler.

        Args:
            payload:  Görev verisi (task_id, callable, dict vb.)
            priority: Öncelik seviyesi (düşük sayı = yüksek öncelik)
            timeout:  Kuyruk doluysa maksimum bekleme süresi (None = sonsuz)

        Raises:
            asyncio.QueueFull: Timeout doldu ve kuyruk hala dolu
            RuntimeError:      Queue cancel edilmiş durumda

        Edge Case:
            cancel_all() çağrıldıktan sonra put → RuntimeError.
            Rationale: Shutdown sırasında yeni görev kabul etmemeli.
        """
        if self._cancelled:
            raise RuntimeError(
                "TaskQueue iptal edilmiş durumda, yeni görev kabul edilemiyor."
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
        """
        Kuyruktan en yüksek öncelikli görevi alır.

        Args:
            timeout: Kuyruk boşsa maksimum bekleme süresi (None = sonsuz)

        Returns:
            Payload nesnesi (QueueItem sarmalayıcısı soyulur)

        Raises:
            asyncio.TimeoutError: Timeout doldu, kuyruk hala boş
            asyncio.CancelledError: Task iptal edildi (propagate edilir)

        Edge Case:
            CancelledError → engine tarafında yakalanır, task failed olur.
            Bu queue'nun sorumluluğu değil, sadece propagate eder.
        """
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
            logger.warning("Queue get iptal edildi (CancelledError)")
            raise

    # ── CANCEL ALL ──

    async def cancel_all(self) -> int:
        """
        Kuyruktaki tüm bekleyen görevleri boşaltır.
        engine.py shutdown sırasında çağırır.

        Returns:
            İptal edilen görev sayısı

        Edge Case:
            Boş kuyrukta çağrılabilir → 0 döner, hata yok.
            cancel_all sonrası yeni put → RuntimeError.
        """
        self._cancelled = True
        cancelled_count = 0

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                cancelled_count += 1
            except asyncio.QueueEmpty:
                break

        logger.info(f"Queue cancel_all: {cancelled_count} görev iptal edildi.")
        return cancelled_count

    # ── RESET ──

    def reset(self) -> None:
        """
        Queue'yu yeniden kullanılabilir hale getirir.
        Test ve recovery senaryoları için.

        Edge Case:
            Queue'da hala item varsa → önce cancel_all çağrılmalı.
            Bu metod sadece flag'i sıfırlar, queue'yu boşaltmaz.
        """
        self._cancelled = False
        self._counter = 0
        logger.info("Queue resetlendi.")

    # ── PROPERTIES ──

    @property
    def size(self) -> int:
        """Kuyruktaki mevcut görev sayısı."""
        return self._queue.qsize()

    @property
    def is_empty(self) -> bool:
        """Kuyruk boş mu?"""
        return self._queue.empty()

    @property
    def is_full(self) -> bool:
        """Kuyruk dolu mu?"""
        return self._queue.full()

    @property
    def is_cancelled(self) -> bool:
        """Queue iptal edilmiş durumda mı?"""
        return self._cancelled
