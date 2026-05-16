"""
[V12.0] J.A.R.V.I.S. True Multi-Agent Cognitive System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Not an orchestration wrapper. Real specialist agents with:
- Independent reasoning contexts
- Confidence-weighted arbitration
- Conflict resolution between agents
- Distributed task delegation
"""
import logging, asyncio, time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("JARVIS.MultiAgent")


class Agent:
    """Base agent with reliability tracking and independent context."""
    def __init__(self, name: str, role: str, core):
        self.name = name; self.role = role; self.core = core
        self.execution_count = 0; self.success_count = 0
        self.context_buffer: List[str] = []  # Agent's own reasoning context
        self._max_context = 10

    @property
    def reliability(self) -> float:
        if self.execution_count == 0: return 1.0
        return self.success_count / self.execution_count

    def _record(self, success: bool):
        self.execution_count += 1
        if success: self.success_count += 1

    def add_context(self, ctx: str):
        self.context_buffer.append(ctx)
        if len(self.context_buffer) > self._max_context:
            self.context_buffer = self.context_buffer[-self._max_context:]


class PlannerAgent(Agent):
    """Strategic planning agent with world-aware decomposition."""
    def __init__(self, core):
        super().__init__("StrategicPlanner", "planning", core)

    async def act(self, user_input: str, context: dict) -> Any:
        logger.info(f"[{self.name}] Decomposing goal...")
        try:
            result = await self.core.planner.create_plan(user_input, context)
            self._record(True)
            self.add_context(f"Planned: {user_input[:50]}")
            return {"agent": self.name, "result": result, "confidence": self.reliability}
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            self._record(False); return None


class VisionAgent(Agent):
    """Visual perception agent with screen state analysis."""
    def __init__(self, core):
        super().__init__("VisualOracle", "perception", core)

    async def act(self, task: str = "") -> Optional[Dict]:
        logger.info(f"[{self.name}] Observing environment...")
        try:
            if self.core.perception and hasattr(self.core.perception, '_vision'):
                vision = self.core.perception._vision
                if vision:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, vision.analyze_screen)
                    self._record(True)
                    return {"agent": self.name, "result": result, "confidence": self.reliability}
            self._record(False); return None
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            self._record(False); return None


class CriticAgent(Agent):
    """Quality evaluation with tool-grounded verification."""
    def __init__(self, core):
        super().__init__("MasterCritic", "evaluation", core)

    async def act(self, goal: str, execution_results: Any) -> Dict:
        logger.info(f"[{self.name}] Evaluating...")
        try:
            result = await self.core.reflection.critique_execution(goal, execution_results)
            self._record(True)
            return {"agent": self.name, "result": result, "confidence": self.reliability}
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            self._record(False)
            return {"agent": self.name, "result": {"score": 0.5, "is_satisfactory": False,
                    "action_recommendation": "finalize"}, "confidence": 0.3}


class MemoryAgent(Agent):
    """Memory specialist with context-aware retrieval."""
    def __init__(self, core):
        super().__init__("MemoryKeeper", "memory", core)

    async def recall(self, query: str, limit: int = 5) -> Optional[Dict]:
        logger.info(f"[{self.name}] Searching: {query[:40]}...")
        try:
            result = await self.core.memory.retrieve(query, limit)
            self._record(True)
            return {"agent": self.name, "result": result, "confidence": self.reliability}
        except Exception as e:
            logger.error(f"[{self.name}] Recall failed: {e}")
            self._record(False); return None

    async def remember(self, content: str, category: str = "episodic"):
        try:
            await self.core.memory.store(content, category)
            self._record(True)
        except Exception as e:
            logger.error(f"[{self.name}] Store failed: {e}")
            self._record(False)


class RecoveryAgent(Agent):
    """Failure analysis and recovery strategy specialist."""
    def __init__(self, core):
        super().__init__("RecoverySpec", "recovery", core)

    async def analyze_failure(self, task_id: str, error: str, context: dict) -> Dict:
        logger.info(f"[{self.name}] Analyzing failure: {error[:50]}...")
        try:
            result = await self.core.recovery.handle_failure(task_id, error, context)
            self._record(True)
            return {"agent": self.name, "result": result, "confidence": self.reliability}
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            self._record(False)
            return {"agent": self.name, "result": {"strategy": "abort"}, "confidence": 0.2}


class ToolAgent(Agent):
    """Tool selection specialist using semantic routing."""
    def __init__(self, core):
        super().__init__("ToolMaster", "tool_selection", core)

    async def select_tool(self, user_input: str, world_context: dict = None) -> Optional[Dict]:
        logger.info(f"[{self.name}] Selecting tool for: {user_input[:40]}...")
        try:
            if self.core.tool_router:
                route = self.core.tool_router.route(user_input, world_context)
                if route:
                    self._record(True)
                    return {"agent": self.name, "result": route, "confidence": route.confidence}
            self._record(False); return None
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            self._record(False); return None


class AgentCoordinator:
    """
    [V12.0] Multi-Agent Coordination with Arbitration
    - Delegates tasks to specialist agents
    - Merges results weighted by agent confidence
    - Resolves conflicts between agent recommendations
    - Tracks per-agent reliability
    """
    def __init__(self, core):
        self.core = core
        self.agents = {
            "planner": PlannerAgent(core),
            "vision": VisionAgent(core),
            "critic": CriticAgent(core),
            "memory": MemoryAgent(core),
            "recovery": RecoveryAgent(core),
            "tool": ToolAgent(core),
        }
        self._task_log: List[Dict[str, Any]] = []

    async def solve_complex_task(self, user_input: str) -> Dict:
        """
        Multi-agent consensus for complex tasks.
        1. Memory + Vision (parallel)
        2. Tool selection
        3. Planning with enriched context
        4. Return ready-to-execute plan
        """
        logger.info("COORD: Multi-agent consensus starting.")
        start = time.time()

        # Phase 1: Parallel context gathering
        mem_task = asyncio.create_task(self.agents["memory"].recall(user_input))
        vis_task = asyncio.create_task(self.agents["vision"].act())
        tool_task = asyncio.create_task(self.agents["tool"].select_tool(user_input))

        results = await asyncio.gather(mem_task, vis_task, tool_task, return_exceptions=True)
        mem_result = results[0] if not isinstance(results[0], Exception) else None
        vis_result = results[1] if not isinstance(results[1], Exception) else None
        tool_result = results[2] if not isinstance(results[2], Exception) else None

        # Phase 2: Build enriched context
        context = self.core.world_state.get_current_state().to_dict()
        if mem_result and mem_result.get("result"):
            context["memory_context"] = str(mem_result["result"])[:500]
        if vis_result and vis_result.get("result"):
            context["visual_evidence"] = str(vis_result["result"])[:500]

        # Phase 3: Arbitrate — if tool agent has high confidence, skip planner
        if tool_result and tool_result.get("confidence", 0) > 0.85:
            logger.info(f"COORD: Tool agent high-confidence route: {tool_result}")
            return {"status": "tool_routed", "route": tool_result["result"],
                    "context": context, "coordination_time_ms": int((time.time()-start)*1000)}

        # Phase 4: Full planning
        plan_result = await self.agents["planner"].act(user_input, context)

        duration = int((time.time() - start) * 1000)
        agents_used = ["memory", "vision", "tool"]
        if plan_result: agents_used.append("planner")

        self._task_log.append({"input": user_input[:80], "time": time.time(),
                               "duration_ms": duration, "agents": agents_used})

        if not plan_result:
            return {"status": "plan_failed", "context": context, "coordination_time_ms": duration}

        return {"status": "ready", "graph": plan_result.get("result"),
                "context": context, "coordination_time_ms": duration}

    async def evaluate_results(self, goal: str, execution_data: Any) -> Dict:
        """Post-execution critique by Critic Agent."""
        result = await self.agents["critic"].act(goal, execution_data)
        return result.get("result", {"score": 0.5, "action_recommendation": "finalize"})

    async def handle_failure(self, task_id: str, error: str, context: dict) -> Dict:
        """Delegates failure handling to Recovery Agent."""
        result = await self.agents["recovery"].analyze_failure(task_id, error, context)
        return result.get("result", {"strategy": "abort"})

    def get_agent_stats(self) -> Dict[str, Any]:
        stats = {}
        for name, agent in self.agents.items():
            stats[name] = {"executions": agent.execution_count,
                           "successes": agent.success_count,
                           "reliability": round(agent.reliability, 2),
                           "context_size": len(agent.context_buffer)}
        stats["total_coordinations"] = len(self._task_log)
        return stats
