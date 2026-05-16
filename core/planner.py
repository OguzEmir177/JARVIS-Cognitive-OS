"""
[V12.0] J.A.R.V.I.S. Runtime Adaptive Planner
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Not static plan-at-start. Real adaptive planner:
- Runtime replanning when steps fail
- Dynamic node injection based on intermediate results
- Opportunistic execution (skip unnecessary steps)
- Plan repair without full replan
"""
import logging, json, re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from core.execution_graph import ExecutionGraph, NodeType, NodeStatus

logger = logging.getLogger("JARVIS.Planner")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LEGACY PLAN STRUCTURES (PlanExecutor compatibility)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class PlanNode:
    step_number: int; protocol_tag: str; argument: str = ""
    sub_nodes: List["PlanNode"] = field(default_factory=list); label: str = ""

@dataclass
class ExecutionPlan:
    steps: List[PlanNode] = field(default_factory=list); original_request: str = ""
    @property
    def total_steps(self) -> int: return len(self.steps)
    def get_context_summary(self) -> str:
        if not self.steps: return "Boş plan."
        return f"Plan: {' → '.join(s.protocol_tag for s in self.steps)} ({self.total_steps} adım)"

ALIAS_MAP = {
    "SEARCH": "GOOGLE_SEARCH", "GOOGLE": "GOOGLE_SEARCH", "YOUTUBE": "YT_SEARCH",
    "YOUTUBE_SEARCH": "YT_SEARCH", "YOUTUBE_PLAY": "YT_PLAY", "OPEN": "WEB_OPEN",
    "KILL": "APP_KILL", "WHATSAPP": "WHATSAPP_MESSAGE", "WA_MESSAGE": "WHATSAPP_MESSAGE",
    "SHUTDOWN": "SYSTEM_SHUTDOWN", "POWER": "SYSTEM_POWER",
    "REMEMBER_THIS": "REMEMBER", "SAVE_MEMORY": "REMEMBER",
    "MAP": "MAP_SHOW", "CHART": "CHART_SHOW", "GRAPH": "CHART_SHOW",
}

def _apply_filters(tag: str, arg: str) -> tuple:
    tag = tag.strip().upper(); arg = arg.strip()
    tag = ALIAS_MAP.get(tag, tag)
    return tag, arg

def parse_plan(response: str) -> Optional[ExecutionPlan]:
    """Parses [PLAN]...[/PLAN] block from LLM response."""
    match = re.search(r'\[PLAN\](.*?)\[/PLAN\]', response, re.DOTALL | re.IGNORECASE)
    if not match: return None
    body = match.group(1).strip()
    if not body: return None
    steps = []; num = 0
    for line in body.split('\n'):
        line = line.strip()
        if not line: continue
        line = re.sub(r'^[\d]+[\.)\-:]\s*', '', line).strip()
        if not line: continue
        proto = re.match(r'\[PROTOCOL:\s*(\w+)\]\s*(.*)', line, re.IGNORECASE)
        if proto:
            tag, arg = proto.group(1), proto.group(2).strip()
        else:
            parts = line.split(None, 1)
            if not parts: continue
            tag = parts[0]; arg = parts[1] if len(parts) > 1 else ""
        tag, arg = _apply_filters(tag, arg)
        num += 1; steps.append(PlanNode(step_number=num, protocol_tag=tag, argument=arg))
    if not steps: return None
    plan = ExecutionPlan(steps=steps)
    logger.info(f"Plan parsed: {plan.get_context_summary()}")
    return plan


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COGNITIVE PLANNER ENGINE (V12 Adaptive)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PlannerEngine:
    """
    [V12.0] Adaptive Cognitive Planner
    Creates DAG plans and repairs them at runtime.
    """
    def __init__(self, brain):
        self.brain = brain
        self._replan_count = 0
        self._max_replans = 3

    async def create_plan(self, user_input: str, world_state: Dict[str, Any]) -> ExecutionGraph:
        """Decomposes goal into ExecutionGraph via LLM."""
        logger.info(f"Planning: {user_input[:60]}")
        prompt = self._build_prompt(user_input, world_state)
        try:
            response = await self.brain.think(prompt)
            match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
            if not match: match = re.search(r'(\{.*\})', response, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                return self._build_graph(user_input, data)
        except Exception as e:
            logger.error(f"Planning failed: {e}")
        return self._fallback_graph(user_input)

    async def repair_plan(self, graph: ExecutionGraph, failed_node_id: str,
                          error: str, world_state: Dict[str, Any]) -> bool:
        """
        Runtime plan repair — tries to fix a failed node without full replan.
        Returns True if repair succeeded (new nodes injected).
        """
        if self._replan_count >= self._max_replans:
            logger.warning("Max replans reached, cannot repair further.")
            return False

        self._replan_count += 1
        failed = graph.nodes.get(failed_node_id)
        if not failed: return False

        logger.info(f"PLAN REPAIR: {failed_node_id} failed with: {error[:80]}")

        # Strategy 1: Simple retry with modified params
        if failed.retry_count < failed.max_retries:
            return False  # Let normal retry handle it

        # Strategy 2: Try alternate tool
        alternates = self._get_alternate_tools(failed.action)
        if alternates:
            alt_tool = alternates[0]
            new_id = await graph.inject_node(
                NodeType.TOOL_CALL, alt_tool,
                params=failed.params.copy(), after_node_id=None)
            # Rewire dependents of failed node to new node
            for n in graph.nodes.values():
                if failed_node_id in n.dependencies and n.status == NodeStatus.PENDING:
                    await graph.rewire_dependency(n.id, failed_node_id, new_id)
            logger.info(f"REPAIR: Replaced {failed.action} with {alt_tool}")
            return True

        # Strategy 3: Skip and inject reasoning node to explain
        await graph.skip_node(failed_node_id, f"Repair failed: {error[:50]}")
        await graph.inject_node(
            NodeType.REASONING, "EXPLAIN_FAILURE",
            params={"original_action": failed.action, "error": error[:200]})
        return True

    async def replan_from_scratch(self, original_goal: str,
                                   completed_nodes: List[Dict],
                                   world_state: Dict[str, Any]) -> ExecutionGraph:
        """Full replan using context of what already succeeded."""
        logger.info(f"FULL REPLAN for: {original_goal[:60]}")
        self._replan_count += 1

        context = {"completed_steps": [n["action"] for n in completed_nodes],
                    "world_state": world_state}
        prompt = f"""[ORIGINAL GOAL]: {original_goal}
[ALREADY COMPLETED]: {json.dumps(context['completed_steps'])}
[CURRENT STATE]: {json.dumps(world_state)}

Kalan adımlar için YENİ plan oluştur (tamamlanmış adımları TEKRARLAMA).
SADECE JSON döndür: {{"nodes": [{{"id": "s1", "type": "tool_call", "action": "TOOL_TAG", "params": {{}}, "deps": []}}]}}"""

        try:
            response = await self.brain.think(prompt)
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                return self._build_graph(original_goal, data)
        except Exception as e:
            logger.error(f"Replan failed: {e}")
        return self._fallback_graph(original_goal)

    def _get_alternate_tools(self, tool_tag: str) -> List[str]:
        alts = {
            "GOOGLE_SEARCH": ["WEB_SEARCH", "WEB_OPEN"],
            "WEB_SEARCH": ["GOOGLE_SEARCH"],
            "APP_OPEN": ["WEB_OPEN"],
            "YT_PLAY": ["YT_SEARCH", "WEB_OPEN"],
        }
        return alts.get(tool_tag, [])

    def _build_prompt(self, goal: str, state: Dict[str, Any]) -> str:
        return f"""[GOAL]: {goal}
[STATE]: {json.dumps(state)}
Görev için DAG plan oluştur. Her adım küçük ve doğrulanabilir olsun.
Node tipleri: tool_call, reasoning, memory_retrieval, validation, reflection
SADECE JSON: {{"reasoning_trace": "...", "nodes": [{{"id": "s1", "type": "tool_call", "action": "TOOL", "params": {{}}, "deps": [], "max_retries": 3}}]}}"""

    def _build_graph(self, goal: str, data: Dict[str, Any]) -> ExecutionGraph:
        graph = ExecutionGraph(task_id=f"plan_{goal[:8]}")
        id_map = {}
        for nd in data.get("nodes", []):
            try:
                nt = NodeType(nd.get("type", "tool_call"))
            except ValueError:
                nt = NodeType.TOOL_CALL
            nid = graph.add_node(nt, nd.get("action", "AUTO"),
                                  nd.get("params", {}),
                                  [id_map[d] for d in nd.get("deps", []) if d in id_map])
            id_map[nd.get("id", nid)] = nid
            graph.nodes[nid].max_retries = nd.get("max_retries", 3)
        logger.info(f"Graph built: {len(graph.nodes)} nodes. Trace: {data.get('reasoning_trace','')[:80]}")
        return graph

    def _fallback_graph(self, goal: str) -> ExecutionGraph:
        graph = ExecutionGraph(task_id=f"fb_{goal[:8]}")
        graph.add_node(NodeType.TOOL_CALL, "AUTO_DETECT", {"input": goal})
        return graph
