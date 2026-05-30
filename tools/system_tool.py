"""[V8.2 ARMORED] J.A.R.V.I.S. System Tools
━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━
WhatsApp and system tools.

[V8.2] _send_direct Fixes:
    - reading contacts.json is now in run_in_executor (async-safe blocking I/O)
    - Exceptions print full stack trace with logger.error + exc_info=True
    - NativeOps.send_whatsapp_message is awaited correctly (it was, preserved)"""

import asyncio
import json
import logging
import os
import re
import time
import subprocess

from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.SystemTools")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WhatsAppTool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WhatsAppTool(BaseTool):
    name              = "whatsapp_message"
    description       = "Sends messages via WhatsApp. Format: Recipient|Message or just Recipient (to ask for the message)"
    protocol_tag      = "WHATSAPP_MESSAGE"
    parameters        = {
        "target": {
            "type": "string",
            "description": "Recipient|Message or just Recipient",
        }
    }
    domain            = "web"
    latency_ms        = 8000
    reliability_score = 0.95
    requires_interaction = True
    #pre_speak = "WhatsApp message is being sent via armored protocol, Sir."

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        """[V8.2 FIXED] Execute method compatible with Engine (Executor) signature."""
        try:
            # Parameter extraction (Params is always dictionary)
            target = params.get("target", "") if isinstance(params, dict) else str(params)
            target = target.strip()

            if not target:
                return ToolResult(
                    success=False, verified=False, error="Fail",
                    message="WhatsApp recipient not specified.",
                    speak="Sir, I couldn't figure out who to send a message to.",
                )

            # Scenario 1: Recipient|Message format
            if "|" in target:
                parts = target.split("|", 1)
                recipient = parts[0].strip()
                message   = parts[1].strip() if len(parts) > 1 else ""
            else:
                recipient = target.strip()
                # Clear non-numeric pure name (if only name is entered)
                clean_rec = re.sub(r"[\+]?\d{7,}", "", recipient).strip().strip(" .,;:-")
                if clean_rec:
                    recipient = clean_rec
                message = ""

            if not recipient:
                return ToolResult(
                    success=False, verified=False, error="Fail",
                    message="Recipient name could not be resolved.",
                    speak="Sir, I couldn't find a valid buyer.",
                )

            # Check number
            loop = asyncio.get_running_loop()
            phone_number = await loop.run_in_executor(
                None, self._resolve_phone_number, recipient
            )

            phone_clean = re.sub(r"[^\d\+]", "", phone_number)
            is_valid = bool(phone_clean and len(phone_clean) >= 7)

            if not phone_number or not is_valid:
                return ToolResult(
                    success=False, verified=False, error="Fail",
                    message="Unknown person or invalid number.",
                    speak=f"{recipient} was not found in my directory. Can you share your number?",
                    next_action="REQUEST_CONTACT_NUMBER",
                    data={"unknown_name": recipient}
                )

            if message:
                return await self._send_direct(recipient, message, engine_context)
                
            return ToolResult(
                success=True, verified=True,
                message=f"WhatsApp dictation mode launched: {recipient}",
                speak=f"Say your message for {recipient}, Sir.",
                next_action="START_DICTATION",
                data={"recipient": recipient},
            )

        except Exception as e:
            # CRITICAL ERROR LOG (Black Box)
            import traceback
            import os
            hata_yolu = os.path.join(os.getcwd(), "WHATSAPP_HATA.txt")
            with open(hata_yolu, "w", encoding="utf-8") as f:
                f.write(f"--- EXECUTE CRITICAL ERROR [{time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
                f.write(traceback.format_exc())
            
            logger.error(f"WhatsAppTool.execute Crash: {e}", exc_info=True)
            return ToolResult(
                success=False, verified=False, error="Fail",
                message=f"Critical execute error: {e}",
                speak="Sir, an internal error has occurred in the WhatsApp module."
            )

    async def _send_direct(
        self, recipient: str, message: str, engine_context: dict = None
    ) -> ToolResult:
        """[V8.2 ARMORED] Direct message sending."""
        from tools.utils.native_ops import NativeOps
        loop = asyncio.get_running_loop()

        try:
            # Google Summary Protection (1000 characters)
            if len(message) > 1000:
                message = message[:1000] + "... [J.A.R.V.I.S. because the message is too long. abbreviated by]"

            # Move blocking I/O (contacts.json) operation to executor
            phone_number = await loop.run_in_executor(
                None, self._resolve_phone_number, recipient
            )

            logger.info(f"Triggering WhatsApp Send: {recipient} ({phone_number})")

            # NativeOps asynchronous URL protocol call
            success = await NativeOps.send_whatsapp_message(phone_number, message)

            if success:
                return ToolResult(
                    success=True, verified=True,
                    message=f"WhatsApp message delivered: {recipient}",
                    speak=f"Your message has been successfully delivered to {recipient}, Sir."
                )
            
            return ToolResult(
                success=False, verified=False, error="Fail",
                message="WhatsApp protocol (NativeOps) failed.",
                speak="Sir, message could not be sent. WhatsApp application did not respond."
            )

        except Exception as e:
            # CRITICAL ERROR LOG (Black Box)
            import traceback
            import os
            hata_yolu = os.path.join(os.getcwd(), "WHATSAPP_HATA.txt")
            with open(hata_yolu, "w", encoding="utf-8") as f:
                f.write(f"--- _SEND_DIRECT CRITICAL ERROR [{time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
                f.write(traceback.format_exc())

            logger.error(f"WhatsAppTool._send_direct Crash: {e}", exc_info=True)
            return ToolResult(
                success=False, verified=False, error="Fail",
                message=f"Submission error: {e}",
                speak="Sir, an error occurred while sending the message."
            )

    def _resolve_phone_number(self, recipient: str) -> str:
        """Decodes number from contacts.json."""
        import json
        import os

        # If the recipient is already a number (starts with +), return directly
        if recipient.startswith("+") or (recipient.isdigit() and len(recipient) > 9):
            return recipient

        contacts_path = os.path.join(os.getcwd(), "contacts.json")
        if not os.path.exists(contacts_path):
            return recipient

        try:
            with open(contacts_path, "r", encoding="utf-8") as f:
                contacts = json.load(f)
                for name, num in contacts.items():
                    if recipient.lower() in name.lower():
                        return num
        except Exception as e:
            logger.warning(f"Directory reading error: {e}")
            
        return recipient
        """Returns number by name from contacts.json.

        This method is called in SYNCHRONOUS — run_in_executor.
        If it is not found in the directory, it returns the recipient value as is.
        (number may have been entered directly).

        Args:
            recipient: Contact name ("My Sister") or phone number ("+905551234567")

        Returns:
            Parsed phone number string"""
        contacts_path = os.path.abspath("contacts.json")

        if not os.path.exists(contacts_path):
            logger.debug(
                f"[WhatsApp] contacts.json not found: {contacts_path} —"
                f"'{recipient}' is used as a number."
            )
            return recipient

        try:
            with open(contacts_path, "r", encoding="utf-8") as f:
                contacts: dict = json.load(f)

            # Try exact match first (case insensitive)
            recipient_lower = recipient.lower()
            for name, number in contacts.items():
                if name.lower() == recipient_lower:
                    logger.debug(f"[WhatsApp] Exact match: '{recipient}' → '{number}'")
                    return str(number)

            # Partial match (ex: "my sister" → "Big Sister")
            for name, number in contacts.items():
                if recipient_lower in name.lower() or name.lower() in recipient_lower:
                    logger.debug(f"[WhatsApp] Partial match: '{recipient}' → '{name}' → '{number}'")
                    return str(number)

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[WhatsApp] Failed to read contacts.json: {e!r}")

        # Not found in the directory → count the entered value as a number
        logger.debug(f"[WhatsApp] Not found in contacts: '{recipient}' — used as a number.")
        return recipient


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WhatsAppDeleteTool (unchanged)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WhatsAppDeleteTool(BaseTool):
    """Deletes the last WhatsApp message."""

    name              = "whatsapp_delete"
    description       = "Deletes the last message on WhatsApp"
    protocol_tag      = "WHATSAPP_DELETE"
    parameters        = {}
    domain            = "web"
    latency_ms        = 3000
    reliability_score = 0.60

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        ctx       = engine_context or {}
        last_num  = ctx.get("last_whatsapp_num")
        last_time = ctx.get("last_whatsapp_time", 0)

        if not last_num:
            return ToolResult(
                success=False, verified=False, error="Fail",
                message="No message found to delete.",
                speak="Sir, I couldn't find a message to delete.",
            )

        if time.time() - last_time > 300:
            return ToolResult(
                success=False, verified=False, error="Fail",
                message="Son mesaj 5 dakikadan eski.",
                speak="Sir, the last message is too old, deletion is not safe.",
            )

        try:
            from tools.utils.native_ops import NativeOps

            await asyncio.get_running_loop().run_in_executor(
                None, NativeOps.kill_app, "WhatsApp"
            )
            return ToolResult(
                success=True, verified=True,
                message="Son mesaj silindi (V8.2 simplified).",
                speak="Son mesaj silindi Efendim.",
                next_action="CLEAR_LAST_HISTORY",
            )
        except Exception as e:
            logger.error(f"[WhatsApp Delete] Deletion error: {e!r}", exc_info=True)
            return ToolResult(
                success=False, verified=False, error="Fail",
                message=f"Delete error: {e!r}",
                speak="Efendim, mesaj silinemedi.",
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#VisionTool (unchanged)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class VisionTool(BaseTool):
    """Screenshot analysis."""

    name              = "vision_analyze"
    description       = "Analyzes the screen"
    protocol_tag      = "VISION"
    parameters        = {}
    domain            = "system"
    latency_ms        = 5000
    reliability_score = 0.90
    pre_speak         = "Please switch to the window to analyze, I get the image within 3 seconds."

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        import asyncio
        # We give the user 3 seconds to Alt+Tab
        await asyncio.sleep(3)
        
        try:
            from core.vision import JarvisVision

            vision   = JarvisVision()
            analysis = await asyncio.get_running_loop().run_in_executor(
                None, vision.analyze_screen
            )
            if analysis:
                return ToolResult(
                    success=True,
                    verified=True,
                    message="Analyzed.",
                    data={"raw_analysis": analysis},
                    next_action="VISION_INTERPRET",
                )
            return ToolResult(
                success=False,
                verified=False,
                error="Fail",
                message="Unsuccessful.",
                speak="Sir, I couldn't analyze the screen.",
            )
        except Exception as e:
            logger.error(f"[Vision] Analysis error: {e!r}", exc_info=True)
            return ToolResult(
                success=False,
                verified=False,
                error="Fail",
                message=str(e),
                speak="Sir, my vision has encountered a problem.",
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#StressTestTool (unchanged)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StressTestTool(BaseTool):
    """Stres testi."""

    name              = "stress_test"
    description       = "Runs a stress test"
    protocol_tag      = "STRESS_TEST"
    parameters        = {}
    domain            = "system"

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        return ToolResult(
            success=True,
            verified=True,
            message="It has been launched.",
            next_action="RUN_STRESS_TEST",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TabKillTool (unchanged)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TabKillTool(BaseTool):
    """Closes the tab."""

    name              = "tab_kill"
    description       = "closes tab"
    protocol_tag      = "TAB_KILL"
    parameters        = {}
    domain            = "desktop"

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        try:
            import pyautogui

            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: (pyautogui.hotkey("ctrl", "w"), time.sleep(0.5)),
            )
            return ToolResult(
                success=True,
                verified=True,
                message="It was closed.",
                speak="Tab closed Sir.",
            )
        except Exception as e:
            logger.error(f"[TabKill] Error: {e!r}", exc_info=True)
            return ToolResult(
                success=False,
                verified=False,
                error="Fail",
                message=str(e),
                speak="Sir, the tab could not be closed.",
            )

class SpeakTool(BaseTool):
    """[V9.1] Jarvis to user via plaintext/voice without using tools
    The basic communication tool that allows people to respond.
    Usage: [PROTOCOL: SPEAK] <message>"""
    name = "Speech and Answer"
    protocol_tag = "SPEAK"
    domain = "system"
    latency_ms = 10
    reliability_score = 1.0
    parameters = {"message": "str"}

    async def execute(self, params: dict, context: dict) -> ToolResult:
        # Receive incoming parameter securely
        if isinstance(params, str):
            msg = params
        else:
            msg = params.get("message", "")
            if not msg and params:
                # If the dict is full but the key is not 'message', take the first one
                msg = str(list(params.values())[0])

        msg = msg.strip()
        if not msg:
            return ToolResult(success=False, verified=False, error="Fail", message="Couldn't find anything to say.")

        return ToolResult(
            success=True,
            verified=True,
            message="Reply to user.",
            speak=msg,  # HERE IS THE MAGIC: IOBridge reads/speaks it automatically!
            data={"reply": msg}
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RememberTool [V9.6] Saving Permanent Information to Memory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RememberTool(BaseTool):
    """[V9.6] Saves permanent information to memory."""
    name = "remember_info"
    description = "It saves important personal or permanent information about the user in memory."
    protocol_tag = "REMEMBER"
    domain = "system"
    parameters = {"information": "str"}
    latency_ms = 500
    reliability_score = 0.95

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            info = params
        else:
            info = params.get("information", "")
            if not info and params:
                info = str(list(params.values())[0])

        info = info.strip()
        if not info:
            return ToolResult(
                success=False,
                message="No information to save was found.",
                speak="Sir, I couldn't understand what you wanted me to record."
            )

        ctx = engine_context or {}
        memory = ctx.get("memory")
        if not memory:
            return ToolResult(success=False, message="Memory object not found.", speak="My memory module is currently disabled.")

        try:
            await memory.save_memory_async(info, "episodic", {"importance": 0.8, "source": "user_command"})
            return ToolResult(
                success=True,
                verified=True,
                message="The information was recorded in memory.",
                speak="I have recorded this information in my memory, Sir."
            )
        except Exception as e:
            logger.error(f"RememberTool error: {e}")
            return ToolResult(success=False, message=str(e), speak="An error occurred while saving information.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ScheduleTool  [V9.2] Dinamik Zamanlama
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ScheduleTool(BaseTool):
    """[V9.2] Dynamic scheduling tool.
    It saves commands such as "Remind me in 5 minutes" to the scheduler.
    
    Usage: [PROTOCOL: SCHEDULE] minute|message
    Example: [PROTOCOL: SCHEDULE] 5|take a break"""
    name              = "schedule_reminder"
    description       = "Sets a reminder after the specified minute. Format: minute|message"
    protocol_tag      = "SCHEDULE"
    domain            = "system"
    latency_ms        = 50
    reliability_score = 0.95
    parameters        = {"reminder": "str"}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        from datetime import datetime, timedelta

        # Parameter parsing
        if isinstance(params, str):
            raw = params
        else:
            raw = params.get("reminder", "")
            if not raw and params:
                raw = str(list(params.values())[0])

        raw = raw.strip()
        if not raw or "|" not in raw:
            return ToolResult(
                success=False,
                message="Invalid schedule format. Expected: minute|message",
                speak="Sir, I couldn't understand the timing format. Example: Take a break after 5 minutes.",
            )

        parts = raw.split("|", 1)
        minutes_str = parts[0].strip()
        message = parts[1].strip() if len(parts) > 1 else ""

        # Minute verification
        try:
            minutes = int(minutes_str)
            if minutes <= 0:
                raise ValueError("Minutes must be positive")
        except ValueError:
            return ToolResult(
                success=False,
                message=f"Invalid minute value: '{minutes_str}'",
                speak="Sir, you must specify a valid minute value.",
            )

        if not message:
            return ToolResult(
                success=False,
                message="The reminder message is empty.",
                speak="Sir, you didn't say what you wanted me to remind you of.",
            )

        # Get scheduler from context
        ctx = engine_context or {}
        scheduler = ctx.get("scheduler")

        if scheduler is None:
            logger.error("[ScheduleTool] 'scheduler' not found in engine_context.")
            return ToolResult(
                success=False,
                message="Scheduler not found — engine_context is missing.",
                speak="Sir, I can't access the timer module.",
            )

        # Calculate target time
        target = datetime.now() + timedelta(minutes=minutes)
        scheduler.add_daily(
            target.hour, target.minute,
            f"[PROTOCOL: SPEAK] {message}"
        )

        logger.info(
            f"[ScheduleTool] Reminder set: {minutes} min later"
            f"({target.strftime('%H:%M')}) → {message[:50]}"
        )

        return ToolResult(
            success=True,
            message=f"Reminder set: {minutes} minutes later ({target.strftime('%H:%M')})",
            speak=f"I will remind you in {minutes} minutes, Sir.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NextStartupReminderTool [V9.6] Remind me on next startup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class NextStartupReminderTool(BaseTool):
    """[V9.6] Allows Jarvis to be displayed to the user the next time the computer/program is started. 
    He records what he has to say."""
    name              = "next_startup_reminder"
    description       = "It saves the message to be reminded when the next program is opened."
    protocol_tag      = "STARTUP_REMINDER"
    domain            = "system"
    latency_ms        = 50
    reliability_score = 0.95
    parameters        = {"message": "str"}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        import os, json

        if isinstance(params, str):
            message = params
        else:
            message = params.get("message", "")
            if not message and params:
                message = str(list(params.values())[0])

        message = message.strip()
        if not message:
            return ToolResult(
                success=False,
                message="The reminder message is empty.",
                speak="Sir, you didn't say what you wanted me to remind you of."
            )

        filepath = os.path.join(os.getcwd(), "startup_reminders.json")
        reminders = []

        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        reminders = data
            except Exception:
                pass

        reminders.append(message)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(reminders, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Failed to save start reminder: {e}")
            return ToolResult(
                success=False,
                message=str(e),
                speak="Sir, there was an error saving the reminder."
            )

        return ToolResult(
            success=True,
            verified=True,
            message="The start reminder has been saved.",
            speak="Understood Sir, I will remind you of this at my next opening."
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SteamLaunchTool [V9.3] Gaming Support
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SteamLaunchTool(BaseTool):
    """[V9.3] Tool to launch games via Steam."""
    name = "steam_launch"
    description = "Launches a specific game via Steam."
    protocol_tag = "STEAM_LAUNCH"
    domain = "desktop"
    parameters = {"game": "str"}
    latency_ms = 2000
    reliability_score = 0.90

    STEAM_GAMES = {
        "cs2": "730", "cs go": "730",
        "dota": "570", "dota 2": "570",
        "pubg": "578080",
        "gta5": "271590", "gta v": "271590",
        "minecraft": "minecraft",
        "roblox": "roblox",
        "rocket league": "252950",
        "rl": "252950",
    }

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            game = params
        else:
            game = params.get("game", "")
            if not game and params:
                game = str(list(params.values())[0])
        
        argument = game.strip()
        game = game.strip().lower()
        if not game:
            return ToolResult(success=False, verified=False, error="Fail", message="Game name not specified.", speak="Which game would you like me to open, Sir?")

        app_id = self.STEAM_GAMES.get(game, game)
        
        import os
        import webbrowser
        import asyncio
        
        loop = asyncio.get_running_loop()
        
        def _launch_steam():
            try:
                os.startfile(f"steam://rungameid/{app_id}")
            except AttributeError:
                webbrowser.open(f"steam://rungameid/{app_id}")
                
        try:
            await loop.run_in_executor(None, _launch_steam)
            return ToolResult(
                success=True,
                verified=True,
                message=f"Steam launch command sent (URI): {app_id}",
                speak=f"{argument} Launching via Steam Sir."
            )
        except Exception as e:
            logger.error(f"Steam startup error: {e}")
            return ToolResult(success=False, verified=False, error="Fail", message=str(e), speak="Sir, the Steam command failed to run.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EpicLaunchTool [V9.4] Epic Games Support
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EpicLaunchTool(BaseTool):
    """[V9.4] Game launcher from Epic Games."""
    name = "epic_launch"
    description = "Launches a specific game via Epic Games."
    protocol_tag = "EPIC_LAUNCH"
    domain = "desktop"
    parameters = {"game": "str"}
    latency_ms = 2000
    reliability_score = 0.90

    EPIC_GAMES = {
        "rocket league": "rocketleague",
        "rl": "rocketleague",
        "fortnite": "Fortnite",
        "fall guys": "FallGuys",
        "fallguys": "FallGuys",
    }

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            game = params
        else:
            game = params.get("game", "")
            if not game and params:
                game = str(list(params.values())[0])
        
        argument = game.strip()
        game = game.strip().lower()
        if not game:
            return ToolResult(success=False, verified=False, error="Fail", message="Game name not specified.", speak="Which Epic game would you like me to open, Sir?")

        slug = self.EPIC_GAMES.get(game, game)
        
        import webbrowser
        import asyncio
        
        loop = asyncio.get_running_loop()
        
        def _launch_epic():
            webbrowser.open(f"com.epicgames.launcher://apps/{slug}?action=launch&silent=true")
            
        try:
            await loop.run_in_executor(None, _launch_epic)
            return ToolResult(
                success=True,
                verified=True,
                message=f"Epic launch command sent (URI): {slug}",
                speak=f"{argument} It is being launched via Epic Games, Sir."
            )
        except Exception as e:
            logger.error(f"Epic Games initialization error: {e}")
            return ToolResult(success=False, verified=False, error="Fail", message=str(e), speak="Sir, the Epic Games command could not be executed.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SystemPowerTool [V9.3] Power Management
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SystemPowerTool(BaseTool):
    """[V9.3] Shutting down, restarting, or putting the computer to sleep.
    It includes an approval mechanism."""
    name = "system_power"
    description = "Shuts down, restarts, or puts the computer to sleep."
    protocol_tag = "SYSTEM_POWER"
    domain = "system"
    parameters = {"action": "str"}
    latency_ms = 100
    reliability_score = 1.0

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            raw_action = params
        else:
            raw_action = params.get("action", "")
            if not raw_action and params:
                raw_action = str(list(params.values())[0])
        
        raw_action = raw_action.strip().lower()
        needs_confirm = "approved" not in raw_action
        action = raw_action.replace("approved", "").strip()

        if action not in ["kapat", "restart_restart", "uyku"]:
            return ToolResult(success=False, verified=False, error="Fail", message=f"Invalid action: {action}", speak="Sir I can only execute shutdown, reboot or sleep commands.")

        if needs_confirm:
            return ToolResult(
                success=False,
                message=f"Pending confirmation for power operation: {action}",
                speak=f"Your approval is required for computer {action} operation, Sir. You can confirm by saying 'Yes' or 'No'.",
                next_action="CONFIRM_POWER",
                data={"pending_action": action}
            )

        # If approved, perform the action
        try:
            if action == "kapat":
                os.system("shutdown /s /t 5")
            elif action == "restart_restart":
                os.system("shutdown /r /t 5")
            elif action == "uyku":
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            
            return ToolResult(
                success=True,
                message=f"System {action} command implemented.",
                speak=f"System {action} process started Sir. Goodbye."
            )
        except Exception as e:
            logger.error(f"Power operation error: {e}")
            return ToolResult(success=False, verified=False, error="Fail", message=str(e), speak="Sir, the system command could not be executed.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ShutdownTool [V9.5] — J.A.R.V.I.S. Graceful Self-Shutdown
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ShutdownTool(BaseTool):
    """[V9.5] J.A.R.V.I.S.'s own asyncio loop and GUI
    ensures safe termination.

    Trigger: [PROTOCOL: SYSTEM_SHUTDOWN]

    Stream:
        1. LLM detects "shut down system" intent and
           Produces [PROTOCOL: SYSTEM_SHUTDOWN] output.
        2. PlanExecutor calls this tool with engine_context.
        3. Sends execute() → io_bridge.request_shutdown() signal.
        4. Engine's start() loop sees the flag and breaks.
        5. engine.shutdown() → scheduler, executor are cleared.
        6. GUI callback receives "CLOSING" signal → root.quit().
        7. The Python process exits cleanly.

    Constraint: sys.exit() CANNOT be used.
        sys.exit() leaves asyncio tasks and Tkinter dirty.
        Instead, the IOBridge signal + engine shutdown cycle is used."""

    name              = "jarvis_shutdown"
    description       = (
        "J.A.R.V.I.S. completely shuts down the system."
        "The asyncio loop, GUI and all subsystems are terminated safely."
    )
    protocol_tag      = "SYSTEM_SHUTDOWN"
    domain            = "system"
    latency_ms        = 50
    reliability_score = 1.0
    parameters        = {}

    # To the system prompt: This tool ONLY supports user J.A.R.V.I.S.
    # is used when you explicitly want to shut down.
    # Example triggers: "shut down system", "shut down self",
    # "close jarvis", "log out", "close to see you"

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        """Sends shutdown signal via IOBridge.

        It is mandatory to have the "io_bridge" key in engine_context.
        PlanExecutor adds this automatically (executor._build_context)."""
        ctx = engine_context or {}
        io_bridge = ctx.get("io_bridge")

        if io_bridge is None:
            # Fallback: If engine_context is missing, log and mark it anyway
            logger.error(
                "[ShutdownTool] 'io_bridge' not found in engine_context!"
                "Check the PlanExecutor context mapping."
            )
            # Last resort: exit with sys.exit (only if there is no io_bridge)
            import sys
            import asyncio
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(loop.stop)
            return ToolResult(
                success=True,
                message="io_bridge not found — event loop stopped.",
                speak="Systems are being shut down, Sir. Have a nice day.",
            )

        # Normal yol: IOBridge sinyali
        io_bridge.request_shutdown()

        logger.info("[ShutdownTool] ✅ Kapatma sinyali IOBridge'e iletildi.")

        return ToolResult(
            success=True,
            message="System shutdown protocol initiated.",
            speak="Systems are shutting down. Have a nice day Sir.",
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLMEvalTool [V15.3] — Cognitive Assessment and Computation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LLMEvalTool(BaseTool):
    name = "llm_eval"
    description = "Reasons, performs calculations, or answers questions based on collected data."
    protocol_tag = "LLM_EVAL"
    domain = "system"
    latency_ms = 2000
    reliability_score = 1.0
    parameters = {"question": {"type": "string", "description": "Question to be answered or calculation to be made"}}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        question = params.get("question", "") or params.get("query", "")
        if isinstance(params, str): question = params
        
        ctx = engine_context or {}
        brain = ctx.get("brain")
        step_data = ctx.get("step_results", {})
        
        if not brain:
            return ToolResult(success=False, verified=False, error="NoBrain", message="There is no brain module.")
            
        prompt = (
            "You are an analytical engine. Read the 'Data Collected' below carefully."
            "Answer/calculate the user's question EXACTLY and CLEARLY based on this data."
            "ATTENTION: If the question contains more than one piece of data (e.g. If any data is missing, don't guess, just say 'Data is missing'.\n\n"
            f"Toplanan Veriler:\n{step_data}\n\n"
            f"Soru: {question}"
        )
        
        print(f"\n[BRAIN LOG] Data to LLM_EVAL:\n{step_data}\n")
        
        try:
            response = await brain.client.chat.completions.create(
                model=brain.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=256
            )
            answer = response.choices[0].message.content.strip()
            import re
            answer = re.sub(r'\[PROTOCOL:.*?\]', '', answer).strip()
            
            return ToolResult(
                success=True, 
                verified=True, 
                message=f"Evaluation result: {answer}", 
                speak=f"Sir, I analyzed the data. Result: {answer}"
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message="Evaluation failed.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# YouTubeStrategyTool [V15.1] — Autonomous Content Factory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class YouTubeStrategyTool(BaseTool):
    """Generates autonomous video idea, title and thumbnail prompt for BabaClutch channel."""
    name              = "youtube_strategy"
    description       = "Generates strategy, title and thumbnail prompt for YouTube channel."
    protocol_tag      = "YOUTUBE_STRATEGY"
    domain            = "web"
    latency_ms        = 4000
    reliability_score = 1.0
    parameters        = {"request": {"type": "string", "description": "Desired strategy (ex: give 3 ideas for Rocket League)"}}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        request = params.get("request", "") or params.get("query", "")
        if isinstance(params, str):
            request = params
            
        request = request.strip()
        if not request:
            return ToolResult(success=False, verified=False, error="Fail", message="The request is empty.", speak="Sir, what do you want me to plan for YouTube?")

        ctx = engine_context or {}
        brain = ctx.get("brain")
        if not brain:
            return ToolResult(success=False, verified=False, error="Fail", message="Brain module not found.")

        #1 Channel DNA and Ruthless Strategist Prompt
        system_prompt = (
            "You are a relentless, data-driven and elite YouTube Content Strategist and Thumbnail Prompt Engineer."
            "Channel Name: BabaClutch (Oğuz and Eymen). Concept: Chaos, rage, friend fight, games with penalties."
            "Games: Rocket League, Minecraft Bedwars, Left 4 Dead 2 and any game the user specified."
            "Strategy Rules: Don't be generic. Focus on CTR and AVD. Write short headlines that spark curiosity."
            "Criticize ideas mercilessly. Let every idea be original and specific to the channel.\n\n"
            "=== THUMBNAIL PROMPT RULES (VERY CRITICAL) ===\n"
            "If you are prompted for a thumbnail prompt, STRICTLY follow these rules:\n"
            "1. Prompt will be in ENGLISH (for visual generator)\n"
            "2. ALL ARTICLES in the Thumbnail will be in TURKISH — English text is PROHIBITED\n"
            "3. Write in ultra-detail: scene atmosphere, lighting, effects, camera angle, color palette, text style, location\n"
            "4. Use game-specific visual elements (characters, arenas, weapons, etc.)\n"
            "5. MUST close the format like this: [PROMPT]...[/PROMPT]\n\n"
            "Sample quality standard (for Rocket League):\n"
            "[PROMPT]Hyper-realistic 3D Rocket League thumbnail art, dark dramatic arena background with deep red and "
            "orange glowing light, two rocket-powered cars on the field, one car exploding mid-air with massive fire "
            "burst and shockwave debris flying outward, the other car boosting aggressively with blue-orange boost "
            "flames trailing behind, large glowing red countdown timer showing '0:30' in the upper right area like "
            "an in-game UI element, sparks and particles filling the air, cinematic dramatic lighting casting harsh "
            "shadows, high contrast vivid colors, ultra-detailed car reflections, same dark moody style as Rocket "
            "League YouTube thumbnails, bold Turkish text 'EVERY 30 SECONDS' in white with thick black outline at"
            "the top left area, even larger bold text 'PATLATMAK ZORUNDAYIZ!' in bright yellow-orange with thick "
            "black outline and slight glow effect in the bottom left area, professional YouTube thumbnail typography "
            "style, impactful and high contrast text, 16:9 format, epic action composition[/PROMPT]\n\n"
            "Like in this example: fully describe the scene, lighting, characters, effects and TURKISH text."
            "Write the Turkish text content in harmony with the challenge/video title, eye-catching and short."
        )

        try:
            #2. J.A.R.V.I.S. Direct API call to bypass restrictions
            response = await brain.client.chat.completions.create(
                model=brain.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request}
                ],
                temperature=0.7,
                max_tokens=1024
            )
            result_text = response.choices[0].message.content.strip()

            # Write to the log for a clear view by hiding the [PROMPT] tag
            import re as _re
            display_text = _re.sub(r'\[/?PROMPT\]', '', result_text).strip()
            logger.info(f"\n{'─'*60}\n[BabaClutch Strateji Raporu]\n{display_text}\n{'─'*60}")

            speak_msg = f"A strategy report has been prepared, Sir:\n\n{display_text}"

            #3. Hacker Touch: Copy to clipboard and open browser if prompted
            if "thumbnail" in request.lower() or "prompt" in request.lower() or "visual" in request.lower():
                try:
                    import pyperclip
                    import webbrowser
                    import asyncio
                    import re

                    extracted_prompt = None

                    # Strategy 1: Closed tag [PROMPT]...[/PROMPT]
                    m = re.search(r'\[PROMPT\](.*?)\[/PROMPT\]', result_text, re.DOTALL | re.IGNORECASE)
                    if m:
                        candidate = m.group(1).strip()
                        if candidate and candidate != "...":
                            extracted_prompt = candidate

                    # Strategy 2: Open tag [PROMPT]... (not closed)
                    if not extracted_prompt:
                        m = re.search(r'\[PROMPT\](.+?)$', result_text, re.DOTALL | re.IGNORECASE)
                        if m:
                            candidate = m.group(1).strip().strip('"').strip()
                            if candidate and candidate != "...":
                                extracted_prompt = candidate

                    # Strategy 3: Get the last line (if the model wrote without tags)
                    if not extracted_prompt:
                        lines = [l.strip() for l in result_text.splitlines() if l.strip()]
                        if lines:
                            last = lines[-1].strip('"').strip()
                            if re.search(r'[a-zA-Z]{5,}', last):
                                extracted_prompt = last

                    final_clipboard = extracted_prompt or result_text
                    pyperclip.copy(final_clipboard)
                    logger.info(f"[YouTubeStrategy] ✅ Panoya kopyalanan thumbnail prompt:\n  {final_clipboard[:120]}")

                    speak_msg += "\n\n📋 Thumbnail prompt copied to clipboard. The visual generator opens..."

                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, webbrowser.open, "https://chatgpt.com/")
                except ImportError:
                    logger.warning("pyperclip is not installed. Clipboard copy skipped.")

            return ToolResult(
                success=True,
                verified=True,
                message=speak_msg,
                speak=speak_msg,
                data={"strategy": result_text}
            )

        except Exception as e:
            logger.error(f"[YouTubeStrategy] Error: {e}", exc_info=True)
            return ToolResult(success=False, verified=False, error="Fail", message=str(e), speak="Sir, there was an error connecting to the strategy module.")