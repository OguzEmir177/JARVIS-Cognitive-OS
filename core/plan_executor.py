"""[V8.3] J.A.R.V.I.S. Plan Executor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The layer that executes the plan steps sequentially/parallelly.
V8.3 Fix: Mangled code cleanup + TypeError fix."""

import asyncio
import logging
import re
import time
import json
import os
from typing import Optional, List, Any

from core.planner import parse_plan, ExecutionPlan, PlanNode
from tools.base_tool import ToolResult

logger = logging.getLogger("JARVIS.PlanExecutor")

# [V15.5] Maximum number of attempts for code error correction cycle
MAX_CODE_FIX_ATTEMPTS = 3


class PlanExecutor:
    """J.A.R.V.I.S. v8.3 Plan Execution Layer."""

    def __init__(self, brain, memory, executor, state_manager, io_bridge, config):
        self.brain = brain
        self.memory = memory
        self.executor = executor
        self.state_manager = state_manager
        self.io_bridge = io_bridge
        self.config = config

        # State tracking (Transferred to Tools)
        self.last_whatsapp_num = None
        self.last_whatsapp_time = 0.0
        self.last_active_file = None
        self.last_contact = None
        self.contacts_path = "contacts.json"

    def _load_contacts(self) -> dict:
        if not os.path.exists(self.contacts_path):
            return {}
        try:
            with open(self.contacts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Directory loading error: {e}")
            return {}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PLAN EXECUTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def execute_plan(self, task_state, plan: ExecutionPlan, _replan_depth: int = 0) -> None:
        logger.info(f"Plan executing: {plan.total_steps} main step. (depth={_replan_depth})")

        tags_in_plan = [n.protocol_tag.upper() for n in plan.steps]
        has_whatsapp = any("WHATSAPP" in t for t in tags_in_plan)

        for i, node in enumerate(plan.steps):
            if not task_state.is_active():
                break

            # Logic Shield
            if node.protocol_tag.upper() == "VISION" and has_whatsapp:
                if any("SEARCH" in t for t in tags_in_plan[:i]):
                    logger.warning(f"Step {node.step_number} (VISION) was skipped.")
                    continue

            if node.sub_nodes:
                tasks = [self.execute_node(task_state, snode) for snode in node.sub_nodes]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                if any(isinstance(r, Exception) or r is False for r in results):
                    logger.warning(f"Partial error in parallel execution of step {node.step_number}.")
            else:
                success = await self.execute_node(task_state, node)
                if not success:
                    if _replan_depth >= self.config.max_replan_attempts:
                        reason = f"Step {node.step_number} failed; max replan exceeded."
                        logger.error(reason)
                        await self.io_bridge.speak("Sir, plan limit exceeded.")
                        self.state_manager.fail_task(task_state.id, reason)
                        return

                    new_plan = await self.replan(task_state, plan, node, "step failed")
                    if new_plan:
                        await self.execute_plan(task_state, new_plan, _replan_depth=_replan_depth + 1)
                    else:
                        self.state_manager.fail_task(task_state.id, "Replan failed.")
                    return

        if task_state.is_active():
            self.state_manager.complete_task(task_state.id)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  NODE EXECUTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def execute_node(self, task_state, node: PlanNode) -> bool:
        """Executes a single plan node. [V13.0 Integrated]"""
        
        #1. Integrated Kernel Protocols (No tools required)
        if node.protocol_tag.upper() == "SPEAK":
            await self.io_bridge.speak(str(node.argument))
            task_state.add_tool_call("SPEAK", str(node.argument), {"success": True})
            return True

        # 2. Iron Dome & Aliases & [V14.0] Adaptive Learning
        if not self.executor.registry.is_registered(node.protocol_tag):
            # Try smart alias
            alias = self.executor.registry.smart_aliases.get(node.protocol_tag.upper())
            if alias:
                node.protocol_tag = alias
            else:
                logger.warning(f"Iron Dome: Unregistered protocol blocked: {node.protocol_tag}")
                
                # [V14.0] Try self-learning for unknown commands
                learned = False
                if hasattr(self.brain, '_adaptive_learner_ref') and self.brain._adaptive_learner_ref:
                    logger.info(f"Iron Dome: Trying to resolve unknown command with LLM...")
                    await self.io_bridge.speak("This talent of mine is not defined yet, I am learning how to do it...")
                    
                    available_tools = self.executor.registry.all_tags
                    # Get original user command from task_state
                    original_req = getattr(task_state, 'goal', str(node.argument))
                    
                    learned_data = await self.brain._adaptive_learner_ref.learn_unknown_command(
                        self.brain, original_req, available_tools
                    )
                    
                    if learned_data and learned_data.get("tool") != "SPEAK":
                        logger.info(f"Iron Dome: LLM found a successful strategy: {learned_data}")
                        node.protocol_tag = learned_data["tool"]
                        node.argument = learned_data["argument"]
                        learned = True
                        await self.io_bridge.speak(f"I'm trying it with the most convenient method I found.")
                
                if not learned:
                    # [V16.0] Kutsal Kase: Tool Synthesis (Kendi Kendine Kod Yazma)
                    synthesized = False
                    if hasattr(self, 'skill_synthesizer') and self.skill_synthesizer:
                        await self.io_bridge.speak(f"Sir, I do not have a vehicle ready for this operation. I code a new tool on the fly with GroqBrain. Please wait.")
                        original_req = getattr(task_state, 'goal', str(node.argument))
                        # Tool tag is cleared to approximate a valid class name form
                        safe_tag = "".join(c if c.isalnum() else "_" for c in node.protocol_tag.upper())
                        if not safe_tag:
                            safe_tag = "DYNAMIC_TOOL"
                        synthesized = await self.skill_synthesizer.synthesize_tool(self.brain, original_req, safe_tag)
                        
                    if synthesized:
                        await self.io_bridge.speak(f"I successfully synthesized the new tool and injected it into the system. I'm running it now.")
                        node.protocol_tag = safe_tag
                    else:
                        await self.io_bridge.speak(
                            f"Sir, I do not have a skill called '{node.protocol_tag}'."
                            f"I couldn't synthesize a tool on my own."
                        )
                        return False

        # 3. Context Interpolation
        context = self._build_context(task_state)
        
        # 3. Execution
        logger.info(f"[execute_node] Initializing: [{node.protocol_tag}] arg='{str(node.argument)[:60]}'")
        try:
            # CORRECTED SIGNATURE: engine_context=context
            result = await self.executor.execute_tool(
                node.protocol_tag, 
                str(node.argument), 
                engine_context=context
            )
        except Exception as e:
            logger.error(f"[execute_node] Tool execute error: {e}", exc_info=True)
            return False

        # ── [V15.5] PYTHON_EXEC SELF-HEALING CYCLE ──────────────────────
        # If the Python code gives an error, send the error to LLM and have the code corrected.
        if not result.success and node.protocol_tag.upper() == "PYTHON_EXEC":
            result = await self._python_self_heal(node, result, context, task_state)
        # ─────────────────────────────────────────────────────────────────────

        # 4. State Update
        task_state.add_tool_call(node.protocol_tag, str(node.argument), result.to_dict())
        
        # 5. Post-Action
        await self._handle_post_execution(task_state, result)
        
        return result.success

    async def _handle_post_execution(self, task_state, result: ToolResult) -> None:
        """Handles post-execution TTS or GUI updates."""
        if result.speak:
            await self.io_bridge.speak(result.speak)
            
        if result.next_action:
            await self.handle_next_action(result)

    async def execute_single(self, task_state, response: str) -> None:
        """Executes all protocol tags in the response in order."""
        # [PROTOL LEAK PROTECTION - ULTRA SECURE]
        # The answer is only the official J.A.R.V.I.S. If the protocol starts with [PROTOCOL: or [PLAN], it is executed.
        # Otherwise this is strictly speaking. All leak tags inside are cleared and voiced directly.
        cleaned_response = response.strip()
        if not (cleaned_response.startswith("[PROTOCOL:") or cleaned_response.startswith("[PLAN") or cleaned_response.startswith("[/PLAN")):
            logger.warning(f"[PlanExecutor] Protocol leak prevented. It is conducted as a conversation.")
            import re as _re
            clean_speech = _re.sub(r'\[PROTOCOL:.*?\]', '', response).strip()
            await self.io_bridge.speak(clean_speech)
            self.state_manager.complete_task(task_state.id)
            return

        matches = list(re.finditer(r'\[PROTOCOL:\s*(\w+)\](.*?)(?=\[PROTOCOL:|$)', response, re.DOTALL))
        if not matches:
            self.state_manager.complete_task(task_state.id)
            return
            
        for i, match in enumerate(matches):
            tag = match.group(1).upper()
            arg = match.group(2).strip()
            node = PlanNode(step_number=i+1, protocol_tag=tag, argument=arg)
            success = await self.execute_node(task_state, node)
            if not success:
                self.state_manager.fail_task(task_state.id, f"Operation {tag} failed.")
                return
                
        self.state_manager.complete_task(task_state.id)

    async def handle_next_action(self, result: ToolResult) -> None:
        """Processes the next_action signals in the tool result."""
        if not result.next_action: return

        handlers = {
            "START_DICTATION":      self._handle_dictation,
            "VISION_INTERPRET":     self._handle_vision_interpret,
            "PYTHON_INTERPRET":     self._handle_python_interpret,
            "CONFIRM_BROWSER_KILL": self._handle_browser_kill_confirm,
            "RUN_STRESS_TEST":      self._handle_stress_test,
            "CLEAR_LAST_HISTORY":   self._handle_clear_history,
            "FILE_WRITE_INTERPRET": self._handle_file_write_interpret,
        }
        handler = handlers.get(result.next_action)
        if handler:
            await handler(result)

    async def _handle_dictation(self, result) -> None:
        self.io_bridge.update_gui("IT IS DICTATED")
        dictated_msg = await self.io_bridge.get_input()
        if not dictated_msg: return
        
        recipient = result.data.get("recipient", self.last_contact)
        contacts = self._load_contacts()
        matched = self._fuzzy_match_contact(recipient, contacts)
        
        if matched:
            from tools.utils.native_ops import NativeOps
            for m_name, m_num in matched:
                await asyncio.get_running_loop().run_in_executor(None, NativeOps.send_whatsapp_blind, m_num, dictated_msg)
                self.last_whatsapp_num = m_num
                self.last_whatsapp_time = time.time()
                self.last_contact = m_name

    @staticmethod
    def _strip_speak_tag(text: str) -> str:
        """Brain sometimes returns a response in the format '[PROTOCOL: SPEAK] message'.
        If this tag is passed raw to io_bridge.speak(), it will leak into the log.
        Returns only clean message text."""
        import re as _re
        # Strip the [PROTOCOL: SPEAK] or [PROTOCOL:SPEAK] tag from the beginning
        cleaned = _re.sub(r'^\s*\[PROTOCOL\s*:\s*SPEAK\]\s*', '', text, flags=_re.IGNORECASE)
        return cleaned.strip()

    async def _handle_vision_interpret(self, result) -> None:
        raw_analysis = result.data.get("raw_analysis", "")
        if not raw_analysis: return
        final = await self.brain.think(f"Explain to your Master what is on the screen: '{raw_analysis}'")
        await self.io_bridge.speak(self._strip_speak_tag(final))

    async def _handle_python_interpret(self, result) -> None:
        output = result.data.get("output", "")
        if not output: return
        final = await self.brain.think(
            f"The output of the Python code you wrote is: '{output}'."
            f"Tell this conclusion to your Master in natural, short and respectful language."
            f"(Ex: 'Sir, I completed the calculation, the result is...')"
        )
        await self.io_bridge.speak(self._strip_speak_tag(final))

    async def _handle_file_write_interpret(self, result) -> None:
        filename = result.data.get("filename", "")
        prompt = (
            f"You have just performed a write operation to file '{filename}'."
            f"Tell your master in very short terms (1-2 sentences) 'what you wrote' and 'why you did this'."
            f"Ex: 'Sir, I fixed the calculator function because there was an addition error.'"
        )
        final = await self.brain.think(prompt, bypass_history=True)
        await self.io_bridge.speak(self._strip_speak_tag(final))

    async def _handle_browser_kill_confirm(self, result) -> None:
        browser = result.data.get("browser", "")
        confirm = await self.io_bridge.get_input()
        if confirm and "evet" in confirm.lower():
            from tools.utils.native_ops import NativeOps
            await asyncio.get_running_loop().run_in_executor(None, NativeOps.kill_app, browser)
            await self.io_bridge.speak(f"{browser} is closed Sir.")

    async def _handle_stress_test(self, result) -> None:
        await self.io_bridge.speak("Stress test completed.")

    async def _handle_clear_history(self, result) -> None:
        if hasattr(self.brain, "chat_history"):
            self.brain.chat_history = self.brain.chat_history[:-1]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [V15.5] PYTHON SELF-HEALING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _python_self_heal(
        self,
        node: "PlanNode",
        failed_result: "ToolResult",
        context: dict,
        task_state,
    ) -> "ToolResult":
        """[V15.5] Python Code Self-Improvement Cycle
        ────────────────────── ───────────────────────
        When a PYTHON_EXEC step fails:
        1. Gets the faulty code + error message.
        2. Sends a "Fix code" prompt to LLM.
        3. Runs the corrected code again via the same tool.
        4. It loops until success or MAX_CODE_FIX_ATTEMPTS is reached."""
        current_result = failed_result
        broken_code = str(node.argument)  # initial code

        for attempt in range(1, MAX_CODE_FIX_ATTEMPTS + 1):
            error_detail = current_result.message or str(current_result.error)
            logger.warning(
                f"[PythonSelfHeal] Deneme {attempt}/{MAX_CODE_FIX_ATTEMPTS} — "
                f"error: {error_detail[:120]}"
            )

            # Notify user
            await self.io_bridge.speak(
                f"Sir, there is an error in my code. I'm correcting, try {attempt}."
            )

            # Send correction request to LLM (bypass_history=True → do not pollute context)
            fix_prompt = (
                f"[PYTHON CODE FIX TASK]\n"
                f"The Python code below was run and gave an error.\n"
                f"Fix the bug and provide ONLY corrected, working Python code.\n"
                f"KURALLAR:\n"
                f"- Don't write any description text, just write pure Python code.\n"
                f"- DO NOT USE input() in code.\n"
                f"- Be sure to write the result with print().\n"
                f"  - Markdown (```) veya protokol etiketi KULLANMA.\n\n"
                f"HATALI KOD:\n{broken_code}\n\n"
                f"ERROR MESSAGE:\n{error_detail}\n\n"
                f"Corrected code:"
            )

            try:
                fixed_response = await self.brain.think(fix_prompt, bypass_history=True)
            except Exception as brain_err:
                logger.error(f"[PythonSelfHeal] Brain call failed: {brain_err}")
                break

            # Extract raw code from LLM response (delete any protocol tags or markdown)
            import re as _re
            fixed_code = fixed_response
            # Get content if tag like [PROTOCOL: PYTHON_EXEC] or [PROTOCOL: SPEAK]
            protocol_match = _re.search(
                r'\[PROTOCOL:\s*PYTHON_EXEC\]\s*(.+)',
                fixed_code, _re.DOTALL | _re.IGNORECASE
            )
            if protocol_match:
                fixed_code = protocol_match.group(1).strip()
            # Clear any Markdown code block
            fixed_code = fixed_code.replace("```python", "").replace("```", "").strip()
            # Kalan protokol etiketlerini temizle
            fixed_code = _re.sub(r'\[/?[A-Z_ :]+PYTHON_EXEC[^\]]*\]', '', fixed_code)
            fixed_code = _re.sub(r'\[/?PROTOCOL[^\]]*\]', '', fixed_code)
            fixed_code = "\n".join(line for line in fixed_code.splitlines() if line.strip()).strip()

            if not fixed_code:
                logger.warning("[PythonSelfHeal] LLM returned empty code, I'm stopping.")
                break

            logger.info(f"[PythonSelfHeal] Corrected code from LLM:\n{fixed_code[:300]}")

            # Run corrected code
            node.argument = fixed_code
            broken_code = fixed_code  # Update for next iteration

            try:
                new_result = await self.executor.execute_tool(
                    "PYTHON_EXEC",
                    fixed_code,
                    engine_context=context
                )
            except Exception as exec_err:
                logger.error(f"[PythonSelfHeal] Fixed code execute error: {exec_err}")
                break

            if new_result.success:
                logger.info(f"[PythonSelfHeal] Trial successfully fixed in {attempt}.")
                await self.io_bridge.speak("I fixed the code and ran it successfully Sir.")
                return new_result
            else:
                current_result = new_result

        # All trials sold out
        logger.error("[PythonSelfHeal] All fix attempts fail.")
        await self.io_bridge.speak(
            "Sir, I couldn't fix the code despite several attempts."
            "Could you please describe the task in more detail?"
        )
        return current_result

    async def replan(self, task_state, old_plan, failed_node, error_msg: str) -> Optional[ExecutionPlan]:
        replan_prompt = (
            f"MISSION FAILED: {error_msg}.\n"
            f"Mevcut durum: {old_plan.get_context_summary()}\n"
            f"Completed step results: {task_state.get_results()}\n"
            f"Generate a new plan."
        )
        try:
            new_response = await self.brain.think(replan_prompt)
            return parse_plan(new_response)
        except: return None

    async def detect_and_parse_plan(self, response: str, user_input: str) -> Optional[ExecutionPlan]:
        if "PLAN" in response.upper() or "```json" in response:
            plan = parse_plan(response)
            if plan:
                plan.original_request = user_input
                return plan
        return None

    def _build_context(self, task_state) -> dict:
        ctx = {
            "task_id":            task_state.id,
            "last_whatsapp_num":  self.last_whatsapp_num,
            "last_whatsapp_time": self.last_whatsapp_time,
            "last_active_file":   self.last_active_file,
            "step_results":       task_state.get_results(),
            "io_bridge":          self.io_bridge,
            "brain":              self.brain,
            "memory":             self.memory,
            "plan_executor":      self,
            "original_request":   getattr(task_state, 'goal', "")
        }
        if hasattr(self, 'scheduler') and self.scheduler:
            ctx["scheduler"] = self.scheduler
        return ctx

    def _fuzzy_match_contact(self, name_target: str, contacts: dict) -> list:
        matched = []
        name_clean = str(name_target).lower().strip()
        for c_name, c_num in contacts.items():
            if name_clean in c_name.lower() or c_name.lower() in name_clean:
                matched.append((c_name, c_num))
        return matched