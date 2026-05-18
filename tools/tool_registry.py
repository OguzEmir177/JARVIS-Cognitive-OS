"""
[V8.0] J.A.R.V.I.S. Tool Registry
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Araç kayıt, keşif ve seçim sistemi.

Yenilikler (core/tools.py'deki ToolRegistry'den farklar):
    - get_best_tool(domain, context) — metadata-tabanlı optimal seçim
    - get_fallback_chain(protocol_tag) — alternatif tool zinciri
    - Mevcut smart alias mantığı korunuyor

Tasarım Kararı:
    Neden centralized registry?
    → Executor sadece tag → tool eşleştirmesi bilir.
    → Hangi tool'un daha güvenilir, hızlı, uygun olduğu
      registry metadata'sına bakılarak karar verilir.
    → Yeni tool eklemek: class yaz + register et. Başka bir yere dokunma.
"""

import logging
from typing import Dict, List, Optional

from tools.base_tool import BaseTool

logger = logging.getLogger("JARVIS.ToolRegistry")


# ── Fallback Zinciri: tool başarısız → hangi alternatif? ──
FALLBACK_CHAINS: Dict[str, List[str]] = {
    "YT_PLAY": ["YT_SEARCH"],
    "APP_KILL": ["TAB_KILL"],
    "WEB_OPEN": ["GOOGLE_SEARCH"],
}

# ── Smart Aliases: LLM'in uydurduğu tag'ler → doğru tag ──
SMART_ALIASES: Dict[str, str] = {
    "GOOGLE": "GOOGLE_SEARCH",
    "SEARCH": "GOOGLE_SEARCH",
    "YOUTUBE_SEARCH": "YT_SEARCH",
    "YOUTUBE_PLAY": "YT_PLAY",
    "YOUTUBE": "YT_SEARCH",
    "BROWSER_OPEN": "WEB_OPEN",
    "OPEN_WEB": "WEB_OPEN",
    "URL_OPEN": "WEB_OPEN",
    "OPEN_APP": "APP_OPEN",
    "LAUNCH_APP": "APP_OPEN",
    "APPLICATION_OPEN": "APP_OPEN",
    "CLOSE_APP": "APP_KILL",
    "KILL_APP": "APP_KILL",
    "KILL_PROCESS": "APP_KILL",
    "KILL": "APP_KILL",
    "EPIC_KILL": "APP_KILL",
    "STEAM_KILL": "APP_KILL",
    "CLOSE_TAB": "TAB_KILL",
    "SEND_WHATSAPP": "WHATSAPP_MESSAGE",
    "WHATSAPP_SEND": "WHATSAPP_MESSAGE",
    "WHATSAPP": "WHATSAPP_MESSAGE",
    "SEE_SCREEN": "VISION",
    "LOOK_SCREEN": "VISION",
    "SCREENSHOT": "VISION",
    "SCREEN_ANALYZE": "VISION",
    "DELETE_WHATSAPP": "WHATSAPP_DELETE",
    "STRESS": "STRESS_TEST",
    "REMINDER": "SCHEDULE",
    "SET_REMINDER": "SCHEDULE",
    "SET_TIMER": "SCHEDULE",
    "TIMER": "SCHEDULE",
    "HATIRLATMA": "SCHEDULE",
    "ALARM": "SCHEDULE",
    "HATIRLATICI": "SCHEDULE",
    "REMIND": "SCHEDULE",
    "FILE_LIST": "FILE_READ",
    "FILE_OPEN": "FILE_OPEN",
    "OPEN_FILE": "FILE_OPEN",
    "FILE_CREATE": "FILE_CREATE",
    "CREATE_FILE": "FILE_CREATE",
    "FILE_APPEND": "FILE_WRITE",
    "GOOGLE_TRENDS": "GOOGLE_TRENDS",
    "TRENDS": "GOOGLE_TRENDS",
    "SON_INDIRILEN": "FILE_LATEST",
    "EN_SON_DOSYA": "FILE_LATEST",
    "LATEST_FILE": "FILE_LATEST",
    "FOLDER_OPEN": "FOLDER_OPEN",
    "FILE_DELETE": "FILE_DELETE",
    "LIST_FILES": "FILE_READ",
    "DIR": "FILE_READ",
    "LS": "FILE_READ",
    "GOOGLE_SUMMARY": "WEB_SEARCH",
    "WEB_SUMMARY": "WEB_SEARCH",
    "SEARCH_AND_SUMMARIZE": "WEB_SEARCH",
    "WEB_SUMMARIZE": "WEB_SEARCH",
    "SUMMARIZE": "WEB_SEARCH",
    "STEAM": "STEAM_LAUNCH",
    "STEAM_OPEN": "STEAM_LAUNCH",
    "OYUN_AC": "STEAM_LAUNCH",
    "SHUTDOWN": "SYSTEM_POWER",
    "KAPAT": "SYSTEM_POWER",
    "RESTART": "SYSTEM_POWER",
    "YENIDEN_BASLAT": "SYSTEM_POWER",
    "WEB_CLOSE": "TAB_KILL",
    "SEKMEYI_KAPAT": "TAB_KILL",
    "SAYFAYI_KAPAT": "TAB_KILL",
    "EPIC_LAUNCH": "EPIC_LAUNCH",
    "EPIC": "EPIC_LAUNCH",
    "EPIC_OPEN": "EPIC_LAUNCH",
    "CLOSE_LAST_TAB": "CLOSE_LAST_TAB",
    "AZ_ONCE_ACTIGI_SEKME": "CLOSE_LAST_TAB",
    "ACTIGI_SEKMEYI_KAPAT": "CLOSE_LAST_TAB",
    "YOUTUBE_PLANLA": "YOUTUBE_STRATEGY",
    "VIDEO_FIKRI": "YOUTUBE_STRATEGY",
    "THUMBNAIL_YAP": "YOUTUBE_STRATEGY",
    "KANAL_STRATEJISI": "YOUTUBE_STRATEGY",
}


class ToolRegistry:
    """
    Merkezi araç kayıt ve keşif sistemi.

    Kullanım:
        registry = ToolRegistry()
        registry.register(GoogleSearchTool())

        tool = registry.get_by_protocol("GOOGLE_SEARCH")
        chain = registry.get_fallback_chain("YT_PLAY")
        best = registry.get_best_tool("web")

    Thread Safety:
        Tek asyncio loop'ta çalışır. Registration sadece startup'ta olur.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Tool'u registry'ye kaydeder.

        Edge Case:
            - Aynı protocol_tag tekrar kaydedilirse → üzerine yaz + uyarı
            - protocol_tag boşsa → ValueError
        """
        if not tool.protocol_tag:
            raise ValueError(
                f"Tool '{tool.name}' protocol_tag tanımsız."
            )

        if tool.protocol_tag in self._tools:
            logger.warning(
                f"Tool override: '{tool.protocol_tag}' "
                f"({self._tools[tool.protocol_tag].name} → {tool.name})"
            )

        self._tools[tool.protocol_tag] = tool
        logger.debug(
            f"Tool registered: {tool.protocol_tag} → {tool.name} "
            f"(domain={tool.domain}, reliability={tool.reliability_score})"
        )

    def get_by_protocol(self, protocol_tag: str) -> Optional[BaseTool]:
        """
        Protocol tag ile tool'u bul.
        Smart alias varsa çözümle.

        Args:
            protocol_tag: Tool'un protokol etiketi

        Returns:
            BaseTool instance veya None

        Edge Case:
            Bilinmeyen tag → alias check → hala yoksa None
        """
        # Direkt eşleşme
        tool = self._tools.get(protocol_tag)
        if tool:
            return tool

        # Smart alias çözümleme
        resolved = SMART_ALIASES.get(protocol_tag.upper())
        if resolved:
            logger.info(f"Alias resolved: {protocol_tag} → {resolved}")
            return self._tools.get(resolved)

        logger.warning(f"Bilinmeyen protocol_tag: '{protocol_tag}'")
        return None

    def get_best_tool(
        self,
        domain: str,
        context: Optional[dict] = None,
    ) -> Optional[BaseTool]:
        """
        Belirtilen domain'de en yüksek reliability_score'a sahip tool'u döndürür.

        Args:
            domain:  "web", "desktop", veya "system"
            context: Opsiyonel bağlamsal veri (ileride kullanılabilir)

        Returns:
            BaseTool veya None (domain'de tool yoksa)

        Edge Case:
            Aynı reliability'de 2 tool → düşük latency tercih edilir
        """
        candidates = [
            t for t in self._tools.values()
            if t.domain == domain
        ]

        if not candidates:
            return None

        # Sıralama: reliability desc, latency asc
        candidates.sort(
            key=lambda t: (-t.reliability_score, t.latency_ms)
        )

        return candidates[0]

    def get_fallback_chain(self, protocol_tag: str) -> List[BaseTool]:
        """
        Başarısız tool için sıralı alternatif tool listesi.

        Args:
            protocol_tag: Başarısız olan tool'un tag'i

        Returns:
            BaseTool listesi (sıralı, boş olabilir)
        """
        chain_tags = FALLBACK_CHAINS.get(protocol_tag, [])
        chain = []

        for tag in chain_tags:
            tool = self.get_by_protocol(tag)
            if tool:
                chain.append(tool)

        return chain

    def get_tools_by_domain(self, domain: str) -> List[BaseTool]:
        """Domain'e göre tool listesi (reliability azalan)."""
        tools = [
            t for t in self._tools.values()
            if t.domain == domain
        ]
        tools.sort(key=lambda t: -t.reliability_score)
        return tools

    def get_tools_prompt(self) -> str:
        """[V9.0] export_schemas() alias — brain.py uyumluluğu için."""
        return self.export_schemas()

    def export_schemas(self) -> str:
        """Tüm araç tanımlarını LLM prompt'a uygun formatta dışa aktarır."""
        lines = []
        for tool in self._tools.values():
            params_str = ", ".join(
                f"{k}: {v.get('type', 'string')}"
                for k, v in tool.parameters.items()
            )
            lines.append(
                f"- {tool.protocol_tag}: {tool.description} "
                f"→ [PROTOCOL: {tool.protocol_tag}] {params_str}"
            )
        return "\n".join(lines)

    @property
    def count(self) -> int:
        """Kayıtlı araç sayısı."""
        return len(self._tools)

    @property
    def all_tags(self) -> List[str]:
        """Kayıtlı tüm protocol tag'leri."""
        return list(self._tools.keys())

    def __repr__(self) -> str:
        return f"ToolRegistry(count={self.count}, tags={self.all_tags})"


    @property
    def smart_aliases(self) -> Dict[str, str]:
        return SMART_ALIASES

    def is_registered(self, tag: str) -> bool:
        """[V9.1] Dinamik allowlist — alias'ı çözümle, sonra kontrol et."""
        resolved = self.smart_aliases.get(tag.upper(), tag.upper())
        return resolved in self.all_tags


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FACTORY — Default Registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def create_default_registry() -> ToolRegistry:
    """
    Tüm v9.0 tool'larını kaydeden factory.

    Import sırası önemli — circular import'ları önler:
        browser_tool → base_tool (OK)
        desktop_tool → base_tool (OK)
        system_tool  → base_tool (OK)
    """
    registry = ToolRegistry()

    # Browser tools (Playwright async)
    try:
        from tools.browser_tool import (
            GoogleSearchTool,
            WebOpenTool,
            YouTubeSearchTool,
            YouTubePlayTool,
            CloseLastTabTool, # [V9.4] EKLENDİ
            WebSearchTool,    # [V9.6] EKLENDİ
        )
        registry.register(GoogleSearchTool())
        registry.register(WebOpenTool())
        registry.register(YouTubeSearchTool())
        registry.register(YouTubePlayTool())
        registry.register(CloseLastTabTool()) # [V9.4] EKLENDİ
        registry.register(WebSearchTool())    # [V9.6] EKLENDİ
        logger.info("Browser tools kaydedildi (Playwright)")
    except ImportError as e:
        logger.warning(f"Browser tools yüklenemedi: {e}")

    # Desktop tools (pywinauto)
    try:
        from tools.desktop_tool import (
            AppOpenTool,
            AppKillTool,
        )
        registry.register(AppOpenTool())
        registry.register(AppKillTool())
        logger.info("Desktop tools kaydedildi (pywinauto)")
    except ImportError as e:
        logger.warning(f"Desktop tools yüklenemedi: {e}")

    # System tools (wrappers)
    # System tools (wrappers)
    try:
        from tools.system_tool import (
            WhatsAppTool,
            WhatsAppDeleteTool,
            VisionTool,
            StressTestTool,
            TabKillTool,
            SpeakTool,      # [V9.1] EKLENDİ
            ScheduleTool,   # [V9.2] EKLENDİ
            SteamLaunchTool, # [V9.3] EKLENDİ
            SystemPowerTool, # [V9.3] EKLENDİ
            EpicLaunchTool,  # [V9.4] EKLENDİ
            ShutdownTool,    # [V9.5] EKLENDİ
            YouTubeStrategyTool, # [V15.1] EKLENDİ
            LLMEvalTool,     # [V15.3] EKLENDİ
        )
        registry.register(WhatsAppTool())
        registry.register(WhatsAppDeleteTool())
        registry.register(VisionTool())
        registry.register(StressTestTool())
        registry.register(TabKillTool())
        registry.register(SpeakTool())      # [V9.1] EKLENDİ
        registry.register(ScheduleTool())    # [V9.2] EKLENDİ
        registry.register(SteamLaunchTool()) # [V9.3] EKLENDİ
        registry.register(SystemPowerTool()) # [V9.3] EKLENDİ
        registry.register(EpicLaunchTool())  # [V9.4] EKLENDİ
        registry.register(ShutdownTool())    # [V9.5] EKLENDİ
        registry.register(YouTubeStrategyTool()) # [V15.1] EKLENDİ
        registry.register(LLMEvalTool())     # [V15.3] EKLENDİ
        logger.info("System tools kaydedildi")
    except ImportError as e:
        logger.warning(f"System tools yüklenemedi: {e}")

    # [V9.0] Filesystem tools — AYRI try bloğu
    try:
        from tools.file_tool import FileReadTool, FileSummarizeTool, FileWriteTool, FileLatestTool, FileCreateTool, FileDeleteTool, FolderOpenTool, FileOpenTool
        from tools.analiz_pro_tool import AnalizProTool
        from tools.python_tool import PythonExecutionTool
        registry.register(FileReadTool())
        registry.register(PythonExecutionTool())
        registry.register(AnalizProTool())
        registry.register(FileSummarizeTool())
        registry.register(FileWriteTool())
        registry.register(FileLatestTool())
        registry.register(FileCreateTool())
        registry.register(FileDeleteTool())
        registry.register(FolderOpenTool())
        registry.register(FileOpenTool())
        logger.info("Filesystem tools kaydedildi")
    except ImportError as e:
        logger.warning(f"Filesystem tools yüklenemedi: {e}")

    # Fonksiyon en son burada biter ve registry'yi geri döndürür
    logger.info(
        f"Default registry oluşturuldu: {registry.count} tool kayıtlı "
        f"→ {registry.all_tags}"
    )
    return registry