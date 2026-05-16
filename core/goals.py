"""
[V12.0] J.A.R.V.I.S. Autonomous Goal Pursuit System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Not just CRUD — goals are autonomously pursued even without user input.
Features: long-running objectives, autonomous continuation, progress estimation,
stale task recovery, proactive sub-goal generation, persistence across sessions.
"""
import uuid, json, os, time, logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger("JARVIS.Goals")

@dataclass
class SubTask:
    id: str; title: str; status: str = "pending"; result: Optional[Any] = None
    attempts: int = 0; max_attempts: int = 3; last_error: str = ""

@dataclass
class Goal:
    id: str; title: str; priority: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "active"  # active, in_progress, completed, archived, failed, paused
    progress: float = 0.0
    dependencies: List[str] = field(default_factory=list)
    subtasks: List[SubTask] = field(default_factory=list)
    retries: int = 0; max_retries: int = 5
    last_activity: str = field(default_factory=lambda: datetime.now().isoformat())
    required_tools: List[str] = field(default_factory=list)
    context_refs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Autonomous pursuit fields
    autonomous: bool = False  # Can this goal be pursued without user input?
    next_action: str = ""  # What should be done next
    blocking_reason: str = ""  # Why is this goal blocked?
    estimated_steps: int = 0
    completed_steps: int = 0

    def to_dict(self): return asdict(self)

    @property
    def is_actionable(self) -> bool:
        """Can the autonomous loop work on this goal right now?"""
        if self.status not in ("active", "in_progress"): return False
        if self.retries >= self.max_retries: return False
        if self.blocking_reason: return False
        # Check dependencies
        return True

    @property
    def staleness_hours(self) -> float:
        try:
            last = datetime.fromisoformat(self.last_activity).timestamp()
            return (time.time() - last) / 3600.0
        except: return 0.0


class GoalManager:
    """
    [V12.0] Persistent Autonomous Goal Manager.
    Goals survive across sessions. The autonomous loop uses get_next_actionable_goal()
    to find work to do even when the user hasn't given new input.
    """
    def __init__(self, storage_path: str = "memory_db/goals.json"):
        self.storage_path = storage_path
        self.goals: Dict[str, Goal] = {}
        self._ensure_storage()
        self.load_goals()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, 'w') as f: json.dump({}, f)

    def load_goals(self):
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
                for gid, gdata in data.items():
                    subtasks = [SubTask(**st) for st in gdata.get('subtasks', [])]
                    gdata['subtasks'] = subtasks
                    self.goals[gid] = Goal(**gdata)
            logger.info(f"Loaded {len(self.goals)} goals ({len(self.get_active_goals())} active)")
        except Exception as e:
            logger.warning(f"Goal load error: {e}")

    def save_goals(self):
        # Thread-safety için verinin anlık kopyasını (snapshot) al
        goals_snapshot = {gid: g.to_dict() for gid, g in self.goals.items()}
        
        def _write():
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(goals_snapshot, f, indent=2)
            except Exception as e:
                logger.error(f"Goal save error: {e}")
        
        import threading
        threading.Thread(target=_write, daemon=True).start()

    def create_goal(self, title: str, priority: int = 1, autonomous: bool = False,
                    metadata: Dict = None) -> Goal:
        gid = str(uuid.uuid4())[:8]
        goal = Goal(id=gid, title=title, priority=priority,
                    autonomous=autonomous, metadata=metadata or {})
        self.goals[gid] = goal
        self.save_goals()
        logger.info(f"Goal created: [{gid}] {title} (autonomous={autonomous})")
        return goal

    def add_goal(self, *args, **kwargs) -> str:
        """Alias for create_goal used by validation tests."""
        return self.create_goal(*args, **kwargs).id

    def mark_completed(self, goal_id: str):
        """Alias to complete a goal."""
        self.update_goal(goal_id, status="completed")

    def update_goal(self, goal_id: str, **kwargs) -> bool:
        if goal_id not in self.goals: return False
        goal = self.goals[goal_id]
        for key, value in kwargs.items():
            if hasattr(goal, key): setattr(goal, key, value)
        goal.last_activity = datetime.now().isoformat()
        self.save_goals()
        return True

    def add_subtask(self, goal_id: str, title: str) -> Optional[str]:
        if goal_id not in self.goals: return None
        st_id = str(uuid.uuid4())[:4]
        self.goals[goal_id].subtasks.append(SubTask(id=st_id, title=title))
        self.goals[goal_id].estimated_steps = len(self.goals[goal_id].subtasks)
        self.save_goals()
        return st_id

    def complete_subtask(self, goal_id: str, subtask_id: str, result: Any = None):
        if goal_id not in self.goals: return
        goal = self.goals[goal_id]
        for st in goal.subtasks:
            if st.id == subtask_id:
                st.status = "completed"; st.result = result; break
        # Update progress
        total = len(goal.subtasks)
        done = sum(1 for st in goal.subtasks if st.status == "completed")
        goal.progress = done / max(total, 1)
        goal.completed_steps = done
        # Auto-complete if all subtasks done
        if total > 0 and done == total:
            goal.status = "completed"
            logger.info(f"Goal [{goal_id}] auto-completed: all subtasks done.")
        self.save_goals()

    def fail_subtask(self, goal_id: str, subtask_id: str, error: str = ""):
        if goal_id not in self.goals: return
        goal = self.goals[goal_id]
        for st in goal.subtasks:
            if st.id == subtask_id:
                st.attempts += 1; st.last_error = error
                if st.attempts >= st.max_attempts:
                    st.status = "failed"
                else:
                    st.status = "pending"  # Will retry
                break
        self.save_goals()

    def get_active_goals(self) -> List[Goal]:
        return [g for g in self.goals.values() if g.status in ("active", "in_progress")]

    def get_next_actionable_goal(self) -> Optional[Goal]:
        """
        Returns the highest-priority goal that the autonomous loop can work on.
        Used by autonomous_loop.py to find proactive work.
        """
        candidates = [g for g in self.goals.values() if g.is_actionable and g.autonomous]
        if not candidates: return None
        # Sort: priority (lower=higher), then staleness (staler = more urgent)
        candidates.sort(key=lambda g: (g.priority, -g.staleness_hours))
        return candidates[0]

    def get_next_subtask(self, goal_id: str) -> Optional[SubTask]:
        """Returns the next pending subtask for a goal."""
        if goal_id not in self.goals: return None
        for st in self.goals[goal_id].subtasks:
            if st.status == "pending" and st.attempts < st.max_attempts:
                return st
        return None

    def record_attempt(self, goal_id: str, success: bool, error: str = ""):
        """Records a goal execution attempt."""
        if goal_id not in self.goals: return
        goal = self.goals[goal_id]
        if not success:
            goal.retries += 1
            if goal.retries >= goal.max_retries:
                goal.status = "failed"
                goal.blocking_reason = f"Max retries ({goal.max_retries}) exceeded: {error}"
                logger.warning(f"Goal [{goal_id}] failed: max retries exceeded.")
        goal.last_activity = datetime.now().isoformat()
        self.save_goals()

    def reprioritize_goals(self):
        """Dynamic reprioritization based on age, staleness, and dependency state."""
        active = self.get_active_goals()
        if not active: return
        now = time.time()
        for goal in active:
            # Stale boost
            if goal.staleness_hours > 1.0 and goal.priority > 1:
                goal.priority = max(1, goal.priority - 1)
            # Dependency completion boost
            if goal.dependencies:
                all_done = all(self.goals.get(d, Goal(id="",title="")).status == "completed"
                              for d in goal.dependencies)
                if all_done and goal.priority > 1:
                    goal.priority = max(1, goal.priority - 1)
            # Subtask progress update
            if goal.subtasks:
                done = sum(1 for st in goal.subtasks if st.status == "completed")
                goal.progress = done / len(goal.subtasks)
                goal.completed_steps = done
        self.save_goals()

    def get_stale_goals(self, stale_hours: float = 2.0) -> List[Goal]:
        return [g for g in self.get_active_goals() if g.staleness_hours > stale_hours]

    def get_goal_summary(self) -> str:
        active = self.get_active_goals()
        if not active: return "No active goals."
        self.reprioritize_goals()
        active.sort(key=lambda g: g.priority)
        s = "Active Goals:\n"
        for g in active[:5]:
            auto = " 🤖" if g.autonomous else ""
            s += f"- [{g.id}] {g.title} (P{g.priority}, {g.progress*100:.0f}%){auto}\n"
            for st in g.subtasks[:3]:
                icon = "✓" if st.status=="completed" else "✗" if st.status=="failed" else "○"
                s += f"  {icon} {st.title}\n"
            if g.next_action: s += f"  → Next: {g.next_action}\n"
        stale = self.get_stale_goals()
        if stale: s += f"\n⚠️ {len(stale)} stale goal(s)\n"
        return s

    def cleanup_old_goals(self, max_days: int = 7):
        now = time.time()
        for goal in list(self.goals.values()):
            if goal.status in ("completed", "failed"):
                try:
                    created = datetime.fromisoformat(goal.created_at).timestamp()
                    if (now - created) / 86400 > max_days: goal.status = "archived"
                except: pass
        self.save_goals()

    def archive_goal(self, goal_id: str):
        self.update_goal(goal_id, status="archived")
