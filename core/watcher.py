import asyncio
import logging
import uuid
from datetime import datetime

logger = logging.getLogger("JARVIS.Watcher")


class ProactiveWatcher:
    """[10/10 v2] J.A.R.V.I.S. Autonomous Guard Module — Adaptive Vision + Behavior Calibration

    What's New (v2):
    ──────────────────────────────── ─────────────────────────────────
    [4] VISION “CONTINUOUS ANALYSIS” — Dynamic Range System:
        + Automatic accelerating/decelerating cycle as needed instead of fixed 5 minutes
        + The interval is shortened when a change is detected on the screen (quick observation)
        + The interval is extended when the screen remains stable (resource saving)
        + Min/max range limits are maintained for safety

    [5] PROACTIVE BEHAVIOR CALIBRATION:
        + Talk/silence threshold finely adjusted
        + Proactivity level varies depending on time zone
        + Consecutive silence counter: shares observation even if silenced for too long
        + Strict rules to prevent unnecessary chatter

    Available (protected):
    + Vision result is sent to GUI as a card
    + Summary card added to Mission Control when proactive action occurs
    + HUD visual status is updated via Vision status callback"""

    # ── Dynamic Range Constants ───────────────────── ─────────────────────
    MIN_INTERVAL_SECONDS = 900       # Minimum observation interval: 15 minutes (Limit protection)
    MAX_INTERVAL_SECONDS = 1800      # Maximum observation interval: 30 minutes
    DEFAULT_INTERVAL_SECONDS = 900   # Default start: 15 minutes

    # Acceleration/deceleration multipliers
    SPEEDUP_FACTOR = 0.6    # Reduce interval to 60% when change is detected
    SLOWDOWN_FACTOR = 1.3   # If stable, range increases to 130%

    # Similarity threshold — if there is a difference below this ratio, it is considered "no change"
    SIMILARITY_THRESHOLD = 0.85

    # [V13.1] API call skip threshold on stable screen
    # brain.think() WILL NOT BE CALLED after so many consecutive stable loops
    STABLE_SKIP_THRESHOLD = 3

    # ── Behavior Calibration Constants ───────────────────────────────────
    MAX_CONSECUTIVE_SILENCE = 6     # Share observation summary if 6 consecutive cycles go silent
    
    # Time zone based proactivity levels
    PROACTIVITY_LEVELS = {
        "quiet":    {"hours": range(0, 8),   "speak_threshold": "critical_only"},
        "morning":  {"hours": range(8, 12),  "speak_threshold": "helpful"},
        "active":   {"hours": range(12, 18), "speak_threshold": "normal"},
        "evening":  {"hours": range(18, 22), "speak_threshold": "moderate"},
        "late":     {"hours": range(22, 24), "speak_threshold": "low"},
    }

    def __init__(self, engine):
        self.engine = engine
        self._running = False

        # Dynamic range status
        self._current_interval = self.DEFAULT_INTERVAL_SECONDS
        self._last_screen_summary: str = ""
        self._consecutive_stable = 0       # Sequential stable loop counter
        self._consecutive_silence = 0      # Consecutive silence timer
        self._total_observations = 0       # Total number of observations
        self._total_actions = 0            # Total number of proactive actions
        # NOTE: JarvisVision removed — watcher uses active-window detection, not screenshots

    async def run(self):
        self._running = True
        logger.info(
            f"[WATCHER] Autonomous Watchman launched."
            f"(Dynamic range: {self.MIN_INTERVAL_SECONDS}s – {self.MAX_INTERVAL_SECONDS}s)"
        )

        while self._running:
            try:
                # Use dynamic range
                await asyncio.sleep(self._current_interval)
                if not self._running:
                    break

                logger.info(
                    f"[WATCHER] Proactive thought cycle triggered."
                    f"(Range: {self._current_interval:.0f}s |"
                    f"Observation #{self._total_observations + 1})"
                )
                await self._trigger_proactive_thought()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WATCHER] Loop Error: {e}")
                await asyncio.sleep(60)

    async def _trigger_proactive_thought(self):
        now = datetime.now()
        self._total_observations += 1

        # 1. Night mode — complete silence
        if now.hour < 8 or now.hour >= 23:
            logger.info("[WATCHER] Night mode. Proactive action has been suspended.")
            # Increase the range to maximum in night mode
            self._current_interval = self.MAX_INTERVAL_SECONDS
            return

        # 2. Get last memory
        recent_memory = "MEMORY IS EMPTY"
        if self.engine.memory:
            recent_memory = str(self.engine.memory.get_recent_memories(3))
            if len(recent_memory) > 2000:
                recent_memory = "... " + recent_memory[-2000:]

        #3. Screen Analysis (Local and Free Window Tracking)
        logger.info("[WATCHER] Observation in progress (Local Window Analysis)...")
        # We read the active window instead of taking a screenshot to avoid exhausting the API quota
        situation = {"active_app": "Unknown", "active_window": "Unknown"}
        if hasattr(self.engine, 'cognitive_core') and self.engine.cognitive_core:
            situation = self.engine.cognitive_core.world_state.get_situation_assessment()
            
        active_app = situation.get("active_app", "Unknown")
        active_win = situation.get("active_window", "Unknown")
        
        if active_app != "Unknown" and active_win != "Unknown":
            screen_summary = f"The user is currently working on window '{active_win}' in application '{active_app}'."
        else:
            screen_summary = "There are no obvious applications on the screen or on the desktop."

        # ── [IMPROVEMENT] DYNAMIC RANGE CALCULATION ─────────────────────────
        screen_changed = self._detect_screen_change(screen_summary)
        self._adjust_interval(screen_changed)

        # Pass the screen analysis result to the GUI Vision Status indicator
        if hasattr(self.engine, 'io_bridge') and self.engine.io_bridge:
            try:
                interval_info = f"[Range: {self._current_interval:.0f}s]"
                self.engine.io_bridge.update_vision_status(
                    summary=(screen_summary + interval_info) if screen_summary else "No meaningful content was found on the screen.",
                    screenshot_path=None
                )
            except Exception as e:
                logger.warning(f"[WATCHER] Vision status could not be sent: {e}")

        # ── [V13.1] STABLE SCREEN PROTECTION — API Limit Shield ─────────
        # If the screen has not been changed for a long time (game, movie, AFK, etc.)
        # DO NOT call brain.think() — Maintain API quota
        if self._consecutive_stable >= self.STABLE_SKIP_THRESHOLD:
            logger.info(
                f"[WATCHER] Display {self._consecutive_stable} is loop stable —"
                f"API call skipped (limit protection). Range: {self._current_interval:.0f}s"
            )
            # Only send local observation cards, no API calls
            if screen_summary and len(screen_summary) > 30:
                self._send_vision_card(now, screen_summary + "[API Bypassed — Stable]", silent=True)
            return

        # ── [5] BEHAVIOR CALIBRATION — Proactivity Level ────────────
        proactivity = self._get_proactivity_level(now)

        # 4. Autonomous Prompt — Calibrated
        watcher_prompt = self._build_calibrated_prompt(
            now, screen_summary, recent_memory, proactivity
        )

        try:
            response = await self.engine.brain.think(watcher_prompt, bypass_history=True)

            silence_variants = ["[SILENCE]", "SILENCE"]
            if any(v in response.upper() for v in silence_variants):
                self._consecutive_silence += 1
                logger.info(
                    f"[WATCHER] The watchman chose to remain silent."
                    f"(Successive silence: {self._consecutive_silence}/{self.MAX_CONSECUTIVE_SILENCE})"
                )

                # [5] Calibration: Share observation summary if silent for too long
                if self._consecutive_silence >= self.MAX_CONSECUTIVE_SILENCE:
                    if screen_summary and len(screen_summary) > 30:
                        self._send_vision_card(now, screen_summary, silent=True)
                        self._consecutive_silence = 0  # Reset counter
                elif screen_summary and screen_summary.strip() and len(screen_summary) > 30:
                    # Send cards also in normal cycle (only if there is content)
                    self._send_vision_card(now, screen_summary, silent=True)
                return

            response = self.engine._sanitize_llm_output(response)
            if not response.strip():
                return

            # Proactive action successful
            self._consecutive_silence = 0
            self._total_actions += 1
            logger.info(
                f"[WATCHER] Watchman took proactive action!"
                f"(Total proactive actions: {self._total_actions})"
            )

            # Add proactive action summary as card to Mission Control
            self._send_watcher_action_card(now, screen_summary, response)

            task_id = str(uuid.uuid4())[:8]
            task_state = self.engine.state_manager.create_task(task_id=task_id, goal="[AUTONOMOUS ACTION]")

            plan = await self.engine.plan_executor.detect_and_parse_plan(response, watcher_prompt)
            if plan:
                await self.engine.plan_executor.execute_plan(task_state, plan)
            else:
                protocol_start = response.find("[PROTOCOL:")
                if protocol_start >= 0:
                    await self.engine.plan_executor.execute_single(task_state, response[protocol_start:])
                else:
                    await self.engine.io_bridge.speak(response)

            self.engine.state_manager.complete_task(task_id)

            # Shorten observation interval after proactive action (active state)
            self._current_interval = max(
                self.MIN_INTERVAL_SECONDS,
                self._current_interval * self.SPEEDUP_FACTOR
            )

        except Exception as e:
            logger.error(f"[WATCHER] Error during proactive thought: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # [4] DYNAMIC RANGE MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_screen_change(self, current_summary: str) -> bool:
        """Determines if there has been a change by comparing the previous and current screen summary.
        It uses simple word-based Jaccard similarity — fast and accurate enough."""
        if not self._last_screen_summary or not current_summary:
            self._last_screen_summary = current_summary or ""
            return True  # First observation, count "change" by default

        prev_words = set(self._last_screen_summary.lower().split())
        curr_words = set(current_summary.lower().split())

        if not prev_words or not curr_words:
            self._last_screen_summary = current_summary
            return True

        intersection = prev_words & curr_words
        union = prev_words | curr_words
        similarity = len(intersection) / len(union) if union else 1.0

        self._last_screen_summary = current_summary

        changed = similarity < self.SIMILARITY_THRESHOLD
        if changed:
            self._consecutive_stable = 0
            logger.info(
                f"[WATCHER] Screen replacement detected!"
                f"(Similarity: {similarity:.2f} < {self.SIMILARITY_THRESHOLD})"
            )
        else:
            self._consecutive_stable += 1
            logger.debug(
                f"[WATCHER] Screen stable. "
                f"(Similarity: {similarity:.2f}, Sequential stable: {self._consecutive_stable})"
            )

        return changed

    def _adjust_interval(self, screen_changed: bool) -> None:
        """Adjusts the observation range according to the screen status.

        If there is change → accelerate (shorten the interval)
        If stable → slow down (extend interval)"""
        if screen_changed:
            new_interval = self._current_interval * self.SPEEDUP_FACTOR
        else:
            new_interval = self._current_interval * self.SLOWDOWN_FACTOR

        # Apply limits
        new_interval = max(self.MIN_INTERVAL_SECONDS, min(self.MAX_INTERVAL_SECONDS, new_interval))

        if new_interval != self._current_interval:
            logger.info(
                f"[WATCHER] Range updated: {self._current_interval:.0f}s → {new_interval:.0f}s"
                f"({'⚡ Sped Up' if screen_changed else '🐢 Slowed Down'})"
            )
        self._current_interval = new_interval

    # ─────────────────────────────────────────────────────────────────────────
    # [5] PROACTIVE BEHAVIOR CALIBRATION
    # ─────────────────────────────────────────────────────────────────────────

    def _get_proactivity_level(self, now: datetime) -> dict:
        """Determines the level of proactivity based on time zone.
        Each level has different speech thresholds."""
        for level_name, level_data in self.PROACTIVITY_LEVELS.items():
            if now.hour in level_data["hours"]:
                return {"name": level_name, **level_data}
        return {"name": "normal", "speak_threshold": "normal", "hours": range(0, 24)}

    def _build_calibrated_prompt(self, now: datetime, screen_summary: str,
                                  recent_memory: str, proactivity: dict) -> str:
        """[5] Creates an autonomous prompt with behavioral calibration applied.

        Calibration Rules:
        ───────────────────────────── ─────────────────────────────
        critical_only : Speak ONLY if there is a system error, crash, or emergency
        low : Speak only if there is a really important reminder or serious error
        moderate: Speak if there is important information or useful observation.
        helpful: Can kindly ask for helpful ideas
        normal: Standard proactivity—error, reminder, suggestion"""
        level_name = proactivity.get("name", "normal")
        threshold = proactivity.get("speak_threshold", "normal")

        # Calibration instructions — different tone and threshold for each level
        calibration_rules = {
            "critical_only": (
                "⚠️ CRITICAL MODE: Speak ONLY when:\n"
                "- If there is an ERROR/CRASH/BLUE SCREEN on the screen\n"
                "- If an urgent reminder (alarm) has been triggered\n"
                "Apart from these, MUST write [SILENCE]. Never disturb the user at night."
            ),
            "low": (
                "🔇 LOW PROACTIVITY: Your speaking threshold is too high.\n"
                "Speak only when:\n"
                "- If there is a critical error or security warning\n"
                "- If there is an urgent reminder that is due\n"
                "At late hours the user is probably resting. DO NOT provide unnecessary information."
            ),
            "moderate": (
                "🔉 MEDIUM PROACTIVITY: Work in balance mode.\n"
                "Speak if:\n"
                "- If you have a clear and concrete observation that will be useful to the user\n"
                "- If you detected an error and can suggest a solution\n"
                "- If there is a reminder due\n"
                "DO NOT make general observations or conversations. Speak concisely."
            ),
            "helpful": (
                "🔊 AUXILIARY MODE: Morning energy, you can be gently helpful.\n"
                "Speak if:\n"
                "- If the user is working on something and you have a helpful tip\n"
                "- If there is an error, warning or reminder\n"
                "- If you have a short motivating observation\n"
                "BUT: Unnecessary chatter, unnecessary praise or empty repetitions are PROHIBITED."
            ),
            "normal": (
                "🎯 STANDARD PROACTIVITY: Normal working hours.\n"
                "Speak if:\n"
                "- If you detected an error on the screen and can suggest a solution\n"
                "- If there is any concrete observation/information that is useful to the user\n"
                "- If there is a reminder due\n"
                "- If the user has finished a video/task and it makes sense to congratulate\n"
                "SPEAKING if:\n"
                "- If the screen is normal and stable\n"
                "- Unless you have something really valuable to say\n"
                "- If there has been no significant change since your last conversation"
            ),
        }

        calibration = calibration_rules.get(threshold, calibration_rules["normal"])

        # Statistics summary
        stats_line = (
            f"[WATCHER STATISTICS]"
            f"Total observations: {self._total_observations} |"
            f"Total proactive actions: {self._total_actions} | "
            f"Consecutive silence: {self._consecutive_silence} |"
            f"Current range: {self._current_interval:.0f}s |"
            f"Proactivity level: {level_name.upper()}"
        )

        watcher_prompt = (
            "[AUTONOMOUS OBSERVATION MODE]\n"
            f"Current time: {now.strftime('%H:%M')}. You are the autonomous 'Watcher' module of J.A.R.V.I.S.\n"
            "The user hasn't asked you anything yet. You woke up in the background on your own initiative.\n\n"

            f"[CURRENT SCREEN STATUS]\nThe user's screen currently has this: {screen_summary}\n\n"

            f"[LAST SAVED MEMORY]\n{recent_memory}\n\n"

            f"[BEHAVIOR CALIBRATION — {level_name.upper()} MODE]\n"
            f"{calibration}\n\n"

            f"{stats_line}\n\n"

            "YOUR MISSION:\n"
            "1. Check the screen status. If the user receives an ERROR or needs help in a critical situation"
            "Proactively speak up and offer help.\n"
            "2. Look at memory. If there's something urgent you need to remind, let me know.\n"
            "3. If you have an idea that is really important and will be useful to the user, use [PROTOCOL: SPEAK]"
            "Intercede gently.\n"
            "4. If everything is normal and there is NO issue important enough to bother you, don't say anything and"
            "ONLY write [SILENCE].\n\n"

            "⚠️ CALIBRATION RULES (MUST BE STRICTLY FOLLOWED):\n"
            "• NEVER use [PROTOCOL: SYSTEM_SHUTDOWN] or [PROTOCOL: SYSTEM_POWER]. You are a background watcher, do not shut down the system proactively.\n"
            "• NEVER make unnecessary chatter. Empty sentences such as 'it's a nice day', 'everything is fine' are PROHIBITED.\n"
            "• NEVER give unnecessary reports such as 'I checked your screen, it's fine'.\n"
            "• NEVER share technical details (which module is running, API status, etc.)\n"
            "• DO NOT REPEAT what you said in the previous cycle.\n"
            "• If you are going to speak, limit yourself to 1-2 SENTENCES. Long conversations PROHIBITED.\n"
            "• If in doubt, ALWAYS choose [SILENCE]. Stay quiet rather than raise a false alarm."
        )

        return watcher_prompt

    # ─────────────────────────────────────────────────────────────────────────
    # GUI CARD SEND (Protected functions)
    # ─────────────────────────────────────────────────────────────────────────

    def _send_vision_card(self, now: datetime, screen_summary: str, silent: bool = False):
        """[10/10] Sends screen analysis summary to Mission Control.
        silent=True: analysis report only (non-action observation)"""
        if not (hasattr(self.engine, 'io_bridge') and self.engine.io_bridge):
            return
        try:
            prefix = "🔍 Observation Summary" if silent else "👁 Screen Analysis"
            interval_str = f"{self._current_interval:.0f}s"
            title = f"{prefix}  —  {now.strftime('%H:%M')}  [{interval_str}]"
            content = screen_summary[:400] + ("..." if len(screen_summary) > 400 else "")
            self.engine.io_bridge.display_card(title, content)
        except Exception as e:
            logger.warning(f"[WATCHER] Vision card could not be sent: {e}")

    def _send_watcher_action_card(self, now: datetime, screen_summary: str, action_response: str):
        """[10/10] Adds summary card to Mission Control when proactive action occurs."""
        if not (hasattr(self.engine, 'io_bridge') and self.engine.io_bridge):
            return
        try:
            title = f"⚡ Proactive Action  —  {now.strftime('%H:%M')}"
            screen_part = (screen_summary[:120] + "...") if len(screen_summary) > 120 else screen_summary
            action_part = (action_response[:200] + "...") if len(action_response) > 200 else action_response
            content = (
                f"📺 Observation: {screen_part}\n\n"
                f"🤖 Response: {action_part}"
            )
            self.engine.io_bridge.display_card(title, content)
        except Exception as e:
            logger.warning(f"[WATCHER] Failed to send action card: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # CONTROL
    # ─────────────────────────────────────────────────────────────────────────

    def stop(self):
        self._running = False

    def get_stats(self) -> dict:
        """Returns Watcher statistics (for debug/GUI)."""
        return {
            "current_interval": self._current_interval,
            "total_observations": self._total_observations,
            "total_actions": self._total_actions,
            "consecutive_silence": self._consecutive_silence,
            "consecutive_stable": self._consecutive_stable,
            "running": self._running,
        }