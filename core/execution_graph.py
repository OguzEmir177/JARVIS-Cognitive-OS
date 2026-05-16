"""
[V12.0] J.A.R.V.I.S. Live Execution Graph
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DAG that mutates at runtime: dynamic node injection, branch switching,
dependency rewiring, plan repair during execution.
"""
import asyncio, logging, time, uuid, re
from enum import Enum
from typing import List, Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, field

logger = logging.getLogger("JARVIS.ExecutionGraph")

class NodeStatus(Enum):
    PENDING = "pending"; RUNNING = "running"; COMPLETED = "completed"
    FAILED = "failed"; SKIPPED = "skipped"; RETRYING = "retrying"

class NodeType(Enum):
    TOOL_CALL = "tool_call"; REASONING = "reasoning"; MEMORY_RETRIEVAL = "memory_retrieval"
    VALIDATION = "validation"; REFLECTION = "reflection"; CONDITION = "condition"

@dataclass
class GraphNode:
    id: str; type: NodeType; action: str
    params: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)
    status: NodeStatus = NodeStatus.PENDING
    result: Any = None; error: Optional[str] = None
    retry_count: int = 0; max_retries: int = 3
    start_time: float = 0.0; end_time: float = 0.0
    injected_at_runtime: bool = False  # Was this node added during execution?

    def to_dict(self):
        return {"id": self.id, "type": self.type.value, "action": self.action,
                "status": self.status.value,
                "result": str(self.result)[:200] if self.result else None,
                "error": self.error, "retries": self.retry_count,
                "runtime_injected": self.injected_at_runtime,
                "duration_ms": int((self.end_time - self.start_time)*1000) if self.end_time else 0}


class ExecutionGraph:
    """
    [V12.0] Live-Mutable DAG Execution Graph
    Supports runtime node injection, branch switching, and dependency rewiring.
    """
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.nodes: Dict[str, GraphNode] = {}
        self._lock = asyncio.Lock()
        self.created_at = time.time()
        self._mutation_log: List[Dict[str, Any]] = []

    def add_node(self, node_type: NodeType, action: str,
                 params: Dict[str, Any] = None,
                 dependencies: List[str] = None) -> str:
        nid = f"{node_type.value}_{str(uuid.uuid4())[:4]}"
        node = GraphNode(id=nid, type=node_type, action=action,
                         params=params or {}, dependencies=set(dependencies or []))
        self.nodes[nid] = node
        return nid

    def get_ready_nodes(self) -> List[GraphNode]:
        ready = []
        for node in self.nodes.values():
            if node.status not in (NodeStatus.PENDING, NodeStatus.RETRYING):
                continue
            all_deps_done = all(
                self.nodes.get(d) and self.nodes[d].status == NodeStatus.COMPLETED
                for d in node.dependencies)
            if all_deps_done:
                ready.append(node)
        return ready

    def is_complete(self) -> bool:
        return all(n.status in (NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED)
                   for n in self.nodes.values())

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  RUNTIME MUTATIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def inject_node(self, node_type: NodeType, action: str,
                          params: Dict[str, Any] = None,
                          after_node_id: str = None) -> str:
        """Injects a new node into the graph at runtime."""
        async with self._lock:
            nid = f"inj_{str(uuid.uuid4())[:4]}"
            deps = set()
            if after_node_id and after_node_id in self.nodes:
                deps.add(after_node_id)
                # Rewire: any node depending on after_node_id now depends on new node
                for n in self.nodes.values():
                    if after_node_id in n.dependencies and n.status == NodeStatus.PENDING:
                        n.dependencies.discard(after_node_id)
                        n.dependencies.add(nid)

            node = GraphNode(id=nid, type=node_type, action=action,
                             params=params or {}, dependencies=deps,
                             injected_at_runtime=True)
            self.nodes[nid] = node
            self._mutation_log.append({"type": "inject", "node": nid, "after": after_node_id,
                                       "time": time.time()})
            logger.info(f"RUNTIME INJECT: {nid} ({action}) after {after_node_id}")
            return nid

    async def skip_node(self, node_id: str, reason: str = ""):
        """Skips a pending node and its dependents if needed."""
        async with self._lock:
            if node_id in self.nodes:
                self.nodes[node_id].status = NodeStatus.SKIPPED
                self.nodes[node_id].error = f"Skipped: {reason}"
                self._mutation_log.append({"type": "skip", "node": node_id,
                                           "reason": reason, "time": time.time()})
                logger.info(f"RUNTIME SKIP: {node_id} — {reason}")

    async def rewire_dependency(self, node_id: str, old_dep: str, new_dep: str):
        """Rewires a dependency edge at runtime."""
        async with self._lock:
            if node_id in self.nodes:
                node = self.nodes[node_id]
                node.dependencies.discard(old_dep)
                node.dependencies.add(new_dep)
                self._mutation_log.append({"type": "rewire", "node": node_id,
                                           "old": old_dep, "new": new_dep, "time": time.time()})

    def get_mutation_log(self) -> List[Dict[str, Any]]:
        return self._mutation_log

    def get_telemetry(self) -> Dict[str, Any]:
        """Full execution telemetry."""
        total = len(self.nodes)
        by_status = {}
        total_time = 0
        for n in self.nodes.values():
            s = n.status.value
            by_status[s] = by_status.get(s, 0) + 1
            if n.end_time and n.start_time:
                total_time += (n.end_time - n.start_time)
        return {"task_id": self.task_id, "total_nodes": total, "by_status": by_status,
                "total_execution_ms": int(total_time * 1000),
                "mutations": len(self._mutation_log),
                "runtime_injected": sum(1 for n in self.nodes.values() if n.injected_at_runtime)}


class GraphExecutor:
    """
    [V12.0] Adaptive Graph Executor
    Executes DAG with parallel batching, retry, and runtime repair.
    """
    def __init__(self, tool_executor: Callable, reflection_engine=None):
        self.tool_executor = tool_executor
        self.reflection = reflection_engine
        self.telemetry = []

    async def execute(self, graph: ExecutionGraph) -> Dict[str, Any]:
        logger.info(f"GRAPH START: {graph.task_id} ({len(graph.nodes)} nodes)")
        stall_count = 0
        max_stalls = 3

        while not graph.is_complete():
            ready = graph.get_ready_nodes()
            if not ready:
                if not graph.is_complete():
                    stall_count += 1
                    if stall_count >= max_stalls:
                        logger.error("Graph stalled — breaking deadlock by skipping blocked nodes.")
                        await self._break_deadlock(graph)
                    else:
                        await asyncio.sleep(0.5)
                        continue
                break

            stall_count = 0
            tasks = [self._execute_node(graph, n) for n in ready]
            await asyncio.gather(*tasks)

        telemetry = graph.get_telemetry()
        logger.info(f"GRAPH DONE: {graph.task_id} — {telemetry}")
        return telemetry

    async def _execute_node(self, graph: ExecutionGraph, node: GraphNode):
        async with graph._lock:
            node.status = NodeStatus.RUNNING; node.start_time = time.time()

        try:
            params = self._interpolate(node.params, graph)
            logger.info(f"Node {node.id} ({node.action}) running...")
            result = await self.tool_executor(node.action, params)

            async with graph._lock:
                node.result = result; node.status = NodeStatus.COMPLETED
                node.end_time = time.time()
                self.telemetry.append(node.to_dict())

            # Post-execution: should we inject a verification node?
            if self.reflection and node.type == NodeType.TOOL_CALL:
                verification = await self._maybe_inject_verification(graph, node)
                if verification:
                    logger.info(f"Verification injected after {node.id}")

        except Exception as e:
            logger.error(f"Node {node.id} failed: {e}")
            async with graph._lock:
                node.error = str(e)
                if node.retry_count < node.max_retries:
                    node.retry_count += 1; node.status = NodeStatus.RETRYING
                    logger.info(f"Node {node.id} retry {node.retry_count}/{node.max_retries}")
                else:
                    node.status = NodeStatus.FAILED; node.end_time = time.time()
                    self.telemetry.append(node.to_dict())

    async def _maybe_inject_verification(self, graph: ExecutionGraph,
                                          completed_node: GraphNode) -> bool:
        """Injects a verification node after critical tool calls."""
        critical_tools = {"APP_OPEN", "WEB_OPEN", "WHATSAPP_MESSAGE"}
        if completed_node.action not in critical_tools:
            return False
        await graph.inject_node(
            NodeType.VALIDATION, f"VERIFY_{completed_node.action}",
            params={"verify_node": completed_node.id,
                    "expected_result": str(completed_node.result)[:100]},
            after_node_id=completed_node.id)
        return True

    async def _break_deadlock(self, graph: ExecutionGraph):
        """Skips nodes with unresolvable dependencies."""
        for node in graph.nodes.values():
            if node.status == NodeStatus.PENDING:
                unmet = [d for d in node.dependencies
                         if d not in graph.nodes or graph.nodes[d].status == NodeStatus.FAILED]
                if unmet:
                    await graph.skip_node(node.id, f"Deadlock: deps {unmet} failed")

    def _interpolate(self, params: Dict[str, Any], graph: ExecutionGraph) -> Dict[str, Any]:
        """Replaces {{node_id.result}} placeholders with actual results."""
        processed = {}
        for k, v in params.items():
            if isinstance(v, str):
                for m in re.findall(r'\{\{(.*?)\.result\}\}', v):
                    dep = graph.nodes.get(m)
                    if dep and dep.status == NodeStatus.COMPLETED:
                        v = v.replace(f"{{{{{m}.result}}}}", str(dep.result))
                processed[k] = v
            else:
                processed[k] = v
        return processed
