import asyncio
import logging
import time
from typing import Dict, Any, List
from enum import Enum

logger = logging.getLogger("JARVIS.Recovery")

class FailureType(Enum):
    TIMEOUT = "timeout"
    AUTH = "authentication"
    TOOL_ERROR = "tool_execution_error"
    REASONING_ERROR = "reasoning_hallucination"
    NETWORK = "network_issue"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"

class RecoverySystem:
    """
    [V11.1] Autonomous Recovery & Self-Healing
    Features: adaptive retry, circuit breaker, alternate tools, failure classification.
    """
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.failure_history: List[Dict[str, Any]] = []
        self._circuit_breakers: Dict[str, int] = {}
        self._circuit_threshold = 3
        self._alternate_tools = {
            "GOOGLE_SEARCH": ["WEB_SEARCH", "WEB_OPEN"],
            "WEB_SEARCH": ["GOOGLE_SEARCH"],
            "APP_OPEN": ["WEB_OPEN"],
            "YT_PLAY": ["YT_SEARCH", "WEB_OPEN"],
        }

    async def handle_failure(self, task_id: str, error: str, context: dict) -> Dict[str, Any]:
        f_type = self._classify_failure(error)
        logger.warning(f"Recovery: {task_id}: {f_type.value} - {error[:100]}")
        
        self.failure_history.append({
            "task_id": task_id, "type": f_type.value,
            "error": error[:200], "time": time.time()
        })
        if len(self.failure_history) > 100:
            self.failure_history = self.failure_history[-100:]
        
        tool = context.get("tool", "unknown")
        recent = sum(1 for f in self.failure_history[-10:] if f["task_id"] == task_id)
        
        if f_type == FailureType.TIMEOUT:
            if recent < 2:
                return {"strategy": "retry_backoff", "delay": 2 ** recent,
                        "params": {"timeout": 30 + recent * 10}}
            return self._suggest_alternate(tool)
        
        if f_type == FailureType.RATE_LIMIT:
            return {"strategy": "retry_backoff", "delay": 10 + recent * 5}
        
        if f_type == FailureType.TOOL_ERROR:
            if recent < 2:
                return {"strategy": "retry", "delay": 1}
            return self._suggest_alternate(tool)
        
        if f_type == FailureType.REASONING_ERROR:
            return {"strategy": "replan", "reason": "Logic error, replan needed."}
        
        if f_type == FailureType.AUTH:
            return {"strategy": "abort", "reason": "Auth error, cannot recover."}
        
        if f_type == FailureType.NETWORK:
            if recent < 3:
                return {"strategy": "retry_backoff", "delay": 3 ** recent}
            return {"strategy": "degrade", "reason": "Persistent network failure."}
        
        return {"strategy": "abort", "reason": f"Unrecoverable: {error[:100]}"}

    def _classify_failure(self, error: str) -> FailureType:
        e = error.lower()
        if any(p in e for p in ["timeout", "timed out"]):
            return FailureType.TIMEOUT
        if any(p in e for p in ["api key", "unauthorized", "401", "403"]):
            return FailureType.AUTH
        if any(p in e for p in ["rate limit", "429", "too many"]):
            return FailureType.RATE_LIMIT
        if any(p in e for p in ["connection", "network", "dns"]):
            return FailureType.NETWORK
        if any(p in e for p in ["logic", "hallucin", "parse"]):
            return FailureType.REASONING_ERROR
        if any(p in e for p in ["error", "failed", "not found"]):
            return FailureType.TOOL_ERROR
        return FailureType.UNKNOWN

    def _suggest_alternate(self, tool: str) -> Dict[str, Any]:
        alts = self._alternate_tools.get(tool, [])
        if alts:
            return {"strategy": "alternate_tool", "alternate": alts[0],
                    "all_alternates": alts}
        return {"strategy": "replan", "reason": f"No alternates for {tool}."}

    def get_health_report(self) -> Dict[str, Any]:
        if not self.failure_history:
            return {"total_failures": 0}
        types = {}
        for f in self.failure_history:
            t = f.get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        return {"total_failures": len(self.failure_history), "types": types}
