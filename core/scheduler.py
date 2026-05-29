"""[V9.0] J.A.R.V.I.S. Proactive Scheduler
━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━
Let the system not only wait for commands, but also like a morning briefing. 
enables it to carry out proactive tasks."""

import asyncio
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("JARVIS.Scheduler")

@dataclass
class ScheduledTask:
    hour:     int
    minute:   int
    action:   str
    repeat:   bool = True
    last_run: Optional[object] = field(default=None, repr=False)

class JarvisScheduler:
    def __init__(self, engine):
        self.engine = engine
        self._running = False
        self._tasks: list[ScheduledTask] = []

    def add_daily(self, hour: int, minute: int, action: str):
        self._tasks.append(ScheduledTask(hour=hour, minute=minute, action=action))
        logger.info(f"[SCHEDULER] Quest added: {hour:02d}:{minute:02d} -> {action[:40]}")

    async def run(self):
        self._running = True
        logger.info("[SCHEDULER] Timer cycle started.")

        # VARSAYILAN: Sabah Brifingi (Her sabah 08:00)
        self.add_daily(8, 0, "Have a morning briefing: Say good morning to Sir, tell him today's date, and summarize yesterday's important events from memory.")

        while self._running:
            try:
                now = datetime.now()
                for task in self._tasks:
                    if (task.hour == now.hour and task.minute == now.minute and task.last_run != now.date()):
                        task.last_run = now.date()
                        logger.info(f"[SCHEDULER] Tetikleniyor: {task.action[:50]}")
                        # Submit the task for processing by the main engine
                        asyncio.create_task(self.engine.process_input(task.action))
                
                sleep_seconds = 60 - datetime.now().second
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SCHEDULER] Error: {e}")
                sleep_seconds = 60 - datetime.now().second
                await asyncio.sleep(sleep_seconds)

    def stop(self):
        self._running = False