"""
[V8.2] J.A.R.V.I.S. Task State Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Her görevin lifecycle'ını yöneten merkezi state deposu.

Sorumluluklar:
    - TaskState oluşturma ve güncelleme
    - Status transition kontrolü (pending → running → completed/failed)
    - Metrik sorgulama (tüm görevler, başarı oranı)

Tasarım Kararları:
    - In-memory dict-based store (SQLite/Redis overkill)
    - Thread-safe değil çünkü tek asyncio event loop'ta çalışıyor
    - TaskState immutable değil — engine doğrudan field güncelleyebilir
      (tool_history.append gibi) ama status transition'lar
      StateManager üzerinden yapılmalı (tutarlılık)

Edge Cases:
    - Aynı task_id ile create_task çağrılırsa → uyarı logla, üzerine yaz
    - Olmayan task_id ile fail/complete → KeyError yerine sessiz log
    - elapsed_ms hesabı: start_time None ise 0 döner
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("JARVIS.StateManager")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TASK STATE — Tekil Görev Durum Nesnesi
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class TaskState:
    """
    Tek bir görevin yaşam döngüsü verisi.

    Status Geçişleri:
        pending → running → completed
                         ↘ failed

    Attributes:
        id:            Benzersiz görev kimliği (uuid kısaltması)
        goal:          Kullanıcının orijinal isteği
        status:        Mevcut durum (pending/running/failed/completed)
        retries:       Kaç kez retry edildi
        last_error:    Son hata mesajı (None ise hata yok)
        tool_history:  Kullanılan araçların kaydı
        outputs:       Görev çıktıları
        start_time:    Görev başlangıç zamanı (monotonic)
        end_time:      Görev bitiş zamanı (monotonic)
        created_at:    Görev oluşturma zamanı (wall clock, loglar için)
        _step_results: Adımlar arası bağlam aktarımı için {TAG: metin} deposu
                       (repr'den gizlenir, sadece interpolasyon için kullanılır)
    """

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
        """
        Görev hâlâ işlenebilir durumda mı?

        plan_executor.execute_plan() her adım öncesi bunu kontrol eder;
        görev dışarıdan fail/complete yapılmışsa döngü kırılır.

        Returns:
            True  → pending veya running: adım yürütmeye devam et
            False → completed veya failed: döngüyü kır
        """
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
        
        # 🛡️ V8.2 FIX: GERÇEK DATA ÖNCELİKLİ OLMALI! (Eskiden 'speak' öncelikliydi)
        interpolation_text = (
            str(data.get("summary", ""))
            or str(data.get("result", ""))
            or str(data.get("content", ""))
            or result_dict.get("message", "")
            or result_dict.get("speak", "")
        )

        if tag and interpolation_text:
            if tag in self._step_results:
                # Aynı araç tekrar kullanıldıysa, eski veriyi silme, yanına ekle!
                self._step_results[tag] += f"\n\n--- EK SONUÇ ---\n{interpolation_text}"
            else:
                self._step_results[tag] = interpolation_text
            logger.debug(
                f"[StateManager] _step_results['{tag}'] güncellendi "
                f"({len(interpolation_text)} karakter)"
            )

    def get_results(self) -> dict:
        """
        executor._interpolate_argument'ın beklediği {TAG: metin} sözlüğünü döndürür.

        Kopya döndürülür: çağıran kod sözlüğü mutate etse bile iç depo korunur.

        Returns:
            Örnek: {"GOOGLE_SEARCH": "Messi Arjantin milli takımında...",
                    "WEB_OPEN": "Sayfa açıldı."}
        """
        return dict(self._step_results)

    # ── PROPERTIES ──────────────────────────────────────────────────────

    @property
    def elapsed_ms(self) -> int:
        """
        Görev süresini milisaniye cinsinden döndürür.

        Edge case: start_time henüz set edilmediyse → 0
        Edge case: end_time henüz yok (hala çalışıyor) → şu ana kadar geçen süre
        """
        if self.start_time is None:
            return 0
        end = self.end_time if self.end_time is not None else time.monotonic()
        return int((end - self.start_time) * 1000)

    @property
    def is_terminal(self) -> bool:
        """Görev terminal durumda mı (completed veya failed)?"""
        return self.status in ("completed", "failed")

    def __repr__(self) -> str:
        return (
            f"TaskState(id='{self.id}', goal='{self.goal[:40]}...', "
            f"status='{self.status}', retries={self.retries}, "
            f"elapsed={self.elapsed_ms}ms)"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STATE MANAGER — Merkezi Görev Deposu
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# Geçerli status transition'ları — bunun dışında geçiş yapılamaz
_VALID_TRANSITIONS: Dict[str, set] = {
    "pending":   {"running"},
    "running":   {"completed", "failed"},
    "completed": set(),       # Terminal — geçiş yok
    "failed":    {"pending"},  # Retry durumunda tekrar pending'e alınabilir
}


class StateManager:
    """
    Görev durumlarını yöneten in-memory store.

    Kullanım (engine.py ile uyumlu):
        sm = StateManager()
        task = sm.create_task(task_id="abc123", goal="Google'da arat")
        sm.start_task("abc123")
        sm.complete_task("abc123")  # veya sm.fail_task("abc123", "timeout")

        all_tasks = sm.get_all_tasks()
        metrics = sm.get_metrics()

    Thread Safety:
        Tek asyncio loop'ta çalıştığı için lock gerekmez.
        Eğer ileride multi-thread gerekirse asyncio.Lock eklenebilir.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskState] = {}

    # ── LIFECYCLE METHODS ──

    def create_task(self, task_id: str, goal: str) -> TaskState:
        """
        Yeni bir görev oluşturur ve 'running' durumuna alır.

        engine.py bunu çağırdıktan hemen sonra işleme başlıyor,
        bu yüzden create + start birleştirildi.
        """
        if task_id in self._tasks:
            logger.warning(
                f"Task '{task_id}' zaten mevcut, üzerine yazılıyor. "
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
            f"Task oluşturuldu ve başlatıldı: {task_id} → '{goal[:50]}'"
        )
        return task

    def complete_task(self, task_id: str) -> None:
        """Görevi başarıyla tamamlandı olarak işaretler."""
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"complete_task: '{task_id}' bulunamadı.")
            return

        if not self._can_transition(task, "completed"):
            return

        task.status = "completed"
        task.end_time = time.monotonic()

        logger.info(
            f"Task tamamlandı: {task_id} "
            f"(süre: {task.elapsed_ms}ms, "
            f"tools: {len(task.tool_history)})"
        )

    def fail_task(self, task_id: str, reason: str) -> None:
        """Görevi başarısız olarak işaretler."""
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"fail_task: '{task_id}' bulunamadı.")
            return

        if not self._can_transition(task, "failed"):
            return

        task.status = "failed"
        task.last_error = reason
        task.end_time = time.monotonic()

        logger.error(
            f"Task başarısız: {task_id} → {reason} "
            f"(süre: {task.elapsed_ms}ms)"
        )

    def retry_task(self, task_id: str) -> bool:
        """Başarısız görevi yeniden deneme için pending'e alır."""
        task = self._tasks.get(task_id)
        if task is None:
            logger.warning(f"retry_task: '{task_id}' bulunamadı.")
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
        """Tekil görev sorgulama. Returns: TaskState veya None."""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[TaskState]:
        """Tüm görevlerin listesini döndürür."""
        return list(self._tasks.values())

    def get_active_tasks(self) -> List[TaskState]:
        """Henüz tamamlanmamış (running/pending) görevleri döndürür."""
        return [
            t for t in self._tasks.values()
            if not t.is_terminal
        ]

    def get_metrics(self) -> Dict[str, Any]:
        """
        Özet metrikleri döndürür.

        Returns:
            {
                "total": int,
                "completed": int,
                "failed": int,
                "running": int,
                "success_rate": float (0.0 - 1.0),
                "avg_duration_ms": float,
            }
        """
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
        """Tüm görev geçmişini temizler. Test ve reset için."""
        count = len(self._tasks)
        self._tasks.clear()
        logger.info(f"StateManager temizlendi: {count} görev silindi.")

    # ── INTERNAL ──

    def _can_transition(self, task: TaskState, target_status: str) -> bool:
        """Status transition'ın geçerli olup olmadığını kontrol eder."""
        valid_targets = _VALID_TRANSITIONS.get(task.status, set())
        if target_status not in valid_targets:
            logger.warning(
                f"Geçersiz transition: {task.id} "
                f"'{task.status}' → '{target_status}' "
                f"(izin verilen: {valid_targets})"
            )
            return False
        return True