import json
import time
import os
import logging
from typing import Any, Dict

logger = logging.getLogger("JARVIS.Telemetry")

class TraceLogger:
    """
    [V14.5] Production-grade structured logging & telemetry system.
    Provides observability for request -> routing -> planning -> tool execution -> response chain.
    """
    def __init__(self, log_dir: str = "logs"):
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "structured_trace.log")
        self.tool_execution_log = os.path.join(log_dir, "tool_execution.log")

    def log_event(self, trace_id: str, phase: str, event_type: str, data: Dict[str, Any]):
        """Logs a structured event in the cognitive pipeline."""
        entry = {
            "timestamp": time.time(),
            "time_iso": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "trace_id": trace_id,
            "phase": phase,
            "event_type": event_type,
            "data": data
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"Telemetry log error: {e}")

    def log_tool_execution(self, trace_id: str, tool_name: str, input_params: Any, 
                           duration_ms: float, success: bool, output: str, error: str = ""):
        """Logs detailed tool execution metrics."""
        entry = {
            "timestamp": time.time(),
            "time_iso": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "trace_id": trace_id,
            "tool_name": tool_name,
            "input": input_params,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "output": output,
            "error": error
        }
        try:
            with open(self.tool_execution_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"Telemetry tool log error: {e}")

telemetry = TraceLogger()
