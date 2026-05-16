"""
[V12.0] J.A.R.V.I.S. Proactive Attention Intelligence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Controls WHEN the agent should act proactively vs stay silent.
Workflow-aware, user-focus-estimating, urgency-scoring attention system.
"""
import time, logging, math
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger("JARVIS.Attention")


class AttentionScorer:
    """
    [V12.0] Proactive Attention & Notification Intelligence
    
    Decides when to interrupt, when to stay silent, and how proactive to be.
    Features:
    - Time-of-day awareness
    - User activity state tracking
    - Cooldown between notifications
    - Workflow disruption prevention
    - Urgency estimation for autonomous actions
    - Focus mode detection
    """
    def __init__(self):
        self.last_interaction = time.time()
        self.priority_threshold = 0.7
        self.recent_notifications: List[Dict[str, Any]] = []
        self._cooldown_seconds = 120
        self._max_notifications_per_hour = 10
        self._notification_count_hour = 0
        self._hour_reset_time = time.time()

        # Task tracking
        self._stuck_task_threshold = 300
        self._last_task_activity = time.time()
        self._error_count_window: List[float] = []

        # Focus tracking
        self._focus_start: float = 0.0
        self._focus_app: str = ""
        self._focus_threshold = 120  # 2 min same app = focus mode

    def should_interrupt(self, event_type: str, priority: float) -> bool:
        """Decides if an event warrants user interruption."""
        now = time.time()

        # Reset hourly counter
        if now - self._hour_reset_time > 3600:
            self._notification_count_hour = 0
            self._hour_reset_time = now

        # Budget check
        if self._notification_count_hour >= self._max_notifications_per_hour:
            return False

        # Cooldown (only critical bypasses)
        if self.recent_notifications:
            last = self.recent_notifications[-1].get("time", 0)
            if now - last < self._cooldown_seconds and priority < 0.95:
                return False

        # Dynamic threshold
        threshold = self._calculate_dynamic_threshold(now)

        if priority >= threshold:
            self.recent_notifications.append({"type": event_type, "time": now, "priority": priority})
            if len(self.recent_notifications) > 20:
                self.recent_notifications = self.recent_notifications[-20:]
            self._notification_count_hour += 1
            return True
        return False

    def should_autonomous_act(self, action_type: str, urgency: float) -> bool:
        """
        Decides if the autonomous loop should take an action.
        More conservative than should_interrupt — autonomous actions
        need higher urgency and stricter conditions.
        """
        now = time.time()
        idle_time = now - self.last_interaction

        # Never act autonomously during active user interaction
        if idle_time < 30:
            return urgency > 0.95  # Only critical

        # During focus mode, be very conservative
        if self.is_user_focused():
            return urgency > 0.9

        # User idle = more freedom to act
        if idle_time > 300:  # 5+ min idle
            return urgency > 0.4
        elif idle_time > 60:
            return urgency > 0.6

        return urgency > 0.75

    def is_user_focused(self) -> bool:
        """Detects if user is in a focused work session."""
        return (time.time() - self._focus_start) > self._focus_threshold and self._focus_app

    def update_focus_tracking(self, current_app: str):
        """Updates focus mode detection based on active app."""
        if current_app == self._focus_app:
            return  # Still focused on same app
        # App changed — reset focus timer
        self._focus_app = current_app
        self._focus_start = time.time()

    def _calculate_dynamic_threshold(self, now: float) -> float:
        threshold = self.priority_threshold
        idle = now - self.last_interaction

        # Activity-based adjustment
        if idle < 60: threshold += 0.25      # Very active
        elif idle < 300: threshold += 0.15   # Active
        elif idle > 1800: threshold -= 0.1   # Long idle

        # Time-of-day
        hour = datetime.now().hour
        if hour < 8 or hour >= 23: threshold += 0.3  # Night
        elif hour >= 22: threshold += 0.15            # Late evening

        # Focus mode
        if self.is_user_focused(): threshold += 0.2

        return threshold

    def record_interaction(self):
        self.last_interaction = time.time()
        self._last_task_activity = time.time()

    def record_task_progress(self):
        self._last_task_activity = time.time()

    def record_error(self):
        now = time.time()
        self._error_count_window.append(now)
        self._error_count_window = [t for t in self._error_count_window if t > now - 600]

    def detect_stuck_task(self) -> bool:
        return (time.time() - self._last_task_activity) > self._stuck_task_threshold

    def detect_error_anomaly(self, threshold: int = 5) -> bool:
        recent = sum(1 for t in self._error_count_window if t > time.time() - 600)
        return recent >= threshold

    def get_proactivity_score(self) -> float:
        """0.0 = silent, 1.0 = very proactive. Used by autonomous loop."""
        hour = datetime.now().hour
        if hour < 8 or hour >= 23: base = 0.1
        elif hour < 12: base = 0.7
        elif hour < 18: base = 0.8
        elif hour < 22: base = 0.5
        else: base = 0.3

        idle = time.time() - self.last_interaction
        if idle > 1800: base *= 0.5
        if self.is_user_focused(): base *= 0.6
        if self.detect_error_anomaly(): base = min(1.0, base + 0.3)
        if self.detect_stuck_task(): base = min(1.0, base + 0.2)
        return round(base, 2)

    def estimate_action_urgency(self, goal_priority: int, goal_staleness_hours: float,
                                 has_deadline: bool = False) -> float:
        """Estimates urgency for autonomous goal pursuit."""
        urgency = 0.3
        # Priority boost (1=highest → more urgent)
        urgency += max(0, (5 - goal_priority) * 0.1)
        # Staleness boost
        urgency += min(0.3, goal_staleness_hours * 0.05)
        # Deadline boost
        if has_deadline: urgency += 0.2
        return min(1.0, urgency)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "last_interaction_ago": round(time.time() - self.last_interaction, 1),
            "notifications_this_hour": self._notification_count_hour,
            "proactivity_score": self.get_proactivity_score(),
            "stuck_detected": self.detect_stuck_task(),
            "error_anomaly": self.detect_error_anomaly(),
            "user_focused": self.is_user_focused(),
            "focus_app": self._focus_app,
            "focus_duration": round(time.time() - self._focus_start, 0) if self._focus_app else 0,
        }
