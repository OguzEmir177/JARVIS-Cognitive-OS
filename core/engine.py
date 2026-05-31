"""[V12.0] J.A.R.V.I.S. Cognitive Execution Engine
━━━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━━
Central orchestration layer. 
Responsibilities:
    - Initialization of subsystems (Brain, Memory, IOBridge, PlanExecutor)
    - Main input loop (Input Loop)
    - Task state management (TaskState)"""

import asyncio
import logging
import re
import uuid
from typing import Callable, Optional

from core.telemetry import telemetry

from core.io_bridge import IOBridge
from core.state_manager import TaskState, StateManager
from core.task_queue import TaskQueue, TaskPriority
from core.planner import parse_plan, ExecutionPlan
from core.executor import Executor
from core.reflector import Reflector
from core.brain import GroqBrain
from core.memory import MemoryManager
from core.config import EngineConfig
from core.cognitive_core import CognitiveCore
from core.pattern_extractor import PatternExtractor
from core.adaptive_learner import AdaptiveLearner
from errors import JarvisError

logger = logging.getLogger("JARVIS.Engine")

class ExecutionEngine:
    """J.A.R.V.I.S. v8.1 Central Orchestrator."""

    def __init__(self, config: Optional[EngineConfig] = None) -> None:
        self.config = config or EngineConfig()
        self._running: bool = False

        # decoupled components
        self.io_bridge = IOBridge(self.config)
        self.state_manager: StateManager = StateManager()
        self.task_queue: TaskQueue = TaskQueue(maxsize=self.config.max_queue_size)
        
        # Core components (installed in initialize)
        self.brain: Optional[GroqBrain] = None
        self.memory: Optional[MemoryManager] = None
        self.executor: Optional[Executor] = None
        self.reflector: Optional[Reflector] = None
        self.plan_executor: Optional["PlanExecutor"] = None
        self.cognitive_core: Optional[CognitiveCore] = None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  IO BRIDGE PROXIES (GUI Compatibility)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @property
    def text_mode(self) -> bool:
        return self.io_bridge.text_mode

    @text_mode.setter
    def text_mode(self, value: bool) -> None:
        self.io_bridge.text_mode = value

    @property
    def text_input_queue(self) -> Optional[object]:
        return self.io_bridge.text_input_queue

    @text_input_queue.setter
    def text_input_queue(self, value: Optional[object]) -> None:
        self.io_bridge.text_input_queue = value

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  DEPENDENCY INJECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def set_tts(self, tts_func: Callable) -> None:
        self.io_bridge.set_tts(tts_func)

    def set_stt(self, stt_func: Callable) -> None:
        self.io_bridge.set_stt(stt_func)

    def set_stt_instance(self, instance: object) -> None:
        self.io_bridge.set_stt_instance(instance)

    def reset_audio(self) -> None:
        """Used to reset crashed sound engine (STT) via GUI."""
        self.io_bridge.reset_audio_engine()

    def set_gui_callback(self, callback: Callable) -> None:
        self.io_bridge.set_gui_callback(callback)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  LIFECYCLE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def initialize(self) -> None:
        """Initializes all subsystems."""
        logger.info("Starting Engine...")

        # 1. Memory
        self.memory = await asyncio.get_running_loop().run_in_executor(
            None, self._init_memory
        )

        # 2. Brain
        self.brain = await self._init_brain_with_retry()

        # 3. Context Compressor [V11.1]
        from core.context_compressor import ContextCompressor
        self.compressor = ContextCompressor()
        self.brain.compressor = self.compressor # Brain'e enjekte et

        # 4. Executor
        self.executor = Executor(
            brain=self.brain,
            memory=self.memory,
            config=self.config,
        )

        # 5. Reflector
        self.reflector = Reflector(
            memory=self.memory,
            brain=self.brain,
        )

        # 6. Plan Executor
        from core.plan_executor import PlanExecutor
        self.plan_executor = PlanExecutor(
            self.brain, self.memory, self.executor, 
            self.state_manager, self.io_bridge, self.config
        )

        # [V16.0] Dynamic Skill Synthesizer
        from core.skill_synthesizer import DynamicSkillSynthesizer
        self.skill_synthesizer = DynamicSkillSynthesizer(self.executor.registry)
        self.plan_executor.skill_synthesizer = self.skill_synthesizer
        logger.info("Dynamic Skill Synthesizer started.")

        # [V9.0] ContactManager — starting contact profile manager
        from core.contact_manager import ContactManager
        self.contact_manager = ContactManager(memory_manager=self.memory)
        self.contact_manager.setup_contacts()

        # PlanExecutor'a referans ver
        self.plan_executor.contact_manager = self.contact_manager
        logger.info("ContactManager is started and connected to PlanExecutor.")
        
        # [V9.0] Create scheduler
        from core.scheduler import JarvisScheduler
        self.scheduler = JarvisScheduler(engine=self)
        self.plan_executor.scheduler = self.scheduler
        logger.info("Scheduler has been created.")
        
        # [V10.2] Autonomous Watcher
        from core.watcher import ProactiveWatcher
        self.watcher = ProactiveWatcher(engine=self)
        logger.info("Proactive Watcher has been launched.")
        
        # [V12.0] Initialize Cognitive Core
        from core.cognitive_core import CognitiveCore
        self.cognitive_core = CognitiveCore(self.config, self.brain, self.memory)
        await self.cognitive_core.initialize()
        
        # Skill Registry entegrasyonu
        self.cognitive_core.skill_registry.register_from_tool_registry(self.executor.registry)
        
        # Memory Consolidator
        from core.memory_consolidator import MemoryConsolidator
        self.memory_consolidator = MemoryConsolidator(memory=self.memory)
        self.scheduler.add_daily(2, 0, "__SYSTEM_CONSOLIDATE__")
        
        self.pattern_extractor = PatternExtractor(memory=self.memory)
        self.memory.pattern_extractor = self.pattern_extractor
        
        # [V15.4] Autonomous Garbage Cleaner (Auto-Cleanup)
        self._run_autonomous_cleanup()

        # [V14.0] Adaptive Learner — Autonomous Learning Engine
        self.adaptive_learner = AdaptiveLearner()
        self.brain._adaptive_learner_ref = self.adaptive_learner  # Brain'e referans ver
        logger.info(f"Adaptive Learner started: {self.adaptive_learner.get_stats()['total_strategies']} strategy loaded.")
        
        logger.info("Engine and Cognitive OS Core V14.0 launched successfully.")


    async def start(self) -> None:
        """Main execution loop."""
        self._running = True
        
        # Startup reminders control
        await self._check_startup_reminders()
        
        await self.io_bridge.speak("Sir, systems are ready. Come on, I'm listening to you.")
        # [V9.0] Start Scheduler in background
        self._scheduler_task = asyncio.create_task(self.scheduler.run())
        # [V9.9] Start Watcher in background
        self._watcher_task = asyncio.create_task(self.watcher.run())
        # [V12.0] Start Autonomous Cognition Loop
        if self.cognitive_core:
            await self.cognitive_core.start_cognition_loop(self)

        while self._running:
            try:
                self.io_bridge.update_gui("LISTENING")

                user_input = await self.io_bridge.get_input()
                if not user_input or len(user_input.strip()) < 2:
                    continue

                if self._is_shutdown_command(user_input):
                    await self._handle_shutdown()
                    break

                # [V9.5] ShutdownTool sentinel control
                if user_input == "__SHUTDOWN__":
                    break

                user_input = self._clean_wake_word(user_input)
                if not user_input:
                    await self.io_bridge.speak("Sir, come again. I am listening.")
                    continue

                # [V12.0] Interrupt cognition loop on user input
                if self.cognitive_core:
                    self.cognitive_core.interrupt_cognition("user_input")

                await self.process_input(user_input)

                # [V9.5] Check flag after ShutdownTool execute
                if self.io_bridge.shutdown_requested:
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Engine loop error: {e}", exc_info=True)
                await self.io_bridge.speak("Sir, an error has occurred.")
                await asyncio.sleep(1)

        await self.shutdown()

    async def shutdown(self) -> None:
        """It shuts down all subsystems cleanly."""
        self._running = False
        logger.info("Engine shutting down...")

        # [V12.0] Cognition Loop durdur
        if self.cognitive_core:
            self.cognitive_core.stop_cognition_loop()
            if self.cognitive_core.perception:
                self.cognitive_core.perception.stop()

        # [V9.9] Stop Watcher
        if hasattr(self, 'watcher'):
            self.watcher.stop()
            if hasattr(self, '_watcher_task') and not self._watcher_task.done():
                self._watcher_task.cancel()
                try:
                    await self._watcher_task
                except asyncio.CancelledError:
                    pass

        # [V9.0] Stop Scheduler
        if hasattr(self, 'scheduler'):
            self.scheduler.stop()
        if hasattr(self, '_scheduler_task') and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        if self.executor:
            await self.executor.cleanup()
        logger.info("Engine V12.0 has been shut down.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PROCESSING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def process_input(self, user_input: str) -> None:
        """[V11.1] Hybrid Cognitive Processing Engine.
        
        Architecture: CognitiveCore modules are used for decision enrichment,
        The actual tool execution is done through the proven legacy pipeline.
        
        pipeline:
          1. Goal Tracking (CognitiveCore)
          2. Semantic Routing (ToolRouter - deterministic)
          3. Brain Reasoning (LLM)
          4. Plan Execution (Legacy PlanExecutor)
          5. Reflection & Recovery (CognitiveCore)
          6. Event Emission (EventBus)"""
        if user_input == "__SYSTEM_CONSOLIDATE__":
            await asyncio.get_running_loop().run_in_executor(
                None, self.memory_consolidator.consolidate)
            await asyncio.get_running_loop().run_in_executor(
                None, self.memory_consolidator.prune_duplicates)
            return

        task_id = str(uuid.uuid4())[:8]
        telemetry.log_event(task_id, "REQUEST_RECEIVED", "start", {"user_input": user_input})
        task_state = self.state_manager.create_task(task_id=task_id, goal=user_input)
        goal = None

        try:
            await self.io_bridge.speak("Understood, Sir.")
            self.io_bridge.update_gui("PROCESSING")

            # ════════════════════════════════════════════════════════
            #  PHASE 0: ADAPTIVE LEARNING PRE-CHECK
            # ════════════════════════════════════════════════════════

            # A. Repetition Detection — Did he repeat the same command in a short time?
            repeat_task_id = None
            if hasattr(self, 'adaptive_learner'):
                repeat_task_id = self.adaptive_learner.detect_repeat(user_input)
                if repeat_task_id:
                    logger.info(f"[V14.0] Detected again — different strategy will be tried.")

            # B. Learned Strategy Control
            # [V15.0] USING learned strategy for FILE_* and FOLDER_* operations
            # — each file command targets a different file, cached arg is invalid
            # [V15.5] Added PYTHON_EXEC — each coding task is unique,
            # cached strategy reruns old/incorrect code
            # [FIX] Added WHATSAPP_MESSAGE and other text-based tools so they don't send old messages
            DYNAMIC_CONTENT_TAGS = {
                "FILE_CREATE", "FILE_WRITE", "FILE_READ", "FILE_DELETE",
                "FOLDER_OPEN", "FILE_LATEST", "PYTHON_EXEC",
                "WHATSAPP_MESSAGE", "WEB_SEARCH", "GOOGLE_SEARCH", "YT_SEARCH",
                "LLM_EVAL", "YOUTUBE_STRATEGY", "REMEMBER", "STARTUP_REMINDER",
                "SCHEDULE", "MAP_SHOW", "CHART_SHOW", "SPEAK"
            }
            learned_strategy = None
            if hasattr(self, 'adaptive_learner') and not repeat_task_id:
                # Run keyword router first — skip learned strategy if dynamic
                try:
                    _quick_route = self.cognitive_core.tool_router._keyword_route(user_input) if self.cognitive_core else None
                    if _quick_route and _quick_route.tool_tag.upper() in DYNAMIC_CONTENT_TAGS:
                        logger.info(f"[V15.0] {_quick_route.tool_tag} — learned strategy skipped (dynamic)")
                    else:
                        learned_strategy = self.adaptive_learner.find_strategy(user_input)
                except Exception:
                    learned_strategy = self.adaptive_learner.find_strategy(user_input)
                
                if learned_strategy and learned_strategy.tool_chain and learned_strategy.tool_chain[0].upper() in DYNAMIC_CONTENT_TAGS:
                    logger.info(f"[V15.0] Learned strategy {learned_strategy.tool_chain[0]} was skipped because it was dynamic.")
                    learned_strategy = None

            # ════════════════════════════════════════════════════════
            #  PHASE 1: COGNITIVE ENRICHMENT (Pre-Execution)
            # ════════════════════════════════════════════════════════

            # A. Goal Tracking — Persistent objective memory
            if self.cognitive_core:
                goal = self.cognitive_core.goal_manager.create_goal(user_input)
                self.cognitive_core.attention.record_interaction()
                
                # Store in working memory
                try:
                    await self.cognitive_core.memory.store(user_input, "working")
                except Exception as mem_err:
                    logger.debug(f"Working memory store skipped: {mem_err}")

            # B. Semantic Routing — Deterministic tool selection (LLM bypass)
            forced_route = None
            
            # [V14.0] If there is a learned strategy, use it first (except FILE_*)
            if learned_strategy and not repeat_task_id:
                from core.tool_router import RouteMatch
                forced_route = RouteMatch(
                    tool_tag=learned_strategy.tool_chain[0],
                    params={"query": learned_strategy.arguments[0] if learned_strategy.arguments else user_input},
                    confidence=learned_strategy.confidence,
                    is_forced=True,
                    reasoning=f"Learned strategy ({learned_strategy.success_count}x success)"
                )
                logger.info(f"[V14.0] Using learned strategy: {learned_strategy.tool_chain}")
            elif self.cognitive_core:
                try:
                    forced_route = self.cognitive_core.tool_router.route(user_input)
                    if forced_route:
                        telemetry.log_event(task_id, "ROUTING", "matched", {"tool": forced_route.tool_tag, "confidence": forced_route.confidence})
                except Exception as route_err:
                    logger.warning(f"Semantic router error (fallback to Brain): {route_err}")

            # ════════════════════════════════════════════════════════
            #  PHASE 2: EXECUTION (Real Tool Pipeline)
            # ════════════════════════════════════════════════════════

            if forced_route and forced_route.is_forced:
                # ── DETERMINISTIC PATH: Router forced a tool ──
                logger.info(
                    f"[OTONOM KARAR] {forced_route.tool_tag} "
                    f"(Trust: {forced_route.confidence:.3f}, Forced: True)"
                )
                from core.planner import PlanNode

                # [V15.0] Param extraction — Router provided for FILE_* tools
                # parametreyi aynen kullan (file_path_and_content, folder_path vb.)
                params = forced_route.params or {}

                # Use correct param key for FILE_* tools
                FILE_PARAM_KEYS = {
                    "FILE_WRITE":  "file_path_and_content",
                    "FILE_CREATE": "file_path",
                    "FILE_READ":   "file_path",
                    "FILE_DELETE": "file_path",
                    "FOLDER_OPEN": "folder_path",
                    "FILE_LATEST": "dir_path",
                }
                tool_tag = forced_route.tool_tag.upper()
                if tool_tag in FILE_PARAM_KEYS:
                    # First try the correct key of the router
                    # [V15.0] CRITICAL: '' (empty string) is also a valid value —
                    # tool gets last_active_file from context. Use None check.
                    expected_key = FILE_PARAM_KEYS[tool_tag]
                    val = params.get(expected_key)
                    if val is not None:
                        node_arg = val  # Pass even "" — gets from tool context
                    elif "query" in params:
                        node_arg = params["query"]
                    else:
                        node_arg = user_input
                else:
                    # Other tools: get query if present, first value or user_input if not
                    if "query" in params:
                        node_arg = params["query"]
                    elif params:
                        node_arg = next(iter(params.values()))
                    else:
                        node_arg = user_input

                node = PlanNode(
                    step_number=1,
                    protocol_tag=forced_route.tool_tag,
                    argument=node_arg
                )
                success = await self.plan_executor.execute_node(task_state, node)

                if not success:
                    last_tool = task_state.tool_history[-1] if task_state.tool_history else {}
                    if not last_tool.get("result", {}).get("speak"):
                        await self.io_bridge.speak(
                            f"Sir, operation {forced_route.tool_tag} failed."
                            f"Should I try a different way?"
                        )
                    self.state_manager.fail_task(task_id, f"Deterministic route failed: {forced_route.tool_tag}")
            else:
                # ── STANDARD PATH: Brain → Plan → Execute ──
                # 1. The Brain Thinks
                response = await self.brain.think(user_input)
                if response == "RATE_LIMIT_ALL":
                    await self.io_bridge.speak("Sir, my brain module has gone into rest.")
                    if goal:
                        self.cognitive_core.goal_manager.update_goal(goal.id, status="failed")
                    return

                # [V9.5] Plan Leak Cleaner
                response = self._sanitize_llm_output(response)

                #2. Plan determination and execution
                plan = await self.plan_executor.detect_and_parse_plan(response, user_input)

                if plan:
                    await self.plan_executor.execute_plan(task_state, plan)
                else:
                    # [V9.8] Mixed Content Management
                    protocol_start = response.find("[PROTOCOL:")
                    if protocol_start > 0:
                        preceding_text = response[:protocol_start].strip()
                        if preceding_text:
                            await self.io_bridge.speak(preceding_text)
                        remaining_response = response[protocol_start:]
                        await self.plan_executor.execute_single(task_state, remaining_response)
                    elif protocol_start == 0:
                        await self.plan_executor.execute_single(task_state, response)
                    else:
                        await self.io_bridge.speak(response)
                        self.state_manager.complete_task(task_id)

            # ════════════════════════════════════════════════════════
            #  PHASE 3: COGNITIVE REFLECTION (Post-Execution)
            # ════════════════════════════════════════════════════════

            # A. Legacy Reflection (episodic memory)
            if self.reflector:
                _ref_task = asyncio.create_task(self.reflector.reflect(task_state))
                _ref_task.add_done_callback(
                    lambda t: logger.warning(f"Reflection task error: {t.exception()!r}")
                    if not t.cancelled() and t.exception() is not None
                    else None
                )

            # B. Pattern Extraction (learning from failures)
            if hasattr(self, 'pattern_extractor'):
                await asyncio.get_running_loop().run_in_executor(
                    None, self.pattern_extractor.extract_patterns)

            # C. Goal Completion
            if goal and self.cognitive_core:
                is_success = task_state.status != "failed"
                self.cognitive_core.goal_manager.update_goal(
                    goal.id,
                    status="completed" if is_success else "failed",
                    progress=1.0 if is_success else 0.0
                )
            
            telemetry.log_event(task_id, "RESPONSE_GENERATED", "end", {"status": task_state.status, "tools": len(task_state.tool_history)})

            # D. [V14.0] ADAPTIVE LEARNING — Pass/Fail Record
            if hasattr(self, 'adaptive_learner'):
                tools_used = [h.get("tool", "") for h in task_state.tool_history if h.get("tool")]
                args_used = [h.get("arg", "") for h in task_state.tool_history if h.get("tool")]
                is_success = task_state.status != "failed"
                
                if tools_used:
                    if is_success:
                        self.adaptive_learner.record_success(user_input, tools_used, args_used)
                        
                        # [V15.0] Semantic Router Dynamic Embedding Autonomous Learning
                        if self.cognitive_core and len(tools_used) == 1 and not (forced_route and forced_route.is_forced):
                            router = getattr(self.cognitive_core, 'tool_router', None)
                            if router and hasattr(router, 'learn_new_route'):
                                arg_to_save = args_used[0] if args_used else None
                                asyncio.create_task(router.learn_new_route(user_input, tools_used[0], arg_to_save))
                    else:
                        self.adaptive_learner.record_failure(user_input, tools_used)
                
                # Update task_id for repeat detection
                self.adaptive_learner.update_recent_task_id(user_input, task_id)

            # E. Event Emission + Tool Learning
            if self.cognitive_core:
                await self.cognitive_core.event_bus.emit("TASK_COMPLETED", {
                    "task_id": task_id,
                    "goal": user_input,
                    "status": task_state.status,
                    "tools_used": len(task_state.tool_history),
                    "tool_used": task_state.tool_history[-1] if task_state.tool_history else ""
                }, sender="Engine")

        except Exception as e:
            logger.error(f"Processing error [{task_id}]: {e}", exc_info=True)
            self.state_manager.fail_task(task_id, str(e))

            # Recovery System
            if self.cognitive_core:
                try:
                    recovery = await self.cognitive_core.recovery.handle_failure(
                        task_id, str(e), {"goal": user_input}
                    )
                    logger.info(f"Recovery strategy: {recovery}")
                    
                    if goal:
                        self.cognitive_core.goal_manager.update_goal(goal.id, status="failed")
                    
                    await self.cognitive_core.event_bus.emit("TASK_FAILED", {
                        "task_id": task_id, "error": str(e), "recovery": recovery
                    }, sender="Engine")
                except Exception as rec_err:
                    logger.warning(f"Recovery system error: {rec_err}")

            await self.io_bridge.speak("Sir, something went wrong.")
        finally:
            # Clean up traces of garbage in memory after the process is finished
            self._run_autonomous_cleanup()
            self.io_bridge.update_gui("LISTENING")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _sanitize_llm_output(text: str) -> str:
        """[V9.5] Plan Leak Sanitizer
        ────────────────────────── ───────────────────────────
        LLM sometimes closes the [PLAN] block with a made-up tag instead of [/PLAN].
        These tags escape the parser and leak onto the user screen as raw strings.

        Cleared patterns:
          ./PROTOCOL PLAN [most common hallucination]
          /PROTOCOL PLAN
          [/PROTOCOL]
          [/PROTOCOL PLAN]
          [PLAN_END] [END_PLAN] [/PLAN_END]
          ./PLAN /PLAN (alone in the wrong place)

        Strategy:
          - Full patterns with square brackets first (most specific → avoids greedy problem)
          - Then slash-prefix general patterns
          - [/PLAN] (current closing) UNTOUCHED."""
        if not text:
            return text

        # ── 1. Fictitious closures in square brackets (PRIORITY) ───
        # [/PROTOCOL PLAN], [/PROTOCOL], [PLAN_END], [END_PLAN], [PLAN_CLOSE]
        text = re.sub(
            r'\[\.?/?(?:PROTOCOL(?:[:\s]+PLAN)?|PLAN_END|END_PLAN|PLAN_CLOSE|/PLAN_END)\]',
            '', text, flags=re.IGNORECASE
        )

        # ── 2. Made-up tags that come with dot-slash prefix ─────────────
        # Ex: "Searched on Google ./PROTOCOL PLAN"
        text = re.sub(
            r'\.?\s*/\s*PROTOCOL(?:[:\s]+PLAN)?\b',
            '', text, flags=re.IGNORECASE
        )

        # ── 3. Slash-prefix genel uydurma etiketler ───────────────────────
        # /PROTOCOL, /PROTOCOL PLAN (without square brackets)
        text = re.sub(
            r'(?<!\[)/\s*PROTOCOL(?:[:\s]+PLAN)?\b',
            '', text, flags=re.IGNORECASE
        )

        # ── 4. Protocol Leak Cleaner (Leaks in text) ─
        # If a line contains a statement like [PROTOCOL: REMEMBER] and it is not a command
        # If # is in the middle of the sentence, clear it out.
        # [V9.8] Clear only non-command start.
        def _leak_fixer(match):
            full_match = match.group(0)
            # If it is at the beginning of a line or preceded by only a space, accept command (tap)
            # But if it's in text ("Please [PROTOCOL: ...]") clear it.
            start_pos = match.start()
            if start_pos > 0 and text[start_pos-1] not in ['\n', ' ']:
                return ""
            return full_match

        text = re.sub(r'\[PROTOCOL:\s*\w+\]', _leak_fixer, text, flags=re.IGNORECASE)

        # ── 4. Clear leftover blank lines ────────────────────────────────
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+\n', '\n', text)

        return text.strip()

    def _is_shutdown_command(self, text: str) -> bool:
        return any(cmd in text.lower() for cmd in [
            "sistemi kapat", "jarvis kapan", "kendini kapat", "log out",
            "shut down yourself", "close yourself", "turn off jarvis",
            "close jarvis", "exit jarvis", "terminate yourself"
        ])

    def _clean_wake_word(self, text: str) -> str:
        # v8.0 logic simplified for orchestrator
        return text.strip()

    async def _handle_shutdown(self) -> None:
        """[V9.5 FIX] Keyword triggered shutdown path.
        Now io_bridge.request_shutdown() is called:
          → 'CLOSING' signal goes to GUI → _on_close() is triggered
          → Sentinel enters the queue → blocking get() is turned on
          → self._running = False (engine loop is broken)"""
        await self.io_bridge.speak("Systems are shutting down. Have a nice day Sir.")
        self.io_bridge.request_shutdown()   # ← GUI sinyali + bayrak + sentinel
        self._running = False

    async def _check_startup_reminders(self) -> None:
        """Checks and reads unread startup reminders."""
        import os, json
        filepath = os.path.join(os.getcwd(), "startup_reminders.json")
        
        def _read_and_clear():
            if not os.path.exists(filepath):
                return None
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                os.remove(filepath)
                return data
            except Exception as e:
                logger.error(f"Startup reminder read error: {e}")
                return None

        reminders = await asyncio.get_running_loop().run_in_executor(None, _read_and_clear)
        if reminders and isinstance(reminders, list):
            await self.io_bridge.speak("Sir, you have reminders from the previous opening.")
            for item in reminders:
                await self.io_bridge.speak(item)
                await asyncio.sleep(1)

    def _init_memory(self):
        from core.memory import MemoryManager
        # [V8.1 Fix] Pass path string, not config object
        m = MemoryManager(db_path=self.config.memory_db_path)
        m.setup_memory()
        return m

    async def _init_brain_with_retry(self) -> "GroqBrain":
        """[V8.1 FIX] BUG #3: Real retry loop — check_connection() in previous version
        The return value was ignored and no retry was made.

        Strategy:
            - Exponential backoff after each failed attempt (2^attempt seconds)
            - Continue in restricted mode if all attempts are exhausted (not crash)"""
        from core.brain import GroqBrain
        b = GroqBrain(self.config, memory_manager=self.memory)

        for attempt in range(self.config.brain_connect_retries):
            connected = await b.check_connection()
            if connected:
                logger.info(f"Brain connection established (trial {attempt + 1}/{self.config.brain_connect_retries})")
                return b

            wait_s = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s…
            logger.warning(
                f"Brain connection attempt {attempt + 1}/{self.config.brain_connect_retries}"
                f"unsuccessful. Will try again after {wait_s}s..."
            )
            await asyncio.sleep(wait_s)

        # Fail-Fast Principle: If all attempts fail, crash the system and give a clear log instead of restricted mode.
        error_msg = (
            f"Critical Error: Brain connection {self.config.brain_connect_retries} could not be established despite attempts!"
            "Please check your internet connection and GROQ_API_KEY."
        )
        logger.critical(error_msg)
        raise SystemError(error_msg)

    def _run_autonomous_cleanup(self) -> None:
        """[V15.5] Autonomous Garbage Cleaner - Cleans all dirty tags."""
        if self.memory and self.memory.collection:
            try:
                def _clean_junk():
                    KIRLI_TAGLAR = [
                        "[ne yaptim]", "[what did it do]",
                        "[what a failure]", "[sonraki seferde]"
                    ]
                    results = self.memory.collection.get(include=["documents"])
                    docs = results.get("documents", [])
                    ids = results.get("ids", [])
                    bad_ids = []
                    
                    for i, doc in enumerate(docs):
                        if doc:
                            doc_lower = doc.lower()
                            if any(tag in doc_lower for tag in KIRLI_TAGLAR):
                                bad_ids.append(ids[i])
                                
                    if bad_ids:
                        self.memory.collection.delete(ids=bad_ids)
                        logger.info(f"Autonomous Cleaning: {len(bad_ids)} garbage logs were deleted from ChromaDB.")
                
                loop = asyncio.get_running_loop()
                loop.run_in_executor(None, _clean_junk)
            except Exception as e:
                logger.debug(f"Auto-cleanup error: {e}")

    def _setup_logging(self) -> None:
        pass