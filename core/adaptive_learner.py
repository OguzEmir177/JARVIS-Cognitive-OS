"""[V14.0] J.A.R.V.I.S. Adaptive Learning System
━━━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━━
Autonomous learning engine. Unknown commands of J.A.R.V.I.S.
It allows him to learn on his own and learn from his mistakes.

Capabilities:
    1. Strategy Recording — Records the strategy of successful missions
    2. Unknown Command Learning — Solves and learns unknown commands with LLM
    3. Failure Adaptation — Finds an alternative path after failure
    4. Repeat Detection — Detects commands that the user repeats
    5. Dynamic Skill Synthesis — Turns learned strategies into permanent skills

Architecture:
    AdaptiveLearner
    ├── StrategyStore (JSON-based persistent strategy memory)
    ├── RepeatDetector (short-term command dedup)
    ├── SkillSynthesizer (learned strategies → reusable skills)
    └── LLM Fallback (asks brain for unknown commands)"""

import asyncio
import json
import os
import time
import logging
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("JARVIS.AdaptiveLearner")

STRATEGY_DB_PATH = "memory_db/learned_strategies.json"


@dataclass
class LearnedStrategy:
    """A learned mission strategy."""
    command_pattern: str      # User's original command (normalized)
    tool_chain: List[str]     # Toolchain used [APP_OPEN, WEB_SEARCH, ...]
    arguments: List[str]      # Argument for each tool
    success_count: int = 0    # How many times has it been successful
    failure_count: int = 0    # How many times did it fail
    last_used: float = 0.0    # Expiry time
    created_at: float = 0.0   # Creation time

    @property
    def confidence(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total

    @property
    def is_reliable(self) -> bool:
        """Is the strategy reliable? (at least 2 successes, 70%+ success rate)"""
        return self.success_count >= 2 and self.confidence >= 0.7


class AdaptiveLearner:
    """[V14.0] J.A.R.V.I.S. Autonomous Learning Engine
    
    Usage:
        learner = AdaptiveLearner()
        
        # Save successful strategy
        learner.record_success("open youtube", ["APP_OPEN"], ["youtube"])
        
        # Next time the same command comes
        strategy = learner.find_strategy("open youtube")
        if strategy:
            # Apply strategy directly
            ...
        
        # Learn from LLM for unknown command
        plan = await learner.learn_unknown_command(brain, "record screen", available_tools)"""

    def __init__(self):
        self.strategies: Dict[str, LearnedStrategy] = {}
        self._recent_commands: List[Dict[str, Any]] = []  # Son 10 komut (repeat detection)
        self._max_recent = 10
        self._load_strategies()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  STRATEGY RECORDING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def record_success(self, user_input: str, tools_used: List[str], 
                       arguments: List[str]) -> None:
        """Records the strategy of a successful mission.
        When the same command comes again, this strategy is applied first."""
        key = self._normalize_command(user_input)
        
        if key in self.strategies:
            strategy = self.strategies[key]
            strategy.success_count += 1
            strategy.last_used = time.time()
            # If a different tool chain was used and it was successful, update
            if tools_used != strategy.tool_chain:
                # Prefer the new chain if it is shorter
                if len(tools_used) <= len(strategy.tool_chain):
                    strategy.tool_chain = tools_used
                    strategy.arguments = arguments
        else:
            self.strategies[key] = LearnedStrategy(
                command_pattern=key,
                tool_chain=tools_used,
                arguments=arguments,
                success_count=1,
                last_used=time.time(),
                created_at=time.time(),
            )
        
        self._prune_strategies()
        self._schedule_save()
        logger.info(f"[LEARNING] Strategy saved: '{key}' → {tools_used}")

    def record_failure(self, user_input: str, tools_used: List[str]) -> None:
        """Saves the failed strategy (to avoid repeating the same path in the future)."""
        key = self._normalize_command(user_input)
        
        if key in self.strategies:
            self.strategies[key].failure_count += 1
            self.strategies[key].last_used = time.time()
            self._prune_strategies()
            self._schedule_save()
            logger.info(f"[LEARNING] Failed strategy recorded: '{key}' (failures={self.strategies[key].failure_count})")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  STRATEGY LOOKUP
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def find_strategy(self, user_input: str) -> Optional[LearnedStrategy]:
        """It searches for a learned strategy that matches the user command.
        
        Matching: 
          1. Exact match (normalized)
          2. Fuzzy match (word intersection 60%+)
        
        Returns: LearnedStrategy or None"""
        key = self._normalize_command(user_input)
        
        # 1. Exact match
        if key in self.strategies:
            strategy = self.strategies[key]
            if strategy.is_reliable:
                logger.info(f"[LEARNING] Exact match found: '{key}' → {strategy.tool_chain} (trust={strategy.confidence:.0%})")
                return strategy
        
        # 2. Fuzzy match — word intersection
        input_words = set(key.split())
        if len(input_words) < 2:
            return None
            
        best_match = None
        best_overlap = 0.0
        
        for pattern, strategy in self.strategies.items():
            if not strategy.is_reliable:
                continue
            pattern_words = set(pattern.split())
            if not pattern_words:
                continue
            overlap = len(input_words & pattern_words) / max(len(input_words), len(pattern_words))
            if overlap > 0.6 and overlap > best_overlap:
                best_match = strategy
                best_overlap = overlap
        
        if best_match:
            logger.info(f"[LEARNING] Fuzzy match found: '{key}' ≈ '{best_match.command_pattern}' (overlap={best_overlap:.0%})")
            return best_match
        
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  UNKNOWN COMMAND LEARNING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def learn_unknown_command(self, brain, user_input: str, 
                                     available_tools: List[str]) -> Optional[Dict[str, Any]]:
        """Learns an unknown command by asking LLM.
        
        Called when Iron Dome blocks unknown protocol.
        I asked LLM "how can I do this command with the tools available?" he asks.
        
        Returns:
            {"tool": "APP_OPEN", "argument": "notepad"} or None"""
        tools_list = ", ".join(available_tools)
        
        prompt = (
            f"[SYSTEM INSTRUCTIONS – TOOL SELECTION]\n"
            f"User requested: \"{user_input}\"\n"
            f"Available vehicles: {tools_list}\n\n"
            f"Which tool should you use with which argument to fulfill this request?\n"
            f"Answer ONLY in the following JSON format, do not write anything else:\n"
            f'{{\"tool\": \"TOOL_TAG\", \"argument\": \"argüman\"}}\n'
            f"If it can't be done with any tool: {{\"tool\": \"SPEAK\", \"argument\": \"Bu işlemi yapma yeteneğim henüz yok.\"}}"
        )
        
        try:
            response = await brain.think(prompt, bypass_history=True)
            
            # output JSON
            json_match = re.search(r'\{.*?\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                tool = data.get("tool", "").upper()
                argument = data.get("argument", "")
                
                if tool and tool in available_tools:
                    logger.info(f"[LEARNING] Unknown command resolved: '{user_input}' → {tool} {argument}")
                    
                    # Save learned strategy
                    self.record_success(user_input, [tool], [argument])
                    
                    return {"tool": tool, "argument": argument}
                elif tool == "SPEAK":
                    return {"tool": "SPEAK", "argument": argument}
                    
        except Exception as e:
            logger.warning(f"[LEARNING] Unknown command could not be resolved: {e}")
        
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  REPEAT DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def detect_repeat(self, user_input: str) -> Optional[str]:
        """It checks whether the user repeats the same command in a short time.
        
        As seen in the log: user writes "create whats up.txt", no response,
        15 seconds later it writes again. This means the previous attempt failed.
        
        Returns:
            The task_id of the previous command (if any again) or None"""
        key = self._normalize_command(user_input)
        now = time.time()
        
        # Is there the same command in the last 30 seconds?
        for cmd in reversed(self._recent_commands):
            if now - cmd["time"] > 30:
                break
            if cmd["key"] == key:
                logger.info(f"[LEARNING] DETECTED AGAIN: '{key}' (also entered {now - cmd['time']:.0f}s ago)")
                return cmd.get("task_id")
        
        # Yeni komutu kaydet
        self._recent_commands.append({"key": key, "time": now, "input": user_input})
        if len(self._recent_commands) > self._max_recent:
            self._recent_commands = self._recent_commands[-self._max_recent:]
        
        return None

    def update_recent_task_id(self, user_input: str, task_id: str) -> None:
        """Updates the task_id of the last command (for repeat detection)."""
        key = self._normalize_command(user_input)
        for cmd in reversed(self._recent_commands):
            if cmd["key"] == key:
                cmd["task_id"] = task_id
                break

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SKILL PROMPT GENERATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_learned_rules_prompt(self, limit: int = 10) -> str:
        """Learned strategies can be injected into the LLM prompt
        It also returns format. It is added to Brain's system_injection."""
        reliable = [s for s in self.strategies.values() if s.is_reliable]
        if not reliable:
            return ""
        
        # Choose the most used and most reliable strategies
        reliable.sort(key=lambda s: (-s.success_count, -s.confidence))
        top = reliable[:limit]
        
        lines = ["[LEARNED STRATEGIES]"]
        for s in top:
            tools_str = " → ".join(s.tool_chain)
            lines.append(f"• '{s.command_pattern}' → {tools_str} (success: {s.success_count}x)")
        
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Learning system statistics."""
        total = len(self.strategies)
        reliable = sum(1 for s in self.strategies.values() if s.is_reliable)
        total_successes = sum(s.success_count for s in self.strategies.values())
        total_failures = sum(s.failure_count for s in self.strategies.values())
        
        return {
            "total_strategies": total,
            "reliable_strategies": reliable,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "recent_commands": len(self._recent_commands),
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  INTERNAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _normalize_command(text: str) -> str:
        """Normalizes the command — remove lowercase, unnecessary spaces,
        Simplify Turkish suffixes."""
        text = text.strip().lower()
        # Skip multiple spaces
        text = re.sub(r'\s+', ' ', text)
        # Remove common Turkish suffixes (simple stemming)
        text = re.sub(r"'?[yiiuü]$", "", text)  # "chrome'u" → "chrome"
        text = re.sub(r"'?[yiiuü]n[ıiuü]$", "", text)  # "chrome'unu" → "chrome"
        return text.strip()

    def _prune_strategies(self, max_strategies: int = 200) -> None:
        """Prunes out the least used/untrusted strategies to prevent Memory Leak."""
        if len(self.strategies) > max_strategies:
            # Sort by reliability and expiration time
            sorted_strats = sorted(
                self.strategies.values(), 
                key=lambda s: (s.is_reliable, s.last_used), 
                reverse=True
            )
            self.strategies = {s.command_pattern: s for s in sorted_strats[:max_strategies]}

    def _load_strategies(self) -> None:
        """Loads the strategy database from file (Fail-Fast)."""
        try:
            if os.path.exists(STRATEGY_DB_PATH):
                with open(STRATEGY_DB_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, sdata in data.items():
                        self.strategies[key] = LearnedStrategy(**sdata)
                logger.info(f"[LEARNING] {len(self.strategies)} strategy loaded.")
        except json.JSONDecodeError as e:
            logger.error(f"[LEARNING] Strategy DB is corrupt (JSON error): {e} — Starting clean.")
        except Exception as e:
            logger.error(f"[LEARN] Critical error loading strategy: {e}")

    def _save_strategies(self) -> None:
        """Saves the strategy database to file (synchronous — must be called with run_in_executor)."""
        try:
            os.makedirs(os.path.dirname(STRATEGY_DB_PATH), exist_ok=True)
            data = {}
            for key, strategy in self.strategies.items():
                data[key] = asdict(strategy)
            with open(STRATEGY_DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # debug→error: Never swallow disk write errors silently (Fail-Fast principle)
            logger.error(f"[LEARNING] ERROR saving strategy: {e}")

    def _schedule_save(self) -> None:
        """[V14.1] Async-Safe Disk Write Scheduler.
        If there is an event loop, it assigns I/O to the ThreadPool (prevents event-loop blocking).
        If there is no loop (test/startup), it runs directly synchronously."""
        try:
            loop = asyncio.get_running_loop()
            # In an async context: throw I/O to thread pool
            loop.run_in_executor(None, self._save_strategies)
        except RuntimeError:
            # No event loop (e.g. test environment, __init__) — write synchronous
            self._save_strategies()
