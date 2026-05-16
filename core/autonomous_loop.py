"""
[V12.0] J.A.R.V.I.S. True Persistent Cognition Loop
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE core of the cognitive OS. This loop runs perpetually:

    PERCEIVE → UPDATE WORLD MODEL → THINK → PRIORITIZE GOALS
    → PLAN → EXECUTE → OBSERVE RESULTS → REFLECT
    → REPLAN → MEMORY CONSOLIDATION → CONTINUE

It does NOT stop after a task completes.
It is NOT triggered only by user input.
It is the living cognitive heartbeat of J.A.R.V.I.S.
"""
import asyncio, logging, time, traceback
from typing import Dict, Any, Optional

logger = logging.getLogger("JARVIS.CognitionLoop")


class AutonomousCognitionLoop:
    """
    [V12.0] Perpetual Cognitive Loop
    
    Runs in the background as an async task. Each cycle:
    1. PERCEIVE — Get situation assessment from world model
    2. THINK — Evaluate what needs attention
    3. PRIORITIZE — Select next goal/action
    4. ACT — Execute if appropriate (respects attention gating)
    5. REFLECT — Evaluate outcome
    6. CONSOLIDATE — Memory maintenance during idle
    
    Adaptive frequency: fast when active, slow when idle.
    Respects user focus — won't interrupt unnecessarily.
    """

    def __init__(self, cognitive_core, engine):
        self.core = cognitive_core
        self.engine = engine
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Timing
        self._min_cycle_ms = 2000     # Minimum 2s between cycles
        self._max_cycle_ms = 30000    # Maximum 30s between cycles (deep idle)
        self._current_cycle_ms = 5000 # Start at 5s
        self._last_cycle_time = 0.0

        # Cognition state
        self._cycles_count = 0
        self._last_autonomous_action = 0.0
        self._autonomous_cooldown = 60.0  # Min 60s between autonomous actions
        self._idle_consolidation_interval = 300.0  # Consolidate memory every 5 min idle
        self._last_consolidation = time.time()

        # Interruption handling
        self._interrupted = False
        self._interrupt_reason = ""

    async def start(self):
        """Starts the perpetual cognition loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._cognition_loop())
        logger.info("═══ AUTONOMOUS COGNITION LOOP STARTED ═══")

    def stop(self):
        """Gracefully stops the cognition loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("═══ AUTONOMOUS COGNITION LOOP STOPPED ═══")

    def interrupt(self, reason: str = "user_input"):
        """
        Interrupts the current cycle (e.g., user gave new input).
        The loop will reset and adapt to the new situation.
        """
        self._interrupted = True
        self._interrupt_reason = reason
        # Speed up next cycle
        self._current_cycle_ms = self._min_cycle_ms

    async def _cognition_loop(self):
        """The perpetual cognition heartbeat."""
        while self._running:
            cycle_start = time.time()
            self._cycles_count += 1

            try:
                # ═══════════════════════════════════════════
                #  PHASE 1: PERCEIVE
                # ═══════════════════════════════════════════
                situation = self._perceive()

                # ═══════════════════════════════════════════
                #  PHASE 2: THINK — What needs attention?
                # ═══════════════════════════════════════════
                decisions = self._think(situation)

                # ═══════════════════════════════════════════
                #  PHASE 3: ACT — Execute if appropriate
                # ═══════════════════════════════════════════
                if decisions.get("should_act"):
                    await self._act(decisions)

                # ═══════════════════════════════════════════
                #  PHASE 4: REFLECT — Post-action analysis
                # ═══════════════════════════════════════════
                if decisions.get("action_taken"):
                    await self._reflect(decisions)

                # ═══════════════════════════════════════════
                #  PHASE 5: CONSOLIDATE — Memory maintenance
                # ═══════════════════════════════════════════
                if situation.get("user_state") in ("idle", "away"):
                    await self._maybe_consolidate()

                # ═══════════════════════════════════════════
                #  PHASE 6: ADAPT FREQUENCY
                # ═══════════════════════════════════════════
                self._adapt_cycle_frequency(situation)

                # Handle interruption flag
                if self._interrupted:
                    self._interrupted = False
                    self._interrupt_reason = ""
                    self._current_cycle_ms = self._min_cycle_ms

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cognition cycle error: {e}")
                logger.debug(traceback.format_exc())
                self._current_cycle_ms = min(self._max_cycle_ms,
                                              self._current_cycle_ms * 2)

            # Log cycle telemetry periodically
            if self._cycles_count % 50 == 0:
                self._log_telemetry(situation if 'situation' in dir() else {})

            # Sleep until next cycle
            elapsed = (time.time() - cycle_start) * 1000
            sleep_ms = max(500, self._current_cycle_ms - elapsed)
            await asyncio.sleep(sleep_ms / 1000.0)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PERCEIVE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _perceive(self) -> Dict[str, Any]:
        """[V13.0] Gathers deep semantic situation assessment."""
        # 1. Environment Graph Assessment
        situation = self.core.world_state.get_situation_assessment()
        
        # 2. Workflow Inference
        wf_state = self.core.workflow_engine.get_state_summary()
        situation.update(wf_state)
        
        # 3. Active Hypotheses
        top_hypotheses = self.core.hypothesis_engine.get_top_hypotheses(limit=2)
        situation["hypotheses"] = [h.description for h in top_hypotheses]
        
        # 4. Standard Metrics
        situation["proactivity"] = self.core.attention.get_proactivity_score()
        situation["active_goals"] = len(self.core.goal_manager.get_active_goals())
        situation["stale_goals"] = len(self.core.goal_manager.get_stale_goals())

        # Update attention focus tracking
        app = situation.get("active_app", "")
        if app:
            self.core.attention.update_focus_tracking(app)
            
            # Workflow Transition Observation
            # Inform workflow engine of the context transition
            if hasattr(self, '_last_app') and self._last_app != app:
                self.core.workflow_engine.observe_transition(
                    from_node=self._last_app, 
                    to_node=app, 
                    duration=time.time() - getattr(self, '_app_start_time', time.time()),
                    context_overlap=0.5 # Simplified
                )
                self._app_start_time = time.time()
            self._last_app = app

        return situation

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  THINK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _think(self, situation: Dict[str, Any]) -> Dict[str, Any]:
        """
        [V13.0] Deep Semantic Reasoning Phase.
        Evaluates workflow, hypotheses, prediction, and goals.
        """
        decisions = {
            "should_act": False,
            "action_type": None,
            "action_target": None,
            "action_taken": False,
            "urgency": 0.0,
            "reasoning": "",
        }

        now = time.time()
        user_state = situation.get("user_state", "unknown")
        
        # Apply Self-Model Calibration to Confidence
        confidence_mod = self.core.self_model.get_confidence_modifier("workflow_inference")

        # ── CHECK 1: Predictive Cognition & Workflow Continuation ──
        predicted_phase = situation.get("prediction", "")
        top_workflow = situation.get("top_workflow")
        wf_confidence = situation.get("top_confidence", 0.0) * confidence_mod
        
        if top_workflow and predicted_phase and wf_confidence > 0.8:
            # We highly confidently predict the user's next workflow phase
            urgency = self.core.attention.estimate_action_urgency(priority=2, goal_staleness_hours=0)
            if self.core.attention.should_autonomous_act("predictive_assistance", urgency):
                if now - self._last_autonomous_action > self._autonomous_cooldown:
                    decisions["should_act"] = True
                    decisions["action_type"] = "predictive_assistance"
                    decisions["action_target"] = f"Prepare {predicted_phase} for {top_workflow}"
                    decisions["urgency"] = urgency
                    decisions["reasoning"] = f"High confidence ({wf_confidence:.2f}) predictive workflow continuation: {predicted_phase}"
                    return decisions # Fast exit on high confidence prediction

        # ── CHECK 2: Hypothesis-Driven Action ──
        if situation.get("hypotheses") and wf_confidence > 0.6:
            # Maybe there's a strong hypothesis about a problem
            top_hyp = situation["hypotheses"][0]
            if "issue" in top_hyp.lower() or "error" in top_hyp.lower():
                decisions["should_act"] = True
                decisions["action_type"] = "hypothesis_resolution"
                decisions["action_target"] = top_hyp
                decisions["urgency"] = 0.8
                decisions["reasoning"] = f"Acting on strong hypothesis: {top_hyp}"
                return decisions

        # ── CHECK 3: Stale autonomous goals ──
        next_goal = self.core.goal_manager.get_next_actionable_goal()
        if next_goal:
            urgency = self.core.attention.estimate_action_urgency(
                next_goal.priority, next_goal.staleness_hours)

            if self.core.attention.should_autonomous_act("goal_pursuit", urgency):
                if now - self._last_autonomous_action > self._autonomous_cooldown:
                    decisions["should_act"] = True
                    decisions["action_type"] = "goal_pursuit"
                    decisions["action_target"] = next_goal
                    decisions["urgency"] = urgency
                    decisions["reasoning"] = (
                        f"Autonomous goal: [{next_goal.id}] {next_goal.title} "
                        f"(stale {next_goal.staleness_hours:.1f}h, urgency {urgency:.2f})")

        # ── CHECK 4: Goal reprioritization (always, low cost) ──
        if self._cycles_count % 10 == 0:  # Every 10 cycles
            self.core.goal_manager.reprioritize_goals()

        # Log cognition trace
        if decisions["should_act"]:
            self.core.log_cognition("CognitionLoop", "decision",
                                     decisions["reasoning"][:200])

        return decisions

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  ACT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _act(self, decisions: Dict[str, Any]):
        """Executes the decided action."""
        action_type = decisions.get("action_type")

        if action_type == "goal_pursuit":
            await self._pursue_goal(decisions.get("action_target"))
            decisions["action_taken"] = True
            self._last_autonomous_action = time.time()

        elif action_type == "anomaly_alert":
            await self._handle_anomaly(decisions.get("reasoning", ""))
            decisions["action_taken"] = True

    async def _pursue_goal(self, goal):
        """Autonomously works on a goal."""
        if not goal:
            return

        logger.info(f"═══ AUTONOMOUS GOAL PURSUIT: [{goal.id}] {goal.title} ═══")
        self.core.log_cognition("CognitionLoop", "goal_pursuit",
                                 f"[{goal.id}] {goal.title}")

        # Update goal status
        self.core.goal_manager.update_goal(goal.id, status="in_progress")

        # Get next subtask
        subtask = self.core.goal_manager.get_next_subtask(goal.id)

        if subtask:
            # Execute subtask through the engine
            try:
                logger.info(f"Executing subtask: {subtask.title}")
                await self.engine.process_input(f"[AUTONOMOUS] {subtask.title}")
                self.core.goal_manager.complete_subtask(goal.id, subtask.id,
                                                         result="Completed autonomously")
                self.core.goal_manager.record_attempt(goal.id, success=True)
            except Exception as e:
                logger.error(f"Autonomous subtask failed: {e}")
                self.core.goal_manager.fail_subtask(goal.id, subtask.id, str(e))
                self.core.goal_manager.record_attempt(goal.id, success=False, error=str(e))
        elif goal.next_action:
            # Execute the goal's next_action
            try:
                await self.engine.process_input(f"[AUTONOMOUS] {goal.next_action}")
                self.core.goal_manager.record_attempt(goal.id, success=True)
            except Exception as e:
                logger.error(f"Autonomous action failed: {e}")
                self.core.goal_manager.record_attempt(goal.id, success=False, error=str(e))
        else:
            # No specific subtask or next_action — mark as needing decomposition
            logger.info(f"Goal [{goal.id}] needs decomposition — no subtasks defined.")
            self.core.goal_manager.update_goal(
                goal.id, blocking_reason="Needs subtask decomposition")

    async def _handle_anomaly(self, reason: str):
        """Handles detected anomalies (e.g., user stuck)."""
        logger.info(f"Anomaly handling: {reason}")
        self.core.log_cognition("CognitionLoop", "anomaly", reason)
        # Emit event for other modules to react
        if self.core.event_bus:
            await self.core.event_bus.emit("ANOMALY_DETECTED", {
                "reason": reason, "time": time.time()
            }, sender="CognitionLoop")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  REFLECT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _reflect(self, decisions: Dict[str, Any]):
        """Post-action reflection."""
        action_type = decisions.get("action_type", "")
        self.core.log_cognition("CognitionLoop", "reflect",
                                 f"Post-{action_type} reflection")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  CONSOLIDATE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _maybe_consolidate(self):
        """Runs memory consolidation during idle periods."""
        now = time.time()
        if now - self._last_consolidation > self._idle_consolidation_interval:
            logger.info("Idle consolidation: running memory maintenance...")
            try:
                await self.core.memory.consolidate()
                self._last_consolidation = now
                self.core.log_cognition("CognitionLoop", "consolidation", "Memory consolidated")
            except Exception as e:
                logger.debug(f"Consolidation error: {e}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  ADAPTIVE FREQUENCY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _adapt_cycle_frequency(self, situation: Dict[str, Any]):
        """Adapts cognition cycle speed based on activity level."""
        user_state = situation.get("user_state", "unknown")
        has_goals = situation.get("active_goals", 0) > 0

        if user_state == "actively_working":
            self._current_cycle_ms = 3000   # 3s — responsive
        elif user_state == "present":
            self._current_cycle_ms = 5000   # 5s — normal
        elif user_state == "idle":
            if has_goals:
                self._current_cycle_ms = 8000   # 8s — can work on goals
            else:
                self._current_cycle_ms = 15000  # 15s — quiet
        else:  # away
            self._current_cycle_ms = 30000  # 30s — deep sleep

        # Clamp
        self._current_cycle_ms = max(self._min_cycle_ms,
                                      min(self._max_cycle_ms, self._current_cycle_ms))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  TELEMETRY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _log_telemetry(self, situation: Dict):
        logger.info(
            f"[COGNITION PULSE] Cycle #{self._cycles_count} | "
            f"Interval: {self._current_cycle_ms}ms | "
            f"User: {situation.get('user_state', '?')} | "
            f"Goals: {situation.get('active_goals', 0)} active, "
            f"{situation.get('stale_goals', 0)} stale | "
            f"Proactivity: {situation.get('proactivity', 0)}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "total_cycles": self._cycles_count,
            "current_interval_ms": self._current_cycle_ms,
            "last_autonomous_action_ago": round(time.time() - self._last_autonomous_action, 1)
                if self._last_autonomous_action else -1,
            "last_consolidation_ago": round(time.time() - self._last_consolidation, 1),
        }
