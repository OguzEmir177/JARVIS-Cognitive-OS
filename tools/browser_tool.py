"""[V8.0] J.A.R.V.I.S. Browser Tools (Playwright Async)

━━━━━━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━━━━━━

Asynchronous web automation tools with Playwright.



Tools:

    GoogleSearchTool → GOOGLE_SEARCH → Google search

    WebOpenTool → WEB_OPEN → open URL

    YouTubeSearchTool → YT_SEARCH → YouTube search

    YouTubePlayTool → YT_PLAY → YouTube video playback



Design Decisions:

    Why Playwright and not webbrowser?

    → webbrowser only opens URL, no checking.

    → Playwright: click, write, hold, screenshot.

    → Async-native: Native compatibility with asyncio event loop.



    Why shared browser instance?

    → Separate browser for each tool = high memory + slow startup.

    → BrowserManager lazy-initiates the singleton browser.

    → All tools share the same browser context.



Edge Cases:

    - If Playwright is not installed → ToolExecutionError (obvious error message)

    - Browser crash → restart attempt

    - Navigation timeout → ToolResult(success=False)

    - Error loading page → catch + fallback"""



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

        "Playwright is not installed. Browser tools are disabled."

        "Kurulum: pip install playwright && playwright install chromium"

    )





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# BROWSER MANAGER — Shared Browser Instance

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━





class BrowserManager:

    """Singleton-ish browser manager.

    All browser tools work on the same instance with get_page().



    Lifecycle:

        page = await BrowserManager.get_page()

        # ... action on the page ...

        # during shutdown:

        await BrowserManager.close()



    Edge Cases:

        - Browser launch (lazy init) on first call

        - Browser crash → automatic restart

        - after close() get_page() → starts a new browser"""

    _playwright = None

    _browser: Optional["Browser"] = None

    _context: Optional["BrowserContext"] = None

    _lock = None # [V8.1] Lazy init via get_running_loop if needed



    @classmethod

    async def get_page(cls) -> "Page":

        """Opens a new page or returns a page from the current context.

        A new tab is opened with each tool call (for isolation)."""

        if not _playwright_available:

            raise ImportError(

                "Playwright is not installed."

                "Kurulum: pip install playwright && playwright install chromium"

            )



        if cls._browser is None or not cls._browser.is_connected():

            await cls._launch_browser()



        page = await cls._context.new_page()

        return page



    @classmethod

    async def _launch_browser(cls) -> None:

        """Starts the browser (chromium, headed)."""

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

            logger.info("Playwright browser launched (Chromium)")

        except Exception as e:

            logger.error(f"Failed to initialize browser: {e}")

            raise



    @classmethod

    async def close(cls) -> None:

        """Closes the browser cleanly."""

        try:

            if cls._browser:

                await cls._browser.close()

            if cls._playwright:

                await cls._playwright.stop()

        except Exception as e:

            logger.warning(f"Browser closing error: {e}")

        finally:

            cls._browser = None

            cls._context = None

            cls._playwright = None

            logger.info("Browser is closed")



    @classmethod

    async def close_page(cls, page: "Page") -> None:

        """Closes a single page."""

        try:

            if page and not page.is_closed():

                await page.close()

        except Exception:

            pass





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#  GOOGLE SEARCH TOOL

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━





class GoogleSearchTool(BaseTool):

    """He searches on Google and leaves the results page open."""



    name = "google_search"

    description = "searches on Google"

    protocol_tag = "GOOGLE_SEARCH"

    parameters = {"query": {"type": "string", "description": "Aranacak terim"}}



    domain = "web"

    latency_ms = 2000

    reliability_score = 0.95

    pre_speak = "I'm searching on Google, Sir."



    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:

        """Does a Google search.

        Uses the user's existing Chrome window."""

        query = params.get("query", "").strip()

        if not query:

            return ToolResult(

                success=False,

                message="The search query is empty.",

                speak="Sir, I couldn't understand what to look for.",

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

                message=f"Searched for '{query}' on Google (Default Browser).",

                speak=f"Searched on Google for '{query}' Sir."

            )

        except Exception as e:

            return ToolResult(

                success=False,

                verified=False,

                error=str(e),

                message=f"Search failed: {e}",

                speak="Sir, the browser could not be opened."

            )



    @staticmethod

    async def _fallback_webbrowser(url: str, query: str) -> ToolResult:

        """Playwright failed → webbrowser.open() fallback."""

        import webbrowser

        loop = asyncio.get_running_loop()

        try:

            await loop.run_in_executor(None, webbrowser.open, url)

            return ToolResult(

                success=True,

                message=f"Searched for '{query}' on Google (webbrowser fallback).",

                speak=f"Searched for '{query}' Sir.",

            )

        except Exception as e:

            return ToolResult(

                success=False,

                message=f"Search failed: {e}",

                speak="Sir, the browser could not be opened.",

            )





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#  WEB OPEN TOOL

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━





class WebOpenTool(BaseTool):

    """Opens URL."""



    name = "web_open"

    description = "Opens the given URL in the browser"

    protocol_tag = "WEB_OPEN"

    parameters = {"url": {"type": "string", "description": "URL to open"}}



    domain = "web"

    latency_ms = 1500

    reliability_score = 0.98

    pre_speak = "I am opening the page, Sir."



    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:

        """Opens the URL in the browser.

        [V9.3] First tries to find Chrome."""

        url = params.get("url", "").strip()

        if not url:

            return ToolResult(

                success=False,

                message="URL is empty.",

                speak="Sir, the address to be opened was not specified.",

            )



        # Protocol control

        if not url.startswith(("http://", "https://")):

            url = f"https://{url}"



        # Default browser fallback if Playwright is not available

        if not _playwright_available:

            import webbrowser

            loop = asyncio.get_running_loop()

            try:

                await loop.run_in_executor(None, webbrowser.open, url)

                return ToolResult(

                    success=True,

                    verified=True,

                    message=f"'{url}' is opened (Default Browser).",

                    speak=f"The page has been opened, Sir.",

                )

            except Exception as e:

                return ToolResult(

                    success=False,

                    verified=False,

                    error=str(e),

                    message=f"Could not open page: {e}",

                    speak="Sir, the browser could not be opened."

                )



        page = None

        try:

            page = await BrowserManager.get_page()

            await page.goto(url, timeout=15000, wait_until="domcontentloaded")

            title = await page.title()



            return ToolResult(

                success=True,

                message=f"'{url}' is opened. Title: {title}",

                speak=f"The page has been opened, Sir.",

            )

        except Exception as e:

            logger.error(f"Web opening error: {e}")

            # Fallback

            import webbrowser

            loop = asyncio.get_running_loop()

            await loop.run_in_executor(None, webbrowser.open, url)

            return ToolResult(

                success=True,

                message=f"'{url}' opened (webbrowser fallback).",

                speak="The page has been opened, Sir.",

            )





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#  CLOSE LAST TAB TOOL

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━



class CloseLastTabTool(BaseTool):

    """Just J.A.R.V.I.S. Closes the last tab opened by."""



    name = "close_last_tab"

    description = "Closes the web tab that was just opened"

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

                    await asyncio.sleep(0.3)

                except Exception as e:

                    pass

                    

            pyautogui.hotkey('ctrl', 'w')

            _last_opened_url = None

            return ToolResult(

                success=True,

                message="The last opened tab has been closed.",

                speak="I closed the tab I opened, Sir."

            )

        else:

            return ToolResult(

                success=False,

                message="There are no tabs open.",

                speak="No open tabs were found to close."

            )





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#  YOUTUBE SEARCH TOOL

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━





class YouTubeSearchTool(BaseTool):

    """Searches YouTube."""



    name = "youtube_search"

    description = "Searches for videos on YouTube"

    protocol_tag = "YT_SEARCH"

    parameters = {"query": {"type": "string", "description": "Aranacak video"}}



    domain = "web"

    latency_ms = 2000

    reliability_score = 0.93

    pre_speak = "I'm looking on YouTube Sir."



    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:

        query = params.get("query", "").strip()

        if not query:

            return ToolResult(

                success=False,

                message="The search query is empty.",

                speak="Sir, I couldn't understand what to look for.",

            )



        url = f"https://www.youtube.com/results?search_query={query}"



        if not _playwright_available:

            import webbrowser

            loop = asyncio.get_running_loop()

            await loop.run_in_executor(None, webbrowser.open, url)

            return ToolResult(

                success=True,

                message=f"Searched for '{query}' on YouTube.",

                speak=f"Searched for '{query}' on YouTube Sir.",

            )



        page = None

        try:

            page = await BrowserManager.get_page()

            await page.goto(url, timeout=12000, wait_until="domcontentloaded")



            return ToolResult(

                success=True,

                message=f"Searched for '{query}' on YouTube.",

                speak=f"Searched for '{query}' on YouTube Sir.",

            )

        except Exception as e:

            logger.error(f"YouTube search error: {e}")

            import webbrowser

            loop = asyncio.get_running_loop()

            await loop.run_in_executor(None, webbrowser.open, url)

            return ToolResult(

                success=True,

                message=f"Searched for '{query}' on YouTube (fallback).",

                speak=f"He was searched, Sir.",

            )





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#  YOUTUBE PLAY TOOL

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━





class YouTubePlayTool(BaseTool):

    """Searches YouTube and plays the first video.



    Edge Cases:

        - If no results → fallback to YT_SEARCH (automatic)

        - Ad blocking → continue after timeout

        - If there is no Playwright → open search URL with webbrowser"""



    name = "youtube_play"

    description = "Searches for videos on YouTube and plays the first result"

    protocol_tag = "YT_PLAY"

    parameters = {"query": {"type": "string", "description": "Video to play"}}



    domain = "web"

    latency_ms = 3000

    reliability_score = 0.85

    pre_speak = "I'm playing on YouTube Sir."



    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:

        query = params.get("query", "").strip()

        if not query:

            return ToolResult(

                success=False,

                message="Video query is empty.",

                speak="Sir, I couldn't understand what to play.",

            )



        search_url = f"https://www.youtube.com/results?search_query={query}"



        if not _playwright_available:

            import webbrowser

            loop = asyncio.get_running_loop()

            await loop.run_in_executor(None, webbrowser.open, search_url)

            return ToolResult(

                success=True,

                message=f"Opened '{query}' on YouTube (webbrowser).",

                speak=f"'{query}' opened on YouTube Sir.",

            )



        page = None

        try:

            page = await BrowserManager.get_page()

            await page.goto(search_url, timeout=12000, wait_until="domcontentloaded")



            # Find and click the first video link

            video_link = page.locator('a#video-title').first

            await video_link.wait_for(timeout=5000)

            video_title = await video_link.get_attribute("title") or query

            await video_link.click()



            # Wait for the video page to load

            await page.wait_for_load_state("domcontentloaded", timeout=8000)



            return ToolResult(

                success=True,

                message=f"Playing '{video_title}' on YouTube.",

                speak=f"Playing '{video_title}' Sir.",

            )



        except (PlaywrightTimeout if _playwright_available else Exception) as e:

            logger.warning(f"YouTube play timeout: {e}")

            return ToolResult(

                success=False,

                message=f"Video could not be played: {e}",

                speak="Sir, the video could not be played.",

            )

        except Exception as e:

            logger.error(f"YouTube play error: {e}")

            return ToolResult(

                success=False,

                message=f"YouTube error: {str(e)[:80]}",

                speak="Sir, there was an error on YouTube.",

            )





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# WebSearchTool [V9.6] — Search That Returns Real Results

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━



class WebSearchTool(BaseTool):

    """[V9.6] Tool that searches the internet and returns REAL content.



    Difference from GoogleSearchTool:

        - GoogleSearchTool → Just opens Chrome with URL (no content)

        - WebSearchTool → DuckDuckGo API + extracts web snippets,

                             returns actual text with data={"summary": "..."}



    This way [STEP:WEB_SEARCH] interpolation works in [PLAN]

    and actual research summary can be sent to WhatsApp.



    Usage: [PROTOCOL: WEB_SEARCH] <query>

    Plan example:

        [PLAN]

        1. WEB_SEARCH Lüleburgaz Athletic Team

        2. WHATSAPP_MESSAGE Eymen|[STEP:WEB_SEARCH]

        [/PLAN]"""



    name              = "web_search"

    description       = (

        "Searches the internet and returns results as TEXT."

        "Use it for multi-step tasks like 'search and text/send'."

        "Choose it to get real content, not just to open a browser."

    )

    protocol_tag      = "WEB_SEARCH"

    domain            = "web"

    latency_ms        = 5000

    reliability_score = 0.85

    parameters        = {"query": {"type": "string", "description": "Arama sorgusu"}}



    # To produce a Turkish summary using the Groq model (optional)

    _SUMMARY_PROMPT = (

        "Summarize the search results below in 3-5 sentences in Turkish."

        "Just write the summary, don't add anything else:\n\n"

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

                message="The search query is empty.",

                speak="Sir, I couldn't understand what to look for.",

            )



        # ── 1. Google Search API (Serper) ─────────

        raw_text = await self._fetch_google(query)



        # ── 2. Generate Turkish summary with Groq (if available) ────────────────────────

        summary = await self._summarize(raw_text, query, engine_context)



        if not summary:

            summary = raw_text  # use raw text if cannot be summarized



        if not summary:

            return ToolResult(

                success=False,

                verified=False,

                error="Fail",

                message=f"No results found for '{query}'.",

                speak=f"Sir, I couldn't find information about '{query}'.",

            )



        logger.info(f"[WebSearch] '{query}' → {len(summary)} character summary")



        return ToolResult(

            success=True,

            verified=True,

            message=f"'{query}' searched. Summary: {summary}",

            speak=f"Sir, I found the result of my research: {summary}",

            data={"summary": summary, "query": query},

        )



    async def _fetch_google(self, query: str) -> str:

        """It pulls real Google Search results via Serper.dev."""

        import os

        import json as _json

        import urllib.request

        

        api_key = os.getenv("SERPER_API_KEY")

        if not api_key:

            return "SYSTEM WARNING: SERPER_API_KEY not found. Please add it to the .env file. The search could not be made."

            

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

                # 1. Knowledge Graph (Google's definitive knowledge panel - Age, Goals etc. are here)

                if "knowledgeGraph" in result:

                    kg = result["knowledgeGraph"]

                    if "description" in kg: snippets.append(f"Bilgi Paneli: {kg['description']}")

                    for attr in kg.get("attributes", {}):

                        snippets.append(f"{attr}: {kg['attributes'][attr]}")

                        

                # 2. Answer Box (Google's direct answer)

                if "answerBox" in result:

                    ans = result["answerBox"].get("answer", "")

                    snip = result["answerBox"].get("snippet", "")

                    if ans: snippets.append(f"Google Definitive Answer: {ans}")

                    if snip: snippets.append(f"Summary: {snip}")

                    

                #3. Organic Results

                for item in result.get("organic", [])[:4]:

                    snippets.append(item.get("snippet", ""))

                    

                return "\n".join(snippets)

            except Exception as e:

                logger.error(f"[WebSearch] Google API error: {e}")

                return f"Search error: {e}"

                

        try:

            return await asyncio.wait_for(loop.run_in_executor(None, _blocking_fetch), timeout=15)

        except asyncio.TimeoutError:

            return "The call has timed out."



    async def _summarize(self, raw_text: str, query: str, engine_context: dict) -> str:

        """Summarizes the text in Turkish with Groq API. If unsuccessful, raw_text is returned."""

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

                            f"Search Results:\n{raw_text}"

                        )

                    }

                ],

                max_tokens=400,

                temperature=0.3,

            )

            return resp.choices[0].message.content.strip()

        except Exception as e:

            logger.warning(f"[WebSearch] Groq summary error: {e}")

            return raw_text  # in case of an error, the raw text is sufficient