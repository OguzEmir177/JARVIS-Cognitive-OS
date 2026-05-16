"""
[V10.5] J.A.R.V.I.S. Desktop Tools
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Evrensel uygulama açma/kapatma araçları.

[V10.5] AppOpenTool güncellendi:
    - UniversalAppIndex (fuzzy matching) tabanlı arama
    - Türkçe karakter toleransı ("whatsap" → WhatsApp)
    - Yazım hatası toleransı ("github" → GitHub Desktop)
    - Start Menu, Desktop, Registry, Steam, Epic, UWP kapsamı
"""

import asyncio
import logging
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.DesktopTools")


class AppOpenTool(BaseTool):
    """Bilgisayardaki herhangi bir uygulamayı fuzzy matching ile açar."""
    name             = "app_open"
    description      = (
        "Bilgisayardaki herhangi bir uygulamayı açar. "
        "Yazım hatalarını ve büyük/küçük harf farklarını tolere eder. "
        "Örn: 'github', 'whatsap', 'steam', 'discord' veya herhangi bir proje kısayolu."
    )
    protocol_tag     = "APP_OPEN"
    parameters       = {"app_name": {"type": "string", "description": "Açılacak uygulama adı"}}
    domain           = "desktop"
    latency_ms       = 3000
    reliability_score = 0.92

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        # Parametre çözümleme
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
                error="Uygulama adı boş.",
                message="Uygulama adı boş.",
                speak="Efendim, hangi uygulamayı açmamı istediğinizi anlayamadım."
            )

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, self._launch, app_name)

        if "BAŞARILI" in result:
            # Açılan uygulamanın adını çıkar
            display = app_name
            if ":" in result:
                try:
                    display = result.split(":", 1)[1].split("açıldı")[0].strip()
                except Exception:
                    display = app_name
            return ToolResult(
                success=True,
                verified=True,
                message=result,
                speak=f"{display} açılıyor Efendim."
            )

        return ToolResult(
            success=False,
            verified=False,
            error=result,
            message=result,
            speak=f"Efendim, {app_name} uygulaması bulunamadı ya da başlatılamadı."
        )

    @staticmethod
    def _launch(app_name: str) -> str:
        """Bloklamalı çağrı — executor'da çalışır."""
        from tools.utils.native_ops import NativeOps
        return NativeOps.open_app(app_name)


class AppKillTool(BaseTool):
    """Masaüstü uygulamasını kapatır."""
    name             = "app_kill"
    description      = "Masaüstü uygulamasını kapatır"
    protocol_tag     = "APP_KILL"
    parameters       = {"app_name": {"type": "string", "description": "Kapatılacak uygulama"}}
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
                message="Uygulama adı boş.",
                speak="Efendim, neyi kapatacağımı anlayamadım."
            )

        app_lower = app_name.lower()
        if any(p in app_lower for p in self.PROTECTED_PROCESSES):
            return ToolResult(
                success=False,
                message="Korumalı işlem.",
                speak="Efendim, bu güvenlik sebebiyle kapatılamaz."
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
                    message=f"'{app_name}' bir web uygulaması.",
                    speak=f"{app_name} bir web uygulaması. {browser} tarayıcısını kapatmamı ister misiniz?",
                    next_action="CONFIRM_BROWSER_KILL",
                    data={"browser": browser, "app": app_name},
                )

        from tools.utils.native_ops import NativeOps
        result = await asyncio.get_running_loop().run_in_executor(
            None, NativeOps.kill_app, app_name
        )
        if "BAŞARILI" in result:
            return ToolResult(success=True, verified=True, message=result, speak=f"{app_name} kapatıldı Efendim.")
        return ToolResult(success=False, verified=False, error="BAŞARISIZ", message="BAŞARISIZ", speak=f"Efendim, {app_name} bulunamadı.")
