import asyncio
import logging
from typing import Callable, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("JARVIS.EventBus")

@dataclass
class JarvisEvent:
    name: str
    data: Any
    timestamp: datetime = None
    sender: str = "system"

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def get(self, key, default=None):
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return default

class EventBus:
    """
    J.A.R.V.I.S. Internal Reasoning Bus
    Asynchronous event distribution system for modular cognition.
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: List[JarvisEvent] = []
        self._max_history = 100

    def subscribe(self, event_name: str, callback: Callable):
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)
        logger.debug(f"Subscribed to {event_name}")

    def publish(self, event_name: str, data: Any, sender: str = "system"):
        """Alias for emit used by validation tests."""
        event = JarvisEvent(name=event_name, data=data, sender=sender)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if event_name in self._subscribers:
            for callback in self._subscribers[event_name]:
                if asyncio.iscoroutinefunction(callback):
                    if loop: loop.create_task(callback(event))
                else:
                    try: callback(event)
                    except Exception as e: logger.error(f"Sync callback error: {e}")

        if "*" in self._subscribers:
            for callback in self._subscribers["*"]:
                if asyncio.iscoroutinefunction(callback):
                    if loop: loop.create_task(callback(event))
                else:
                    try: callback(event)
                    except Exception as e: logger.error(f"Sync wildcard callback error: {e}")

    async def emit(self, event_name: str, data: Any, sender: str = "system"):
        event = JarvisEvent(name=event_name, data=data, sender=sender)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        logger.info(f"Event: {event_name} from {sender}")
        
        if event_name in self._subscribers:
            tasks = []
            for callback in self._subscribers[event_name]:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(callback(event))
                else:
                    # Protect Event Loop by dumping synchronous functions to Thread Pool
                    loop = asyncio.get_running_loop()
                    tasks.append(loop.run_in_executor(None, callback, event))
            
            if tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.error(f"EventBus Timeout: {event_name} dinleyicilerinden biri dondu!")
        
        # Also notify wildcard subscribers
        if "*" in self._subscribers:
            tasks = []
            for callback in self._subscribers["*"]:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(callback(event))
                else:
                    # Protect Event Loop by dumping synchronous functions to Thread Pool
                    loop = asyncio.get_running_loop()
                    tasks.append(loop.run_in_executor(None, callback, event))
            if tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.error("EventBus Timeout: Wildcard (*) dinleyicilerinden biri dondu!")

    def get_history(self, limit: int = 10) -> List[JarvisEvent]:
        return self._history[-limit:]
