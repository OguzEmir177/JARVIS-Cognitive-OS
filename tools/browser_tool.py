"""
[V8.0] J.A.R.V.I.S. Browser Tools (Playwright Async)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Playwright ile asenkron web otomasyonu araçları.

Araçlar:
    GoogleSearchTool  → GOOGLE_SEARCH  → Google arama
    WebOpenTool       → WEB_OPEN       → URL açma
    YouTubeSearchTool → YT_SEARCH      → YouTube arama
    YouTubePlayTool   → YT_PLAY        → YouTube video oynatma

Tasarım Kararları:
    Neden Playwright ve webbrowser değil?
    → webbrowser sadece URL açar, kontrol yok.
    → Playwright: tıklama, yazma, bekleme, ekran görüntüsü.
    → Async-native: asyncio event loop ile doğal uyum.

    Neden paylaşımlı browser instance?
    → Her tool'da ayrı browser = yüksek bellek + yavaş başlatma.
    → BrowserManager singleton browser'ı lazy-init eder.
    → Tüm tool'lar aynı browser context'i paylaşır.

Edge Cases:
    - Playwright kurulu değilse → ToolExecutionError (açık hata mesajı)
    - Browser crash → yeniden başlatma denemesi
    - Navigasyon timeout → ToolResult(success=False)
    - Sayfa yüklenirken hata → catch + fallback
"""

import asyncio
import logging
from typing import Dict, Optional

from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.BrowserTools")

_last_opened_url = None

# ── Playwright lazy import ──
_playwright_available = True
try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        TimeoutError as PlaywrightTimeout,
    )
except ImportError:
    _playwright_available = False
    logger.warning(
        "Playwright yüklü değil. Browser tool'ları devre dışı. "
        "Kurulum: pip install playwright && playwright install chromium"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BROWSER MANAGER — Paylaşımlı Browser Instance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BrowserManager:
    """
    Singleton-ish browser yöneticisi.
    Tüm browser tool'ları get_page() ile aynı instance üzerinden çalışır.

    Lifecycle:
        page = await BrowserManager.get_page()
        # ... sayfa üzerinde işlem ...
        # shutdown sırasında:
        await BrowserManager.close()

    Edge Cases:
        - İlk çağrıda browser launch (lazy init)
        - Browser crash → otomatik yeniden başlatma
        - close() sonrası get_page() → yeni browser başlatır
    """
    _playwright = None
    _browser: Optional["Browser"] = None
    _context: Optional["BrowserContext"] = None
    _lock = None # [V8.1] Lazy init via get_running_loop if needed

    @classmethod
    async def get_page(cls) -> "Page":
        """
        Yeni bir sayfa açar veya mevcut context'ten bir sayfa döndürür.
        Her tool çağrısında yeni tab açılır (izolasyon için).
        """
        if not _playwright_available:
            raise ImportError(
                "Playwright kurulu değil. "
                "Kurulum: pip install playwright && playwright install chromium"
            )

        if cls._browser is None or not cls._browser.is_connected():
            await cls._launch_browser()

        page = await cls._context.new_page()
        return page

    @classmethod
    async def _launch_browser(cls) -> None:
        """Browser'ı başlatır (chromium, headed)."""
        try:
            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(
                headless=False,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            cls._context = await cls._browser.new_context(
                viewport=None,  # Tam ekran
                no_viewport=True,
            )
            logger.info("Playwright browser başlatıldı (Chromium)")
        except Exception as e:
            logger.error(f"Browser başlatılamadı: {e}")
            raise

    @classmethod
    async def close(cls) -> None:
        """Browser'ı temiz kapatır."""
        try:
            if cls._browser:
                await cls._browser.close()
            if cls._playwright:
                await cls._playwright.stop()
        except Exception as e:
            logger.warning(f"Browser kapatma hatası: {e}")
        finally:
            cls._browser = None
            cls._context = None
            cls._playwright = None
            logger.info("Browser kapatıldı")

    @classmethod
    async def close_page(cls, page: "Page") -> None:
        """Tek bir sayfayı kapatır."""
        try:
            if page and not page.is_closed():
                await page.close()
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GOOGLE SEARCH TOOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GoogleSearchTool(BaseTool):
    """Google'da arama yapar ve sonuç sayfasını açık bırakır."""

    name = "google_search"
    description = "Google'da arama yapar"
    protocol_tag = "GOOGLE_SEARCH"
    parameters = {"query": {"type": "string", "description": "Aranacak terim"}}

    domain = "web"
    latency_ms = 2000
    reliability_score = 0.95
    pre_speak = "Google'da arıyorum Efendim."

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        """
        Google araması yapar.
        Kullanıcının mevcut Chrome penceresini kullanır.
        """
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(
                success=False,
                message="Arama sorgusu boş.",
                speak="Efendim, ne arayacağımı anlayamadım.",
            )

        url = f"https://www.google.com/search?q={query}"
        
        global _last_opened_url
        _last_opened_url = url
        
        import webbrowser
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, webbrowser.open, url)
            return ToolResult(
                success=True,
                verified=True,
                message=f"Google'da '{query}' aratıldı (Varsayılan Tarayıcı).",
                speak=f"'{query}' için Google'da arama yapıldı Efendim."
            )
        except Exception as e:
            return ToolResult(
                success=False,
                verified=False,
                error=str(e),
                message=f"Arama başarısız: {e}",
                speak="Efendim, tarayıcı açılamadı."
            )

    @staticmethod
    async def _fallback_webbrowser(url: str, query: str) -> ToolResult:
        """Playwright başarısız → webbrowser.open() fallback."""
        import webbrowser
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, webbrowser.open, url)
            return ToolResult(
                success=True,
                message=f"Google'da '{query}' aratıldı (webbrowser fallback).",
                speak=f"'{query}' aratıldı Efendim.",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                message=f"Arama başarısız: {e}",
                speak="Efendim, tarayıcı açılamadı.",
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WEB OPEN TOOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class WebOpenTool(BaseTool):
    """URL açar."""

    name = "web_open"
    description = "Verilen URL'yi tarayıcıda açar"
    protocol_tag = "WEB_OPEN"
    parameters = {"url": {"type": "string", "description": "Açılacak URL"}}

    domain = "web"
    latency_ms = 1500
    reliability_score = 0.98
    pre_speak = "Sayfayı açıyorum Efendim."

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        """
        URL'yi tarayıcıda açar.
        [V9.3] Öncelikle Chrome'u bulmaya çalışır.
        """
        url = params.get("url", "").strip()
        if not url:
            return ToolResult(
                success=False,
                message="URL boş.",
                speak="Efendim, açılacak adres belirtilmedi.",
            )

        # Protokol kontrolü
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Playwright mevcut değilse varsayılan tarayıcı fallback
        if not _playwright_available:
            import webbrowser
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, webbrowser.open, url)
                return ToolResult(
                    success=True,
                    verified=True,
                    message=f"'{url}' açıldı (Varsayılan Tarayıcı).",
                    speak=f"Sayfa açıldı Efendim.",
                )
            except Exception as e:
                return ToolResult(
                    success=False,
                    verified=False,
                    error=str(e),
                    message=f"Sayfa açılamadı: {e}",
                    speak="Efendim, tarayıcı açılamadı."
                )

        page = None
        try:
            page = await BrowserManager.get_page()
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            title = await page.title()

            return ToolResult(
                success=True,
                message=f"'{url}' açıldı. Başlık: {title}",
                speak=f"Sayfa açıldı Efendim.",
            )
        except Exception as e:
            logger.error(f"Web açma hatası: {e}")
            # Fallback
            import webbrowser
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, webbrowser.open, url)
            return ToolResult(
                success=True,
                message=f"'{url}' açıldı (webbrowser fallback).",
                speak="Sayfa açıldı Efendim.",
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLOSE LAST TAB TOOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CloseLastTabTool(BaseTool):
    """
    Sadece J.A.R.V.I.S. tarafından açılan son sekmeyi kapatır.
    """

    name = "close_last_tab"
    description = "Az önce açılan web sekmesini kapatır"
    protocol_tag = "CLOSE_LAST_TAB"
    parameters = {}

    domain = "web"
    latency_ms = 500
    reliability_score = 0.95

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        global _last_opened_url
        if _last_opened_url:
            import pygetwindow as gw
            import pyautogui
            import time
            
            chrome_windows = gw.getWindowsWithTitle('Chrome')
            if chrome_windows:
                try:
                    chrome_windows[0].activate()
                    time.sleep(0.3)
                except Exception as e:
                    pass
                    
            pyautogui.hotkey('ctrl', 'w')
            _last_opened_url = None
            return ToolResult(
                success=True,
                message="Son açılan sekme kapatıldı.",
                speak="Açtığım sekmeyi kapattım Efendim."
            )
        else:
            return ToolResult(
                success=False,
                message="Açılmış bir sekme yok.",
                speak="Kapatılacak açık sekme bulunamadı."
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  YOUTUBE SEARCH TOOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class YouTubeSearchTool(BaseTool):
    """YouTube'da arama yapar."""

    name = "youtube_search"
    description = "YouTube'da video arar"
    protocol_tag = "YT_SEARCH"
    parameters = {"query": {"type": "string", "description": "Aranacak video"}}

    domain = "web"
    latency_ms = 2000
    reliability_score = 0.93
    pre_speak = "YouTube'da arıyorum Efendim."

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(
                success=False,
                message="Arama sorgusu boş.",
                speak="Efendim, ne arayacağımı anlayamadım.",
            )

        url = f"https://www.youtube.com/results?search_query={query}"

        if not _playwright_available:
            import webbrowser
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, webbrowser.open, url)
            return ToolResult(
                success=True,
                message=f"YouTube'da '{query}' aratıldı.",
                speak=f"'{query}' YouTube'da aratıldı Efendim.",
            )

        page = None
        try:
            page = await BrowserManager.get_page()
            await page.goto(url, timeout=12000, wait_until="domcontentloaded")

            return ToolResult(
                success=True,
                message=f"YouTube'da '{query}' aratıldı.",
                speak=f"'{query}' YouTube'da aratıldı Efendim.",
            )
        except Exception as e:
            logger.error(f"YouTube arama hatası: {e}")
            import webbrowser
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, webbrowser.open, url)
            return ToolResult(
                success=True,
                message=f"YouTube'da '{query}' aratıldı (fallback).",
                speak=f"Aratıldı Efendim.",
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  YOUTUBE PLAY TOOL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class YouTubePlayTool(BaseTool):
    """
    YouTube'da arama yapıp ilk videoyu oynatır.

    Edge Cases:
        - Sonuç yoksa → YT_SEARCH'e fallback (otomatik)
        - Reklam engeli → timeout sonrası devam
        - Playwright yoksa → webbrowser ile arama URL'si aç
    """

    name = "youtube_play"
    description = "YouTube'da video arar ve ilk sonucu oynatır"
    protocol_tag = "YT_PLAY"
    parameters = {"query": {"type": "string", "description": "Oynatılacak video"}}

    domain = "web"
    latency_ms = 3000
    reliability_score = 0.85
    pre_speak = "YouTube'da çalıyorum Efendim."

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(
                success=False,
                message="Video sorgusu boş.",
                speak="Efendim, ne çalacağımı anlayamadım.",
            )

        search_url = f"https://www.youtube.com/results?search_query={query}"

        if not _playwright_available:
            import webbrowser
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, webbrowser.open, search_url)
            return ToolResult(
                success=True,
                message=f"YouTube'da '{query}' açıldı (webbrowser).",
                speak=f"'{query}' YouTube'da açıldı Efendim.",
            )

        page = None
        try:
            page = await BrowserManager.get_page()
            await page.goto(search_url, timeout=12000, wait_until="domcontentloaded")

            # İlk video bağlantısını bul ve tıkla
            video_link = page.locator('a#video-title').first
            await video_link.wait_for(timeout=5000)
            video_title = await video_link.get_attribute("title") or query
            await video_link.click()

            # Video sayfası yüklenmesini bekle
            await page.wait_for_load_state("domcontentloaded", timeout=8000)

            return ToolResult(
                success=True,
                message=f"YouTube'da '{video_title}' oynatılıyor.",
                speak=f"'{video_title}' oynatılıyor Efendim.",
            )

        except (PlaywrightTimeout if _playwright_available else Exception) as e:
            logger.warning(f"YouTube play timeout: {e}")
            return ToolResult(
                success=False,
                message=f"Video oynatılamadı: {e}",
                speak="Efendim, video oynatılamadı.",
            )
        except Exception as e:
            logger.error(f"YouTube play hatası: {e}")
            return ToolResult(
                success=False,
                message=f"YouTube hatası: {str(e)[:80]}",
                speak="Efendim, YouTube'da bir hata oluştu.",
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WebSearchTool [V9.6] — Gerçek Sonuç Döndüren Arama
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WebSearchTool(BaseTool):
    """
    [V9.6] İnternette araştırma yapan ve GERÇEK içerik döndüren araç.

    GoogleSearchTool'dan farkı:
        - GoogleSearchTool → Sadece Chrome'u URL ile açar (içerik yok)
        - WebSearchTool    → DuckDuckGo API + web snippet çeker,
                             data={"summary": "..."} ile gerçek metin döndürür

    Bu sayede [PLAN] içinde [STEP:WEB_SEARCH] interpolasyonu çalışır
    ve WhatsApp'a gerçek araştırma özeti gönderilebilir.

    Kullanım: [PROTOCOL: WEB_SEARCH] <sorgu>
    Plan örneği:
        [PLAN]
        1. WEB_SEARCH Lüleburgaz Atletik Takımı
        2. WHATSAPP_MESSAGE Eymen|[STEP:WEB_SEARCH]
        [/PLAN]
    """

    name              = "web_search"
    description       = (
        "İnternette arama yapar ve sonuçları METIN olarak döndürür. "
        "'Araştır ve mesaj at/gönder' gibi çok adımlı görevlerde kullan. "
        "Sadece tarayıcı açmak için değil, gerçek içerik almak için tercih et."
    )
    protocol_tag      = "WEB_SEARCH"
    domain            = "web"
    latency_ms        = 5000
    reliability_score = 0.85
    parameters        = {"query": {"type": "string", "description": "Arama sorgusu"}}

    # Groq modelini kullanarak Türkçe özet üretmek için (isteğe bağlı)
    _SUMMARY_PROMPT = (
        "Aşağıdaki arama sonuçlarını Türkçe olarak 3-5 cümleyle özetle. "
        "Sadece özeti yaz, başka bir şey ekleme:\n\n"
    )

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            query = params
        else:
            query = params.get("query", "")
            if not query and params:
                query = str(list(params.values())[0])
        query = query.strip()

        if not query:
            return ToolResult(
                success=False,
                verified=False,
                error="Fail",
                message="Arama sorgusu boş.",
                speak="Efendim, ne arayacağımı anlayamadım.",
            )

        # ── 1. Google Search API (Serper) ─────────
        raw_text = await self._fetch_google(query)

        # ── 2. Groq ile Türkçe özet üret (varsa) ────────────────────────
        summary = await self._summarize(raw_text, query, engine_context)

        if not summary:
            summary = raw_text  # özetlenemezse ham metni kullan

        if not summary:
            return ToolResult(
                success=False,
                verified=False,
                error="Fail",
                message=f"'{query}' için sonuç bulunamadı.",
                speak=f"Efendim, '{query}' hakkında bilgi bulamadım.",
            )

        logger.info(f"[WebSearch] '{query}' → {len(summary)} karakter özet")

        return ToolResult(
            success=True,
            verified=True,
            message=f"'{query}' araştırıldı. Özet: {summary}",
            speak=f"Efendim, araştırma sonucunu buldum: {summary}",
            data={"summary": summary, "query": query},
        )

    async def _fetch_google(self, query: str) -> str:
        """Serper.dev üzerinden gerçek Google Arama sonuçlarını çeker."""
        import os
        import json as _json
        import urllib.request
        
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            return "SİSTEM UYARISI: SERPER_API_KEY bulunamadı. Lütfen .env dosyasına ekleyin. Arama yapılamadı."
            
        loop = asyncio.get_running_loop()
        
        def _blocking_fetch() -> str:
            url = "https://google.serper.dev/search"
            payload = _json.dumps({"q": query, "gl": "tr", "hl": "tr"}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json"
            })
            
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = _json.loads(resp.read().decode("utf-8"))
                    
                snippets = []
                # 1. Knowledge Graph (Google'ın kesin bilgi paneli - Yaş, Gol sayısı vb. buradadır)
                if "knowledgeGraph" in result:
                    kg = result["knowledgeGraph"]
                    if "description" in kg: snippets.append(f"Bilgi Paneli: {kg['description']}")
                    for attr in kg.get("attributes", {}):
                        snippets.append(f"{attr}: {kg['attributes'][attr]}")
                        
                # 2. Answer Box (Google'ın doğrudan verdiği yanıt)
                if "answerBox" in result:
                    ans = result["answerBox"].get("answer", "")
                    snip = result["answerBox"].get("snippet", "")
                    if ans: snippets.append(f"Google Kesin Yanıtı: {ans}")
                    if snip: snippets.append(f"Özet: {snip}")
                    
                # 3. Organik Sonuçlar
                for item in result.get("organic", [])[:4]:
                    snippets.append(item.get("snippet", ""))
                    
                return "\n".join(snippets)
            except Exception as e:
                logger.error(f"[WebSearch] Google API hatası: {e}")
                return f"Arama hatası: {e}"
                
        try:
            return await asyncio.wait_for(loop.run_in_executor(None, _blocking_fetch), timeout=15)
        except asyncio.TimeoutError:
            return "Arama zaman aşımına uğradı."

    async def _summarize(self, raw_text: str, query: str, engine_context: dict) -> str:
        """Groq API ile metni Türkçe özetler. Başarısız olursa raw_text döner."""
        if not raw_text:
            return ""

        ctx = engine_context or {}
        brain = ctx.get("brain")
        if brain is None:
            return raw_text  # brain yoksa ham metin kullan

        try:
            import os
            from groq import AsyncGroq
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                return raw_text

            client = AsyncGroq(api_key=api_key)
            model = getattr(brain.config, "brain_models", ["llama-3.3-70b-versatile"])[0]

            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"{self._SUMMARY_PROMPT}"
                            f"Konu: {query}\n\n"
                            f"Arama Sonuçları:\n{raw_text}"
                        )
                    }
                ],
                max_tokens=400,
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[WebSearch] Groq özet hatası: {e}")
            return raw_text  # hata olursa ham metin yeterli