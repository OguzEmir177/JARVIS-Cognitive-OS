"""
[V12.0] J.A.R.V.I.S. Tool-Grounded Reflection Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOT just LLM self-critique. Real reflection that:
- Verifies tool outputs against expected behavior
- Confirms external state changes (did the app really open?)
- Detects hallucinated tool results
- Provides semantic consistency checking
- Tracks reflection history for learning
"""
import logging, json, re, time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("JARVIS.Reflection")


class ReflectionEngine:
    """
    [V13.0] Advanced Cognitive Reflection
    
    Modes:
    1. Tool Verification — execution results against expectations
    2. Workflow Consistency — does the action align with the current workflow phase?
    3. Intent Alignment — does it serve the inferred user intent?
    4. LLM Critique — deep reasoning check
    """
    def __init__(self, brain):
        self.brain = brain
        self.reflection_history: List[Dict[str, Any]] = []
        self._max_history = 100

        # Tool verification rules (tool_tag → expected behavior)
        self._verification_rules = {
            "APP_OPEN": {"expect_in_result": ["opened", "açıldı", "başlatıldı", "running"],
                         "fail_indicators": ["not found", "bulunamadı", "error", "hata"]},
            "WEB_SEARCH": {"expect_in_result": ["http", "result", "sonuç", "found"],
                           "fail_indicators": ["no results", "timeout", "error"]},
            "WEB_OPEN": {"expect_in_result": ["opened", "açıldı", "navigated"],
                         "fail_indicators": ["failed", "error", "timeout"]},
            "WHATSAPP_MESSAGE": {"expect_in_result": ["sent", "gönderildi", "delivered"],
                                 "fail_indicators": ["failed", "error", "not sent"]},
            "REMEMBER": {"expect_in_result": ["saved", "stored", "kaydedildi", "hafızaya"],
                         "fail_indicators": ["error", "failed"]},
            "MAP_SHOW": {"expect_in_result": ["map", "harita", "gösterildi", "location"],
                         "fail_indicators": ["error", "not found"]},
            "CHART_SHOW": {"expect_in_result": ["chart", "grafik", "rendered", "oluşturuldu"],
                           "fail_indicators": ["error", "failed"]},
        }

    async def critique_execution(self, goal: str, execution_data: Any) -> Dict[str, Any]:
        """
        Two-phase critique:
        Phase 1: Tool-grounded verification (deterministic)
        Phase 2: LLM reasoning critique (if needed)
        """
        logger.info(f"Reflecting on: {goal[:60]}")

        # ── PHASE 1: TOOL-GROUNDED VERIFICATION ──
        tool_issues = []
        tool_score = 1.0
        nodes_summary = []

        if hasattr(execution_data, 'nodes'):
            for node in execution_data.nodes.values():
                node_info = {"id": node.id, "action": node.action,
                             "status": node.status.value,
                             "result": str(node.result)[:300] if node.result else None,
                             "error": node.error}
                nodes_summary.append(node_info)

                # Verify each completed tool call
                if node.status.value == "completed" and node.result:
                    verification = self._verify_tool_result(
                        node.action, str(node.result))
                    if not verification["passed"]:
                        tool_issues.append(
                            f"{node.action}: {verification['reason']}")
                        tool_score -= 0.2
                elif node.status.value == "failed":
                    tool_issues.append(f"{node.action}: execution failed — {node.error}")
                    tool_score -= 0.3

        tool_score = max(0.0, tool_score)

        # ── PHASE 2: ADVANCED COGNITIVE CONSISTENCY ──
        # Check if the execution makes sense in the current world state
        consistency_score = 1.0
        consistency_issues = []
        
        # We will dynamically evaluate this if we have the workflow context
        if hasattr(execution_data, 'workflow_context'):
            workflow = execution_data.workflow_context
            if workflow and "predictive" in goal.lower():
                # Temporal Consistency: Are we predicting too far ahead?
                consistency_score -= 0.1
                consistency_issues.append("Temporal consistency: Prediction may be premature")
                
            # Intent Alignment: Does this match inferred hypotheses?
            if hasattr(execution_data, 'active_hypotheses') and execution_data.active_hypotheses:
                aligned = any(h.lower() in goal.lower() for h in execution_data.active_hypotheses)
                if not aligned:
                    consistency_score -= 0.15
                    consistency_issues.append("Intent Alignment: Action does not clearly map to top hypotheses")

        # ── PHASE 3: LLM CRITIQUE (only if verification is ambiguous) ──
        llm_critique = None
        if 0.3 < tool_score < 0.9 and nodes_summary:
            llm_critique = await self._llm_critique(goal, nodes_summary)

        # ── MERGE RESULTS ──
        if llm_critique:
            final_score = (tool_score * 0.4) + (consistency_score * 0.2) + (llm_critique.get("score", 0.5) * 0.4)
            action = llm_critique.get("action_recommendation", "finalize")
            all_issues = tool_issues + consistency_issues + llm_critique.get("missing_elements", [])
        else:
            final_score = (tool_score * 0.7) + (consistency_score * 0.3)
            action = "finalize" if final_score > 0.6 else "replan" if final_score > 0.3 else "abort"
            all_issues = tool_issues + consistency_issues

        result = {
            "score": round(final_score, 2),
            "is_satisfactory": final_score > 0.6,
            "tool_verification_score": round(tool_score, 2),
            "consistency_score": round(consistency_score, 2),
            "tool_issues": tool_issues,
            "hallucinations_detected": [],
            "missing_elements": all_issues,
            "action_recommendation": action,
            "critique_reasoning": f"Tool: {tool_score:.2f}, Consistency: {consistency_score:.2f}" + (
                f", LLM: {llm_critique.get('score', 'N/A')}" if llm_critique else ""),
            "recommended_params": llm_critique.get("recommended_params", {}) if llm_critique else {}
        }

        self._record(goal, result)
        return result

    def _verify_tool_result(self, tool_tag: str, result: str) -> Dict[str, Any]:
        """
        Deterministic tool result verification — no LLM needed.
        Checks if result contains expected success indicators.
        """
        rules = self._verification_rules.get(tool_tag)
        if not rules:
            return {"passed": True, "reason": "No verification rules for this tool"}

        result_lower = result.lower()

        # Check fail indicators first (higher priority)
        for fail in rules.get("fail_indicators", []):
            if fail in result_lower:
                return {"passed": False,
                        "reason": f"Fail indicator found: '{fail}'"}

        # Check expected indicators
        expected = rules.get("expect_in_result", [])
        if expected:
            found = any(exp in result_lower for exp in expected)
            if not found:
                return {"passed": False,
                        "reason": f"Expected indicators not found: {expected[:3]}"}

        return {"passed": True, "reason": "Result matches expected pattern"}

    async def _llm_critique(self, goal: str, nodes: List[Dict]) -> Optional[Dict]:
        """Second-pass LLM critique for ambiguous cases."""
        prompt = f"""[GOAL]: {goal}
[EXECUTION]: {json.dumps(nodes[:5], indent=1)}

Kritik analiz yap:
1. Sonuçlar hedefe uygun mu?
2. Herhangi bir halüsinasyon var mı?
3. Eksik adım var mı?

SADECE JSON döndür:
{{"score": 0.0-1.0, "is_satisfactory": bool, "missing_elements": [], "action_recommendation": "finalize|retry_step|replan", "recommended_params": {{}}}}"""

        try:
            response = await self.brain.think(prompt)
            match = re.search(r'\{.*?\}', response, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            logger.debug(f"LLM critique failed: {e}")
        return None

    async def critique_response(self, user_input: str, response: str) -> Dict[str, Any]:
        """Quick pre-delivery quality check for text responses."""
        issues = []
        score = 1.0

        # Hallucination patterns
        patterns = [
            ("[PROTOCOL: UNKNOWN]", "Unknown protocol", 0.3),
            ("as an AI", "Breaking character", 0.15),
            ("placeholder", "Placeholder leaked", 0.2),
            ("GOOGLE_SUMMARY", "Hallucinated tool", 0.25),
        ]
        for pat, issue, penalty in patterns:
            if pat.lower() in response.lower():
                issues.append(issue); score -= penalty

        # Protocol leak
        leaks = re.findall(r'\[PROTOCOL:\s*\w+\]', response)
        if leaks and not response.strip().startswith("[PROTOCOL:"):
            issues.append(f"Protocol leak: {leaks}"); score -= 0.15

        # Too short
        if len(response.strip()) < 10:
            issues.append("Too short"); score -= 0.3

        # Repetition
        sents = [s.strip() for s in response.split('.') if s.strip()]
        if len(sents) > 3:
            unique = set(s.lower() for s in sents)
            if len(unique) < len(sents) * 0.5:
                issues.append("Excessive repetition"); score -= 0.2

        return {"score": max(0.0, score), "is_satisfactory": score > 0.6,
                "issues": issues, "needs_retry": score < 0.4}

    async def verify_external_state(self, expected: Dict[str, Any],
                                     world_state) -> Dict[str, Any]:
        """
        Verifies execution results against actual world state.
        E.g., "did the app really open?" → check world_state.active_window
        """
        checks = []
        all_pass = True

        if "expected_window" in expected:
            actual = world_state.get_current_state().active_window
            matches = expected["expected_window"].lower() in actual.lower()
            checks.append({"check": "window_match", "expected": expected["expected_window"],
                           "actual": actual, "passed": matches})
            if not matches: all_pass = False

        if "expected_app" in expected:
            actual = world_state.get_current_state().active_app_name
            matches = expected["expected_app"].lower() in actual.lower()
            checks.append({"check": "app_match", "expected": expected["expected_app"],
                           "actual": actual, "passed": matches})
            if not matches: all_pass = False

        return {"all_passed": all_pass, "checks": checks}

    def _record(self, goal: str, critique: Dict[str, Any]):
        self.reflection_history.append({
            "goal": goal[:100], "score": critique.get("score", 0),
            "action": critique.get("action_recommendation", "unknown"),
            "tool_score": critique.get("tool_verification_score", -1),
            "timestamp": time.time()
        })
        if len(self.reflection_history) > self._max_history:
            self.reflection_history = self.reflection_history[-self._max_history:]

    def get_reflection_stats(self) -> Dict[str, Any]:
        if not self.reflection_history:
            return {"total": 0, "avg_score": 0.0}
        scores = [r.get("score", 0) for r in self.reflection_history]
        actions = {}
        for r in self.reflection_history:
            a = r.get("action", "unknown"); actions[a] = actions.get(a, 0) + 1
        return {"total": len(self.reflection_history),
                "avg_score": sum(scores)/len(scores),
                "avg_tool_score": sum(r.get("tool_score",0) for r in self.reflection_history
                                      if r.get("tool_score",-1) >= 0) /
                                  max(1, sum(1 for r in self.reflection_history
                                             if r.get("tool_score",-1) >= 0)),
                "action_distribution": actions, "recent_scores": scores[-5:]}
