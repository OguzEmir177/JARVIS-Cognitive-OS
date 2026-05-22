"""
[V12.0] J.A.R.V.I.S. Cognitive Core — Autonomous Operating System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Central cognitive orchestrator. Provides cognitive services AND
manages the autonomous cognition loop.

Architecture:
    CognitiveCore
    ├── AutonomousCognitionLoop (perpetual PERCEIVE→THINK→ACT→REFLECT)
    ├── GoalManager (persistent objectives with autonomous pursuit)
    ├── ToolRouter (semantic + historical routing)
    ├── ReflectionEngine (tool-grounded verification)
    ├── WorldStateManager (environment graph)
    ├── AttentionScorer (proactive notification gating)
    ├── RecoverySystem (failure handling)
    ├── EventBus (inter-module communication)
    ├── DynamicMemorySystem (self-improving cognitive memory)
    ├── SkillRegistry (dynamic capabilities)
    ├── PlannerEngine (runtime adaptive planning)
    └── AgentCoordinator (multi-agent cognition)
"""
import asyncio, logging, time, uuid
from typing import Dict, Any, Optional

from core.event_bus import EventBus
from core.world_state import EnvironmentGraph
from core.goals import GoalManager
from core.planner import PlannerEngine
from core.execution_graph import GraphExecutor
from core.reflection import ReflectionEngine
from core.recovery import RecoverySystem
from core.skills import SkillRegistry
from core.attention import AttentionScorer
from core.multi_agent import AgentCoordinator
from memory.memory_manager import DynamicMemorySystem

# V13 Semantic Engines
from core.workflow_inference import WorkflowInferenceEngine
from core.hypothesis_engine import HypothesisEngine
from core.self_model import SelfModel

logger = logging.getLogger("JARVIS.CognitiveCore")

class CognitiveCore:
    """
    [V13.0] Cognitive Services Provider + Autonomous Loop Manager.
    """
    def __init__(self, config, brain, chroma_memory):
        self.config = config
        self.brain = brain

        # 1. Base Systems
        self.event_bus = EventBus()
        self.world_state = EnvironmentGraph(self.event_bus)
        self.goal_manager = GoalManager()
        self.memory = DynamicMemorySystem(chroma_memory)
        self.skill_registry = SkillRegistry()

        # 2. V13 Semantic Cognition Engines
        self.workflow_engine = WorkflowInferenceEngine(self.world_state)
        self.hypothesis_engine = HypothesisEngine(self.event_bus)
        self.self_model = SelfModel()

        # 3. Reasoning & Decision
        self.planner = PlannerEngine(self.brain)
        self.reflection = ReflectionEngine(self.brain)
        self.recovery = RecoverySystem(self.event_bus)
        self.attention = AttentionScorer()

        # 4. Semantic Router (lazy loaded)
        self._tool_router = None
        self._router_loading = False

        # 4. Perception (started separately)
        self.perception = None

        # 5. Autonomous Cognition Loop (started after engine is ready)
        self._cognition_loop = None

        # 6. Multi-Agent Coordinator (lazy — needs full core)
        self._agent_coordinator = None

        # 7. Cognition Traces (Observability)
        self.cognition_log: list = []
        self._max_log = 500
        self._start_time = time.time()

        # Wire up events
        self.event_bus.subscribe("WINDOW_CHANGED", self._on_window_changed)
        self.event_bus.subscribe("TASK_COMPLETED", self._on_task_completed)
        self.event_bus.subscribe("TASK_FAILED", self._on_task_failed)
        self.event_bus.subscribe("PERCEPTION_UPDATE", self._on_perception_update)

    @property
    def tool_router(self):
        if self._tool_router is None and not self._router_loading:
            self._router_loading = True
            try:
                from core.semantic_router import SemanticRouter
                self._tool_router = SemanticRouter()
                logger.info("SemanticRouter (Vector-based) loaded.")
            except ImportError as e:
                logger.error(f"SemanticRouter ImportError: {e}. Lütfen requirements.txt kurulumlarını yapın.")
                self._router_loading = False
            except Exception as e:
                logger.warning(f"SemanticRouter yüklenemedi: {e}")
                self._router_loading = False
        return self._tool_router

    @property
    def agent_coordinator(self):
        if self._agent_coordinator is None:
            self._agent_coordinator = AgentCoordinator(self)
        return self._agent_coordinator

    async def initialize(self):
        """Initialize perception and other async systems."""
        logger.info("Initializing Cognitive OS Core V12.0...")

        # Start perception
        try:
            from core.perception import PerceptionLayer
            self.perception = PerceptionLayer(self.event_bus, self.world_state)
            await self.perception.start()
            logger.info("Perception Engine started.")
        except ImportError as e:
            logger.warning(f"Perception not available: {e}")
        except Exception as e:
            logger.warning(f"Perception failed to start: {e}")

        logger.info("Cognitive Core V12.0 Online.")

    async def start_cognition_loop(self, engine):
        """Starts the autonomous cognition loop (called after engine is ready)."""
        from core.autonomous_loop import AutonomousCognitionLoop
        self._cognition_loop = AutonomousCognitionLoop(self, engine)
        await self._cognition_loop.start()
        logger.info("═══ AUTONOMOUS COGNITION LOOP ONLINE ═══")

    def stop_cognition_loop(self):
        if self._cognition_loop:
            self._cognition_loop.stop()

    def interrupt_cognition(self, reason: str = "user_input"):
        """Interrupts the cognition loop (e.g., user gave new input)."""
        if self._cognition_loop:
            self._cognition_loop.interrupt(reason)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  COGNITION TRACE (Observability)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def log_cognition(self, module: str, action: str, detail: str = ""):
        entry = {"time": time.time(), "module": module,
                 "action": action, "detail": detail[:300]}
        self.cognition_log.append(entry)
        if len(self.cognition_log) > self._max_log:
            self.cognition_log = self.cognition_log[-self._max_log:]

    def get_cognition_trace(self, limit: int = 20) -> list:
        return self.cognition_log[-limit:]

    def get_system_status(self) -> Dict[str, Any]:
        """Full system observability dashboard."""
        status = {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "cognition_loop": self._cognition_loop.get_status() if self._cognition_loop else "not started",
            "attention": self.attention.get_stats(),
            "goals": {"active": len(self.goal_manager.get_active_goals()),
                       "stale": len(self.goal_manager.get_stale_goals())},
            "reflection": self.reflection.get_reflection_stats(),
            "memory": self.memory.get_stats(),
            "world_state": self.world_state.get_situation_assessment(),
            "recovery": self.recovery.get_health_report(),
            "skills": self.skill_registry.get_stats(),
            "cognition_traces": len(self.cognition_log),
        }
        if self._tool_router:
            status["tool_router"] = self._tool_router.get_tool_stats()
        if self._agent_coordinator:
            status["agents"] = self._agent_coordinator.get_agent_stats()
        return status

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  EVENT HANDLERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _on_window_changed(self, event):
        self.log_cognition("Perception", "window_change", str(event.data)[:100])

    async def _on_task_completed(self, event):
        self.log_cognition("Engine", "task_completed", str(event.data)[:100])
        # Record tool success in router
        if self._tool_router and isinstance(event.data, dict):
            tool = event.data.get("tool_used", "")
            if tool:
                self._tool_router.record_execution(tool, success=True)

    async def _on_task_failed(self, event):
        self.log_cognition("Engine", "task_failed", str(event.data)[:100])
        self.attention.record_error()
        if self._tool_router and isinstance(event.data, dict):
            tool = event.data.get("tool_used", "")
            if tool:
                self._tool_router.record_execution(tool, success=False)

    async def _on_perception_update(self, event):
        self.log_cognition("Perception", "update", str(event.data)[:100])
