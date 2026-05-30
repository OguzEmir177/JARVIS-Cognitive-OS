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
                    logger.info(f"[YouTubeStrategy] ✅ Thumbnail prompt copied to clipboard:\n  {final_clipboard[:120]}")

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