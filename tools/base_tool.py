"""[V8.0] J.A.R.V.I.S. Base Tool & ToolResult
━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━
The base class and standard output structure of all async tools.

Changes (differences from core/tools.py):
    - execute() → async def execute()
    - Mandatory metadata: domain, latency_ms, reliability_score
    - to_schema() also exports metadata fields

Design Decision:
    Why async execute()?
    → Playwright native async. Desktop/system tools
      It is wrapped with internal run_in_executor.
    → Executor makes a single await tool.execute() call.
    → Uniform interface — no tools require special handling."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("JARVIS.Tools")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOOL RESULT — Standard Tool Output
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class ToolResult:
    """Each tool returns this object from execute()."""
    success: bool
    verified: bool = False
    message: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0
    speak: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    next_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":           self.success,
            "verified":          self.verified,
            "message":           self.message,
            "error":             self.error,
            "execution_time_ms": self.execution_time_ms,
            "speak":             self.speak,
            "data":              self.data,
            "next_action":       self.next_action,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BASE TOOL — Async Abstract Base Class
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BaseTool(ABC):
    """All J.A.R.V.I.S. Base class of v8.0 tools.

    Subclasses MUST define:
        - name: Vehicle name (unique, snake_case)
        - description: Human readable description
        - match protocol_tag: [PROTOCOL: X] tag
        - parameters: Parameter schemas (JSON Schema-like dict)
        -domain: "web" | "desktop" | "system"
        - latency_ms: Estimated latency (ms)
        - reliability_score: Reliability score (0.0-1.0)
        - execute(): async — method that performs the operation

    Optional:
        - requires_interaction: Vehicles that require engine-level interaction
        - pre_speak: TTS message before Execute"""

    name: str = ""
    description: str = ""
    protocol_tag: str = ""
    parameters: Dict[str, dict] = {}

    # ── ZORUNLU METADATA ──
    domain: str = "system"           # "web" | "desktop" | "system"
    latency_ms: int = 1000           # Tahmini ms
    reliability_score: float = 0.5   # 0.0 - 1.0

    # ── OPSIYONEL ──
    requires_interaction: bool = False
    pre_speak: str = ""

    @abstractmethod
    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        """Run the tool asynchronously.

        Args:
            params: Tool-specific parameters
            engine_context: Read-only context by Engine

        Returns:
            ToolResult"""
        pass

    def to_schema(self) -> dict:
        """Exports the tool's definition in JSON Schema format that LLM understands.
        Including metadata fields."""
        return {
            "name": self.name,
            "description": self.description,
            "protocol_tag": self.protocol_tag,
            "parameters": self.parameters,
            "requires_interaction": self.requires_interaction,
            "domain": self.domain,
            "latency_ms": self.latency_ms,
            "reliability_score": self.reliability_score,
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"tag={self.protocol_tag}, "
            f"domain={self.domain}, "
            f"reliability={self.reliability_score})"
        )


def _run_sync(func, *args):
    """Helper to run blocking function in asyncio thread pool.
    Desktop and system tools use this function."""
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, func, *args)
