"""[V8.0] J.A.R.V.I.S. Rule-Based Reflector
━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━
Post-mission evaluation engine.

Responsibilities:
    - What did I do? / What did it do? / What failed? /
      What changes next time? answer your questions
    - Save the result to ChromaDB as episodic memory
    - Provide context for future planning

Design Decisions:
    Why rule-based (not LLM)?
    → Groq free tier: 30 req/min, 6000 tokens/min.
      Calling for reflection LLM on every mission blows the budget.
    → Simple success/error → deterministic templates are enough.
    → Ambiguous cases are rare → there is an optional LLM flag.

    Why 4 question format?
    → "What did I do? What worked? What failed? What to change?"
      — standard reflective learning framework.
    → Template text moves to ChromaDB → semantics in the future
      It is used as context in tasks similar to retrieval.

Edge Cases:
    - If TaskState.tool_history is empty → note "tool not used"
    - If all tools are successful → short positive summary
    - If all tools fail → detailed error analysis
    - Partial success → "ambiguous" flag → optional LLM reflection"""

import logging
from typing import Any, Dict, List, Optional

from core.state_manager import TaskState
from core.memory import MemoryManager

logger = logging.getLogger("JARVIS.Reflector")


class Reflector:
    """Rule-based reflection engine.

    API compatible with engine.py:
        reflector = Reflector(memory=memory, brain=brain)
        result = reflector.reflect(task_state)
        #result → {"summary": str, "task_type": str,
        #            "outcome": str, "tool_used": str}
        # or None (if reflection is not required)

    Attributes:
        memory: MemoryManager reference (for episodic write)
        brain: GroqBrain reference (for optional LLM reflection)"""

    def __init__(
        self,
        memory: Optional[MemoryManager] = None,
        brain: Optional[Any] = None,  # GroqBrain Any to prevent circular import
    ) -> None:
        self.memory = memory
        self.brain = brain

    async def reflect(self, task_state: TaskState) -> Optional[Dict[str, str]]:
        """Produces post-task rule-based reflection.

        Args:
            task_state: Completed or failed TaskState

        Returns:
            Reflection dict:
                {
                    "summary":    str — 4 sorunun cevabını içeren özet metin
                    "task_type":  str — görev türü (web/desktop/system/mixed)
                    "outcome":    str — "success" | "failure" | "partial"
                    "tool_used":  str — kullanılan ana tool (virgülle ayrılmış)
                }
            None — reflection if there is nothing to produce
                   (ex: empty tool_history, mission not finished yet)

        Edge Cases:
            - is_terminal == False → None (task not finished, no reflection)
            - tool_history is empty → general chat, reflection skip
            - All tools successful → short positive note
            - All tools fail → detailed error note
            - Partial success → "partial" outcome"""
        # Guard: Do not produce reflection if the task is not yet in terminal state
        if not task_state.is_terminal:
            logger.debug(
                f"Reflection skipped: task {task_state.id}"
                f"not yet terminal ({task_state.status})"
            )
            return None

        # Guard: Producing reflection if the tool is not used (pure chat)
        history = task_state.tool_history
        if not history:
            logger.debug(
                f"Reflection skipped: task {task_state.id}"
                f"tool_history is empty (pure chat)"
            )
            return None

        # ── ANALYSIS ──
        tools_used = [h.get("tool", "unknown") for h in history]
        successes = [h for h in history if h.get("success", False)]
        failures = [h for h in history if not h.get("success", True)]
        total_duration = sum(h.get("duration_ms", 0) for h in history)

        # ── OUTCOME DETERMINATION ──
        outcome = self._determine_outcome(
            total=len(history),
            success_count=len(successes),
            failure_count=len(failures),
        )

        # ── TASK TYPE ──
        task_type = self._infer_task_type(tools_used)

        # ── TOOL USED (comma separated) ──
        unique_tools = list(dict.fromkeys(tools_used))  # order-preserving unique
        tool_used_str = ", ".join(unique_tools)

        # ── 4 SORUNUN CEVABI ──
        summary = self._build_summary(
            goal=task_state.goal,
            outcome=outcome,
            tools_used=unique_tools,
            successes=successes,
            failures=failures,
            total_duration=total_duration,
            last_error=task_state.last_error,
        )

        logger.info(
            f"Reflection generated: task={task_state.id},"
            f"outcome={outcome}, tools={tool_used_str}"
        )

        reflection_dict = {
            "summary": summary,
            "task_type": task_type,
            "outcome": outcome,
            "tool_used": tool_used_str,
        }

        # [V8.1] Importance Scoring & Pruning
        importance = 0.6 # Default
        if outcome == "failure":
            importance = 0.2
        elif "music" in task_type or "spotify" in tool_used_str.lower():
            importance = 0.4 # Routine tasks
        
        # ── BUDAMA (Pruning) ──
        if importance < 0.3:
            logger.info(f"Reflection pruned (Importance={importance} < 0.3): task={task_state.id}")
            return reflection_dict

        # Episodic memory recording CANCELED (To maintain token limit and prevent garbage data)
        # Learning operations are already recorded in JSON by AdaptiveLearner.
        return reflection_dict

    async def reflect_with_llm(
        self, task_state: TaskState, hint: str = ""
    ) -> Optional[Dict[str, str]]:
        """LLM supported reflection for ambiguous situations.

        This method is only invoked when explicitly called by the engine.
        In normal flow, reflect() works rule-based.

        Args:
            task_state: Task state
            hint: additional context to LLM (e.g. "reason for partial success unclear")

        Returns:
            Reflection dict or None

        Edge Cases:
            - if brain is None → fallback to rule-based reflect()
            - LLM timeout → fallback to rule-based reflect()
            - LLM 429 → fallback to rule-based reflect()"""
        if self.brain is None:
            logger.warning(
                "LLM reflection was requested but brain is not available,"
                "rule-based fallback is used."
            )
            return await self.reflect(task_state)

        # Get rule-based base reflection
        base_reflection = await self.reflect(task_state)
        if base_reflection is None:
            return None

        # Ask the LLM: "Why was this mission partially successful?"
        try:
            prompt = (
                f"J.A.R.V.I.S. completed a task.\n"
                f"Hedef: {task_state.goal}\n"
                f"Result: {base_reflection['outcome']}\n"
                f"Tools used: {base_reflection['tool_used']}\n"
                f"Rule-based summary: {base_reflection['summary']}\n"
                f"Additional context: {hint}\n\n"
                f"Write a brief review about this assignment."
                f"What should be done differently next time?"
            )

            # brain.think() is now async
            llm_response_obj = await self.brain.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=150,
                timeout=5.0,
            )
            llm_response = llm_response_obj.choices[0].message.content.strip()

            base_reflection["summary"] += f"\n[LLM INSIGHT]: {llm_response}"
            logger.info("LLM reflection has been added successfully.")

        except Exception as e:
            logger.warning(f"LLM reflection failed (fallback): {e}")

        return base_reflection

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  INTERNAL — Reflection Building Blocks
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _determine_outcome(
        total: int, success_count: int, failure_count: int
    ) -> str:
        """It determines the success status.

        Returns:
            "success" — all steps successful
            "failure" — all steps failed
            "partial" — mixed results

        Edge Case:
            total == 0 → "success" (no tool used = pure chat success)"""
        if total == 0:
            return "success"
        if failure_count == 0:
            return "success"
        if success_count == 0:
            return "failure"
        return "partial"

    @staticmethod
    def _infer_task_type(tools_used: List[str]) -> str:
        """Extracts the task type from the tools used.

        Mapping:
            GOOGLE_SEARCH, WEB_OPEN, YT_* → "web"
            APP_OPEN, APP_KILL, TAB_KILL → "desktop"
            VISION, STRESS_TEST → "system"
            Mixed → “mixed”"""
        web_tools = {"GOOGLE_SEARCH", "WEB_OPEN", "YT_SEARCH", "YT_PLAY",
                     "WHATSAPP_MESSAGE", "WHATSAPP_DELETE"}
        desktop_tools = {"APP_OPEN", "APP_KILL", "TAB_KILL"}
        system_tools = {"VISION", "STRESS_TEST"}

        tool_set = set(tools_used)

        has_web = bool(tool_set & web_tools)
        has_desktop = bool(tool_set & desktop_tools)
        has_system = bool(tool_set & system_tools)

        categories = sum([has_web, has_desktop, has_system])

        if categories > 1:
            return "mixed"
        if has_web:
            return "web"
        if has_desktop:
            return "desktop"
        if has_system:
            return "system"
        return "unknown"

    @staticmethod
    def _build_summary(
        goal: str,
        outcome: str,
        tools_used: List[str],
        successes: List[Dict],
        failures: List[Dict],
        total_duration: int,
        last_error: Optional[str],
    ) -> str:
        """It converts the answers to 4 questions into a single summary text.

        Format:
            [WHAT DID I DO] ...
            [WHAT IT DID] ...
            [WHAT FAILED] ...
            [NEXT TIME] ...

        Edge Cases:
            - If there is no failure → "There is no failure"
            - If there is no success → "Nothing works"
            - last_error None → error detail is skipped"""
        lines = []

        # 1. NE YAPTIM?
        tools_str = ", ".join(tools_used) if tools_used else "no vehicle"
        lines.append(
            f"[NE YAPTIM] Hedef: '{goal[:80]}'. "
            f"Tools used: {tools_str}."
            f"Total time: {total_duration}ms."
        )

        # 2. WHAT WORKED?
        if successes:
            success_tools = [s.get("tool", "?") for s in successes]
            lines.append(
                f"[WHAT IT DID] Successful tools: {', '.join(success_tools)}."
            )
        else:
            lines.append("[WHAT WORKED] There is no tool that works.")

        # 3. WHAT FAILED?
        if failures:
            fail_tools = [f.get("tool", "?") for f in failures]
            error_detail = f"Last error: {last_error}" if last_error else ""
            lines.append(
                f"[WHAT FAILED] Failed tools:"
                f"{', '.join(fail_tools)}.{error_detail}"
            )
        else:
            lines.append("[WHAT HAS FAILED] There is no one who has failed.")

        # 4. WHAT WILL CHANGE NEXT TIME?
        if outcome == "success":
            lines.append(
                "[NEXT TIME] Same strategy"
                "Reusable (proven successful)."
            )
        elif outcome == "failure":
            # Hangi fallback denenebilir?
            suggestion = (
                f"Alternative tools or different arguments can be tried."
            )
            if last_error and "timeout" in last_error.lower():
                suggestion = "Timeout period can be increased or a lighter vehicle can be tried."
            lines.append(f"[NEXT TIME] {suggestion}")
        else:  # partial
            lines.append(
                "[NEXT TIME] For failed steps"
                "The fallback chain should be reviewed."
            )

        return " ".join(lines)
