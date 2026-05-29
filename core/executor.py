"""[V8.0] J.A.R.V.I.S. ToolExecutor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The layer that finds and runs tools via the Tool Registry.

Responsibilities:
    - Protocol tag → tool matching
    - Parameter preparation (arg → param dict)
    - Async tool execution (blocking tools with run_in_executor)
    - Metadata-based fallback tool selection
    - Measuring tool working time

Design Decisions:
    Why is Executor a separate class?
    → It abstracts engine.py from tool execution details.
    → Tool selection logic (metadata, fallback) in one place.
    → The rule that tools do not touch the engine state is enforced by the executor
      (engine_context is passed as a read-only dict).

    Why is execute_tool() async?
    → Playwright tools native async.
    → For blocking tools (pyautogui, subprocess)
      run_in_executor() is used.
    → Engine can wrap with asyncio.wait_for(timeout).

Edge Cases:
    - Unknown protocol_tag → ToolExecutionError
    - If Tool.execute() throws exception → wrap it in ToolExecutionError
    - If Fallback tool is not found → Returns to None (decided by engine)
    - If tool time exceeds config.tool_timeout_seconds →
      TimeoutError on engine side (not executor's responsibility)"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

from core.config import EngineConfig
from core.brain import GroqBrain
from core.memory import MemoryManager
from tools.base_tool import BaseTool, ToolResult
from tools.tool_registry import ToolRegistry, create_default_registry
from errors import ToolExecutionError
from core.telemetry import telemetry

logger = logging.getLogger("JARVIS.Executor")


# Metadata is now defined in tool classes (domain, latency_ms, reliability_score)
# Fallback chains are defined in tools/tool_registry.py (FALLBACK_CHAINS)


class Executor:
    """Tool execution and fallback management layer.

    API compatible with engine.py:
        executor = Executor(brain, memory, config)

        result = await executor.execute_tool(
            protocol_tag="GOOGLE_SEARCH",
            argument="Python lessons",
            engine_context={"last_whatsapp_num": None},
        )

        fallback = await executor.try_fallback(
            protocol_tag="YT_PLAY",
            argument="lofi beats",
            engine_context={},
        )

        await executor.cleanup()

    Attributes:
        registry: ToolRegistry instance (all tools are registered here)
        brain: GroqBrain reference (if LLM access to tools is required)
        memory: MemoryManager reference (added to tool context)
        config: EngineConfig reference
        _metadata: Tool metadata cache"""

    def __init__(
        self,
        brain: GroqBrain,
        memory: Optional[MemoryManager] = None,
        config: Optional[EngineConfig] = None,
    ) -> None:
        self.brain = brain
        self.memory = memory
        self.config = config or EngineConfig()

        # Tool Registry — via tools/ package
        self.registry: ToolRegistry = create_default_registry()

        logger.info(
            f"Executor started: {self.registry.count} tool registered →"
            f"{self.registry.all_tags}"
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  EXECUTE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def execute_tool(
        self,
        protocol_tag: str,
        argument: str = "",
        engine_context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Finds and runs the tool corresponding to the specified protocol_tag.

        Args:
            protocol_tag: Protocol tag of the Tool (e.g. "GOOGLE_SEARCH")
            argument: The argument to pass to the Tool (ex: "Python lessons")
            engine_context: Read-only context provided by the engine

        Returns:
            ToolResult — the result of the tool's execution

        Raises:
            ToolExecutionError: Tool not found or execute() threw exception

        Edge Cases:
            - Unknown tag → Registry alias check → still missing error
            - If Tool.execute() is blocking → async is wrapped with run_in_executor
            - If Tool returns None → ToolResult(success=False) is produced"""
        tool = self.registry.get_by_protocol(protocol_tag)

        if tool is None:
            msg = f"Bilinmeyen protokol: '{protocol_tag}'"
            logger.error(msg)
            raise ToolExecutionError(
                message=msg,
                tool_name=protocol_tag,
            )

        # Interpolation (Context Transfer)
        interpolated_arg = self._interpolate_argument(argument, engine_context)

        # Parameter preparation — first parameter = argument
        params = self._build_params(tool, interpolated_arg)
        ctx = engine_context or {}
        ctx["brain"] = self.brain  # [V9.0] Add brain reference for file summarization

        # Pre-speak (for long-running tools)
        if hasattr(tool, "pre_speak") and tool.pre_speak:
            logger.info(f"Tool pre_speak: {tool.pre_speak[:40]}...")

        # Execution
        start_time = time.monotonic()

        logger.info(
            f"Tool execute: {tool.name} "
            f"(tag={protocol_tag}, arg='{argument[:50]}', "
            f"domain={tool.domain}, "
            f"expected_latency={tool.latency_ms}ms)"
        )

        try:
            import asyncio
            # [V15.0] Tool-specific timeouts — fail-fast, deadlock prevention
            TOOL_TIMEOUTS = {
                "APP_OPEN":    20.0,
                "APP_KILL":    10.0,
                "FOLDER_OPEN": 8.0,
                "FILE_CREATE": 10.0,
                "FILE_WRITE":  10.0,
                "FILE_READ":   10.0,
                "FILE_DELETE": 10.0,
                "FILE_LATEST": 10.0,
                "WEB_OPEN":    45.0,
                "YT_PLAY":     45.0,
                "YT_SEARCH":   45.0,
                "GOOGLE_SEARCH": 45.0,
                "WEB_SEARCH":  90.0,
                "PYTHON_EXEC": 60.0,
            }
            timeout = TOOL_TIMEOUTS.get(protocol_tag, 30.0)
            result = await asyncio.wait_for(tool.execute(params, ctx), timeout=timeout)

            if result is None:
                result = ToolResult(
                    success=False,
                    verified=False,
                    message=f"{tool.name} returned None.",
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)
            result.execution_time_ms = duration_ms
            
            if not result.verified:
                result.success = False

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(f"Tool timeout: {tool.name} (time: {duration_ms}ms, limit={timeout}s)")
            return ToolResult(
                success=False,
                verified=False,
                error="Timeout",
                message=f"Task timed out ({timeout:.0f}s limit exceeded)."
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            trace_id = engine_context.get("task_id", "unknown") if engine_context else "unknown"
            telemetry.log_tool_execution(
                trace_id=trace_id,
                tool_name=tool.protocol_tag,
                input_params=params,
                duration_ms=duration_ms,
                success=False,
                output="",
                error=str(e)
            )
            logger.error(
                f"Tool exception: {tool.name} → {e} "
                f"(duration: {duration_ms}ms)",
                exc_info=True,
            )
            raise ToolExecutionError(
                message=f"Error running {tool.name}: {str(e)[:100]}",
                tool_name=tool.name,
                original_error=e,
            )

        trace_id = engine_context.get("task_id", "unknown") if engine_context else "unknown"
        
        telemetry.log_tool_execution(
            trace_id=trace_id,
            tool_name=tool.protocol_tag,
            input_params=params,
            duration_ms=duration_ms,
            success=result.success,
            output=result.message,
            error=""
        )

        logger.info(
            f"Tool result: {tool.name} → "
            f"success={result.success}, "
            f"duration={duration_ms}ms, "
            f"next_action={result.next_action or 'none'}"
        )

        return result

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  FALLBACK
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def try_fallback(
        self,
        protocol_tag: str,
        argument: str = "",
        engine_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[ToolResult]:
        """For the unsuccessful tool, it tries an alternative from the fallback chain.

        Fallback selection logic:
            1. Ordered alternatives are retrieved from FALLBACK_CHAINS
            2. Each alternative is tried with execute_tool()
            3. The first successful result is returned
            4. If all else fails, None is returned.

        Args:
            protocol_tag: Tag of the original failed tool
            argument: Original argument (the same is given to fallback)
            engine_context: Read-only engine context

        Returns:
            ToolResult: Successful fallback result
            None: No fallback worked

        Edge Cases:
            - If fallback chain is not defined → None (silent)
            - Fallback tool also fails → next try in the chain
            - Exception in Fallback tool → log, go to next"""
        fallback_tools = self.registry.get_fallback_chain(protocol_tag)

        if not fallback_tools:
            logger.info(
                f"No fallback chain: {protocol_tag}"
            )
            return None

        for fallback_tool in fallback_tools:
            fallback_tag = fallback_tool.protocol_tag
            logger.info(
                f"Fallback deneniyor: {protocol_tag} → {fallback_tag}"
            )
            try:
                result = await self.execute_tool(
                    protocol_tag=fallback_tag,
                    argument=argument,
                    engine_context=engine_context,
                )
                if result.success:
                    logger.info(
                        f"Fallback successful: {fallback_tag}"
                    )
                    return result
                else:
                    logger.warning(
                        f"Fallback failed: {fallback_tag} → {result.message}"
                    )
            except ToolExecutionError as e:
                logger.warning(
                    f"Fallback exception: {fallback_tag} → {e.message}"
                )
                continue

        logger.warning(
            f"All fallbacks fail: {protocol_tag} → {fallback_tools}"
        )
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  METADATA QUERY
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_tool_metadata(self, protocol_tag: str) -> Dict[str, Any]:
        """It reads the tool's metadata directly from the tool class."""
        tool = self.registry.get_by_protocol(protocol_tag)
        if tool:
            return {
                "domain": tool.domain,
                "latency_ms": tool.latency_ms,
                "reliability_score": tool.reliability_score,
            }
        return {}

    def get_best_tool_for_domain(self, domain: str) -> Optional[str]:
        """It returns the best tool in the domain via the registry."""
        best = self.registry.get_best_tool(domain)
        return best.protocol_tag if best else None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  CLEANUP
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def cleanup(self) -> None:
        """Cleans Executor resources.
        engine.py calls during shutdown.
        Playwright browser instance is closed."""
        try:
            from tools.browser_tool import BrowserManager
            await BrowserManager.close()
        except Exception as e:
            logger.warning(f"Browser cleanup error: {e}")
        logger.info("Executor cleanup completed.")

    @staticmethod
    def _interpolate_argument(argument: str, context: Optional[Dict[str, Any]]) -> str:
        """Replaces the [PROTOCOL: TAG] placeholders within the argument with the results of the previous steps."""
        if not argument or not context or "step_results" not in context:
            return argument

        # [V8.2] Support both [PROTOCOL: TAG] and [STEP: TAG] format
        pattern = r"\[(?:PROTOCOL|STEP):\s*(\w+)\]"
        results = context.get("step_results", {})

        def _replace(match):
            tag = match.group(1)
            # If there is a result with that tag, inject it, otherwise leave the placeholder
            return str(results.get(tag, match.group(0)))

        return re.sub(pattern, _replace, argument)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  INTERNAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _build_params(tool: BaseTool, argument: str) -> Dict[str, Any]:
        """[V15.0] According to the tool parameter scheme argument → param dict.

        Special mapping for FILE_* tools:
          FILE_WRITE → file_path_and_content: argument
          FILE_CREATE → file_path: argument
          FILE_READ → file_path: argument
          FILE_DELETE → file_path: argument
          FOLDER_OPEN → folder_path: argument
          FILE_LATEST → dir_path: argument

        Other tools: argument to the first parameter name."""
        if not tool.parameters:
            return {}

        argument = argument or ""

        # [V15.0] Strict param names for FILE tools
        FILE_PARAM_MAP = {
            "FILE_WRITE":  "file_path_and_content",
            "FILE_CREATE": "file_path",
            "FILE_READ":   "file_path",
            "FILE_DELETE": "file_path",
            "FOLDER_OPEN": "folder_path",
            "FILE_LATEST": "dir_path",
        }

        tag = tool.protocol_tag.upper()
        if tag in FILE_PARAM_MAP:
            return {FILE_PARAM_MAP[tag]: argument}

        first_param_name = next(iter(tool.parameters.keys()), None)
        if first_param_name:
            return {first_param_name: argument}
        return {}
