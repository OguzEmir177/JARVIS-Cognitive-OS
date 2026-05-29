"""[V10.5] J.A.R.V.I.S. Desktop Tools
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Universal app toggle tools.

[V10.5] AppOpenTool updated:
    - Search based on UniversalAppIndex (fuzzy matching)
    - Turkish character tolerance ("whatsap" → WhatsApp)
    - Typos tolerance ("github" → GitHub Desktop)
    - Start Menu, Desktop, Registry, Steam, Epic, UWP coverage"""

import asyncio
import logging
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.DesktopTools")


class AppOpenTool(BaseTool):
    """It opens any application on the computer with fuzzy matching."""
    name             = "app_open"
    description      = (
        "Opens any application on the computer."
        "Tolerates typos and case differences."
        "For example: 'github', 'whatsap', 'steam', 'discord' or any project shortcut."
    )
    protocol_tag     = "APP_OPEN"
    parameters       = {"app_name": {"type": "string", "description": "Application name to open"}}
    domain           = "desktop"
    latency_ms       = 3000
    reliability_score = 0.92

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        # Parameter parsing
        if isinstance(params, str):
            app_name = params
        else:
            app_name = params.get("app_name", "")
            if not app_name and params:
                app_name = str(list(params.values())[0])

        app_name = app_name.strip()
        if not app_name:
            return ToolResult(
                success=False,
                verified=False,
                error="Application name is empty.",
                message="Application name is empty.",
                speak="Sir, I couldn't understand which application you want me to open."
            )

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._launch, app_name)

        if "SUCCESSFUL" in result:
            # Get the name of the opened application
            display = app_name
            if ":" in result:
                try:
                    display = result.split(":", 1)[1].split("opened")[0].strip()
                except Exception:
                    display = app_name
            return ToolResult(
                success=True,
                verified=True,
                message=result,
                speak=f"{display} is opening, Sir."
            )

        return ToolResult(
            success=False,
            verified=False,
            error=result,
            message=result,
            speak=f"Sir, application {app_name} could not be found or started."
        )

    @staticmethod
    def _launch(app_name: str) -> str:
        """Blocked call — runs on executor."""
        from tools.utils.native_ops import NativeOps
        return NativeOps.open_app(app_name)


class AppKillTool(BaseTool):
    """Closes the desktop application."""
    name             = "app_kill"
    description      = "Closes the desktop application"
    protocol_tag     = "APP_KILL"
    parameters       = {"app_name": {"type": "string", "description": "Application to close"}}
    domain           = "desktop"
    latency_ms       = 2000
    reliability_score = 0.75

    PROTECTED_PROCESSES = ["python", "jarvis", "cmd", "powershell", "code"]
    WEB_APPS = {
        "youtube": "Chrome", "spotify": "Chrome", "netflix": "Chrome",
        "whatsapp": "Chrome", "twitter": "Chrome", "instagram": "Chrome",
        "google": "Chrome", "gmail": "Chrome",
    }

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            app_name = params
        else:
            app_name = params.get("app_name", "").strip()

        if not app_name:
            return ToolResult(
                success=False,
                message="Application name is empty.",
                speak="Sir, I couldn't figure out what to turn off."
            )

        app_lower = app_name.lower()
        if any(p in app_lower for p in self.PROTECTED_PROCESSES):
            return ToolResult(
                success=False,
                message="Protected transaction.",
                speak="Sir, this cannot be closed for security reasons."
            )

        NATIVE_APPS = {
            "whatsapp", "discord", "telegram",
            "spotify", "steam", "epic", "epic games",
        }

        if app_lower not in NATIVE_APPS:
            browser = self.WEB_APPS.get(app_lower)
            if browser:
                return ToolResult(
                    success=False,
                    message=f"'{app_name}' is a web application.",
                    speak=f"{app_name} is a web application. Do you want me to close browser {browser}?",
                    next_action="CONFIRM_BROWSER_KILL",
                    data={"browser": browser, "app": app_name},
                )

        from tools.utils.native_ops import NativeOps
        result = await asyncio.get_running_loop().run_in_executor(
            None, NativeOps.kill_app, app_name
        )
        if "SUCCESSFUL" in result:
            return ToolResult(success=True, verified=True, message=result, speak=f"{app_name} is closed Sir.")
        return ToolResult(success=False, verified=False, error="UNSUCCESSFUL", message="UNSUCCESSFUL", speak=f"Sir, {app_name} was not found.")
