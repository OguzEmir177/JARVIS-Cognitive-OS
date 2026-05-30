"""[V15.0] J.A.R.V.I.S. Deterministic Semantic Tool Router
━━━━━━━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Routing pipeline:
  STAGE 1: KEYWORD-FIRST deterministic matching (priority rules)
  STAGE 2: SEMANTIC embedding matching (fuzzy fallback)
  STAGE 3: AMBIGUITY gate → LLM fallback

V15.0 Changes:
  - FILE_* intents are separated with 99% accuracy
  - FOLDER_OPEN vs APP_OPEN clear distinction
  - FILE_WRITE context-aware: path|content format
  - FILE_DELETE full implementation
  - Overengineering removed, determinism prioritized"""
import logging, time, json, os, re
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("JARVIS.ToolRouter")

@dataclass
class RouteMatch:
    tool_tag: str
    params: Dict[str, Any]
    confidence: float
    is_forced: bool = False
    reasoning: str = ""

    def __getitem__(self, index):
        if index == 0:
            return self
        raise IndexError("RouteMatch acts as a single-element list for compatibility")

@dataclass
class ToolProfile:
    """Runtime performance profile for a tool."""
    tag: str
    total_calls: int = 0
    successes: int = 0
    failures: int = 0
    avg_latency_ms: float = 0.0
    last_used: float = 0.0
    context_scores: Dict[str, float] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.successes / max(self.total_calls, 1)

    @property
    def reliability_score(self) -> float:
        return (self.successes + 1) / (self.total_calls + 2)


class AutonomousToolRouter:
    """
    [V15.0] Deterministic-First Tool Router

    Priority:
      1. KEYWORD-FIRST: Deterministic Turkish verb patterns
      2. SEMANTIC: Embedding cosine similarity
      3. AMBIGUITY: If top-2 too close → LLM
    """

    PROFILE_PATH = "memory_db/tool_profiles.json"

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        logger.info(f"Loading semantic engine: {model_name}")
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

        self.tool_definitions = {
            "MAP_SHOW": ["show location on map", "where is this place", "find address",
                         "show on map", "where is this?", "find coordinates", "yol tarifi",
                         "harita", "Istanbul map", "Istanbul on the map", "show city on map"],
            "CHART_SHOW": ["create data chart", "visualize statistics", "draw graph",
                           "create chart", "visualize data", "tablo yap", "istatistik"],
            "APP_OPEN": ["launch application", "open program", "start software",
                         "start the application", "open the program", "run",
                         "open spotify", "open youtube", "open chrome", "open discord",
                         "open steam", "open browser", "open the app"],
            "APP_KILL": ["close application", "terminate process", "stop program",
                         "close the application", "end", "durdur", "close the program"],
            "WEB_SEARCH": ["search internet", "find information online",
                           "internette ara", "bilgi bul", "research", "google",
                           "ne demek", "nedir", "how old", "kimdir"],
            "YT_SEARCH": ["search youtube", "find video", "search on youtube", "video bul"],
            "YT_PLAY": ["play youtube video", "watch video", "play on youtube", "video izle"],
            "WHATSAPP_MESSAGE": ["send whatsapp message", "send message", "whatsapp yaz", "mesaj at"],
            "REMEMBER": ["remember this", "save to memory", "remember this", "kaydet"],
            "SYSTEM_POWER": ["shutdown computer", "restart", "turn off the computer", "reboot"],
            "WEB_OPEN": ["open website", "go to url", "open site", "adrese git", "open website"],
            "FILE_LATEST": ["find latest downloaded file", "son indirilen dosya",
                            "What did I download last time?", "find last file", "The last file I downloaded"],
            "FILE_CREATE": ["create file", "create file", "create txt", "yeni dosya", "dosya yarat"],
            "FILE_WRITE": ["write to file", "dosyaya yaz", "add file content", "write in"],
            "FILE_READ": ["read file", "dosya oku", "file content", "what does it say"],
            "FILE_DELETE": ["delete file", "dosya sil", "remove file", "delete the file"],
            "FOLDER_OPEN": ["open folder", "open folder", "open directory", "open folder"],
            "YOUTUBE_STRATEGY": ["youtube stratejisi", "video fikri", "thumbnail promptu", "challenge fikri", "channel plan", "youtube planla"],
            "ANALIZ_PRO": ["connect to analysis pro", "analysis application", "server health status", "analiz durumu", "analysis link"],
        }

        # Pre-compute embeddings
        self.target_embeddings = {}
        for tag, phrases in self.tool_definitions.items():
            self.target_embeddings[tag] = self.model.encode(phrases)

        self.profiles: Dict[str, ToolProfile] = {}
        self._load_profiles()

    @property
    def _profiles(self):
        return self.profiles

    def route(self, user_input: str, world_context: Dict[str, Any] = None,
              context: Dict[str, Any] = None) -> Optional[RouteMatch]:
        """
        [V15.0] KEYWORD-FIRST + semantic + historical routing.
        """
        world_context = world_context or context

        # ═══════════════════════════════════════════════════
        #  STAGE 1: KEYWORD-FIRST DETERMINISTIC
        # ═══════════════════════════════════════════════════
        keyword_match = self._keyword_route(user_input)
        if keyword_match:
            logger.info(f"Router: KEYWORD HIT → {keyword_match.tool_tag} ({user_input[:50]!r})")
            return keyword_match

        # ═══════════════════════════════════════════════════
        #  STAGE 2: SEMANTIC ROUTING
        # ═══════════════════════════════════════════════════
        input_emb = self.model.encode([user_input])[0]

        results = []
        for tag, embeddings in self.target_embeddings.items():
            sims = np.dot(embeddings, input_emb) / (
                np.linalg.norm(embeddings, axis=1) * np.linalg.norm(input_emb) + 1e-8
            )
            semantic_score = float(np.max(sims))
            profile = self.profiles.get(tag)
            reliability = profile.reliability_score if profile else 0.5
            hist_factor = 0.7 + (reliability * 0.3)

            ctx_boost = 0.0
            if world_context:
                app = world_context.get("active_app", "").lower()
                if any(b in app for b in ["chrome", "firefox", "edge"]):
                    if tag in ("WEB_SEARCH", "WEB_OPEN", "YT_SEARCH"):
                        ctx_boost = 0.05

            final = (semantic_score * 0.7) + (reliability * 0.2) + (ctx_boost * 0.1)
            results.append((tag, final, semantic_score))

        results.sort(key=lambda x: x[1], reverse=True)
        best_tag, best_score, raw_semantic = results[0]

        # AMBIGUITY DETECTION
        if len(results) >= 2:
            second_score = results[1][1]
            gap = best_score - second_score
            if gap < 0.03 and best_score < 0.80:
                logger.info(f"Router: AMBIGUOUS → LLM'e devrediliyor")
                return None

        logger.info(f"Router: {best_tag} (combined={best_score:.3f}, semantic={raw_semantic:.3f})")

        if best_score > 0.70:
            return RouteMatch(tool_tag=best_tag, params={"query": user_input},
                              confidence=best_score, is_forced=True,
                              reasoning=f"High-confidence semantic ({raw_semantic:.3f})")
        elif best_score > 0.45:
            return RouteMatch(tool_tag=best_tag, params={"query": user_input},
                              confidence=best_score, is_forced=False,
                              reasoning=f"Moderate match ({raw_semantic:.3f})")
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  [V15.0] KEYWORD-FIRST ROUTING
    #
    # PRIORITY ORDER (high to low):
    # 1. FILE operations (most specific)
    #    2. FOLDER operations
    #3. CHAT (leave it to LLM)
    #    4. APP operations
    #    5. Web/search operations
    #    6. System operations
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _keyword_route(self, user_input: str) -> Optional[RouteMatch]:
        # Remove periods, exclamation marks and question marks so that Regex anchors ($) are not broken
        text = user_input.strip().lower().rstrip('.!?')

        # ── 1. FILE_DELETE: "delete X", "delete file", "delete test.txt" ──
        # Check BEFORE — "file" + "delete" combination for sure delete
        if self._is_file_delete(text):
            file_ref = self._extract_file_ref(text)
            return RouteMatch(
                tool_tag="FILE_DELETE",
                params={"file_path": file_ref},
                confidence=0.99, is_forced=True,
                reasoning=f"FILE_DELETE: sil keyword + dosya ref"
            )

        # ── 2. FILE_READ: "read", "show content", "what it says" ──
        if self._is_file_read(text):
            file_ref = self._extract_file_ref(text)
            return RouteMatch(
                tool_tag="FILE_READ",
                params={"file_path": file_ref},
                confidence=0.99, is_forced=True,
                reasoning=f"FILE_READ: oku keyword"
            )

        # ── 3. FILE_WRITE: "Write Y to/into X", "append to file" ──
        if self._is_file_write(text):
            return RouteMatch(
                tool_tag="FILE_WRITE",
                params={"file_path_and_content": user_input},
                confidence=0.99, is_forced=True,
                reasoning="FILE_WRITE: yaz/ekle keyword"
            )

        # ── 4. FILE_CREATE: "create", "create" + file context ──
        if self._is_file_create(text):
            return RouteMatch(
                tool_tag="FILE_CREATE",
                params={"file_path": user_input},
                confidence=0.99, is_forced=True,
                reasoning="FILE_CREATE: create keyword"
            )

        # ── 5. FILE_LATEST: "son indirilen" ──
        if "son indiri" in text or ("son" in text and "dosya" in text and "indiri" in text):
            return RouteMatch(
                tool_tag="FILE_LATEST",
                params={"dir_path": "indirilenler"},
                confidence=0.98, is_forced=True,
                reasoning="FILE_LATEST: son indirilen keyword"
            )

        # ── 6. FOLDER_OPEN: open folder — check BEFORE APP_OPEN ──
        if self._is_folder_open(text):
            folder_name = self._extract_folder_name(text)
            return RouteMatch(
                tool_tag="FOLDER_OPEN",
                params={"folder_path": folder_name},
                confidence=0.99, is_forced=True,
                reasoning=f"FOLDER_OPEN: folder keyword → {folder_name}"
            )

        # ── 7. CHAT / KNOWLEDGE / MATHEMATICS → LLM ──
        chat_patterns = [
            r"\b(hello|hi|what's up|how are you|thank you|thank you|excellent)\b",
            r'\b(sen kimsin|neler yapabilirsin|kendinden bahset)\b',
            r'\b(add|subtract|multiply|divide|calculate|what is it|prime|mathematics)\b',
        ]
        for pat in chat_patterns:
            if re.search(pat, text):
                return None

        # ── 8. APP_KILL: "X kapat" ──
        kill_patterns = [
            r'^(.+?)(?:\'?[yiiuü])\s+close$',
            r'^(.+?)\s+kapat$',
            r'^kapat\s+(.+)$',
        ]
        for pat in kill_patterns:
            m = re.match(pat, text)
            if m:
                app_name = m.group(1).strip()
                if any(w in app_name for w in ['bilgisayar', 'sistem', 'pc', 'windows']):
                    return RouteMatch(tool_tag="SYSTEM_POWER", params={"query": ""},
                                      confidence=0.98, is_forced=True)
                # if folder is not closed
                if "folder" not in app_name and "dosya" not in app_name:
                    return RouteMatch(tool_tag="APP_KILL", params={"query": app_name},
                                      confidence=0.98, is_forced=True)

        # ── 9. APP_OPEN: "X open", "X start", "X run" ──
        open_patterns = [
            r"^(.+?)(?:'?[yiiuü])\s+aç$",
            r"^(.+?)\s+open$",
            r"^(.+?)(?:'?[yiiuü])\s+start$",
            r"^(.+?)\s+start$",
            r"^(.+?)(?:'?[yiiuü])\s+run$",
            r"^(.+?)\s+run$",
            r"^open\s+(.+)$",
        ]
        for pat in open_patterns:
            m = re.match(pat, text)
            if m:
                app_name = m.group(1).strip()
                # Search verbs control
                if any(text.endswith(w) for w in ['arat', ' ara', 'research']):
                    break
                # If contains folder/file → not APP_OPEN
                if "folder" in app_name or "dizin" in app_name:
                    break
                if app_name and len(app_name) >= 2:
                    return RouteMatch(
                        tool_tag="APP_OPEN",
                        params={"query": app_name},
                        confidence=0.98, is_forced=True,
                        reasoning=f"APP_OPEN: 'Open {app_name}'"
                    )

        # ── 10. YT_SEARCH ──
        yt_search = re.match(r"youtube'?(?:da|ta|de|te)\s+(ara|arat|bul)\s*(.*)$", text)
        if yt_search:
            query = yt_search.group(2).strip() or user_input
            return RouteMatch(tool_tag="YT_SEARCH", params={"query": query},
                              confidence=0.95, is_forced=True, reasoning="YT_SEARCH")

        # ── 11. WEB_SEARCH ──
        search_patterns = [
            r'^(.+?)\s+research$',
            r'^(.+?)(?:\'?[yiiuü])\s+research$',
            r'^(.+?)\s+nedir$',
            r'^(.+?)\s+ne\s+demek$',
            r'^(.+?)\s+kimdir$',
            r'^(.+?)\s+how\s+old$',
        ]
        for pat in search_patterns:
            m = re.match(pat, text)
            if m:
                query = m.group(1).strip()
                return RouteMatch(tool_tag="WEB_SEARCH", params={"query": query},
                                  confidence=0.92, is_forced=True)

        # ── 12. GOOGLE_SEARCH ──
        google_search = re.match(r"google'?(?:da|de)\s+(?:ara|arat)\s*(.*)$", text)
        if google_search:
            query = google_search.group(1).strip() or user_input
            return RouteMatch(tool_tag="GOOGLE_SEARCH", params={"query": query},
                              confidence=0.95, is_forced=True)

        # ── 13. WHATSAPP_MESSAGE ──
        wa_patterns = [
            r'(.+?)(?:\'?[yeaıuü])[wha]?\s+message\s+(?:at|send|write)',
            r'message\s+(?:at|send|write)\s+(.+)',
        ]
        for pat in wa_patterns:
            m = re.search(pat, text)
            if m:
                return RouteMatch(tool_tag="WHATSAPP_MESSAGE", params={"query": user_input},
                                  confidence=0.93, is_forced=True)

        # ── 14. SCHEDULE ──
        schedule_match = re.search(r'(\d+)\s*(dakika|saat|dk|sa)\s*sonra\s+(.+)', text)
        if schedule_match:
            return RouteMatch(tool_tag="SCHEDULE", params={"query": user_input},
                              confidence=0.95, is_forced=True)

        # ── 15. YOUTUBE_STRATEGY (EXACT ROUTE) ──
        youtube_keywords = ["thumbnail", "video fikri", "challenge", "youtube planla", "kanal stratejisi"]
        # If it says 'youtube' but it DOES NOT have app_open words like 'open', 'application', 'launch', be a strategist.
        is_youtube_strategy = any(w in text for w in youtube_keywords) or ("youtube" in text and not any(kw in text for kw in ["hungry", "uygulama", "start", "run"]))
        
        if is_youtube_strategy:
            return RouteMatch(tool_tag="YOUTUBE_STRATEGY", params={"request": user_input},
                              confidence=0.99, is_forced=True, reasoning="YOUTUBE_STRATEGY keyword")

        # ── 16. ANALYSIS PRO (PRECISE GUIDANCE) ──
        analiz_keywords = ["analiz pro", "analysis application", "server health", "connection test", "kanal raporu", "son durum", "research trends", "rakip analizi"]
        # If there is 'open', 'start', 'run' this is an APP_OPEN request, don't ping!
        is_analiz_pro = any(w in text for w in analiz_keywords) and not any(kw in text for kw in ["hungry", "start", "run"])
        
        if is_analiz_pro:
            return RouteMatch(tool_tag="ANALIZ_PRO", params={"query": user_input},
                              confidence=0.99, is_forced=True, reasoning="ANALIZ_PRO keyword")

        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  INTENT DETECTION HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _is_file_delete(self, text: str) -> bool:
        """FILE_DELETE: "delete file/txt", "delete test.txt", "delete file"
        Except: "delete chrome" (remove app), "delete discord" etc."""
        has_sil = "sil" in text
        if not has_sil:
            return False
        # Delete file if it contains extension like "file" or ".txt"/".py"/".json"
        has_file_indicator = (
            "dosya" in text or
            "txt" in text or
            re.search(r'\.\w{2,4}', text) is not None or
            "file" in text or
            "file" in text
        )
        return has_file_indicator

    def _is_file_read(self, text: str) -> bool:
        """FILE_READ: "read file", "read test.txt", "read file", "show contents"
    """
        read_keywords = ["oku", "show content", "what does it say", "what is the content"]
        has_read = any(kw in text for kw in read_keywords)
        if not has_read:
            return False
        # "file" or extension or context word
        context_keywords = ["dosya", "txt", "contents"]
        has_file = (
            any(kw in text for kw in context_keywords) or
            re.search(r'\.\w{2,4}', text) is not None
        )
        return has_file

    def _is_file_write(self, text: str) -> bool:
        """FILE_WRITE: "Write Y into X", "append to file", "write into"
        Except: Just "type" alone (can be a speech command)"""
        write_keywords = ["write in", "dosyaya yaz", "dosyaya ekle", "add content", "write into"]
        if any(kw in text for kw in write_keywords):
            return True
        # "Write X" pattern — if context contains file
        if re.search(r'\byaz\b', text) and (
            "dosya" in text or
            re.search(r'\.\w{2,4}', text) is not None or
            "into" in text
        ):
            return True
        return False

    def _is_file_create(self, text: str) -> bool:
        """FILE_CREATE: "create file", "create test.txt", "create X on desktop"
        Except: "create plan" (not document), "create list" etc."""
        create_keywords = ["create", "yarat"]
        has_create = any(kw in text for kw in create_keywords)
        if not has_create:
            return False
        # File context
        file_keywords = ["txt", "dosya", "metin", "belge", ".py", ".json", ".md", ".log"]
        has_file = (
            any(kw in text for kw in file_keywords) or
            re.search(r'\.\w{2,4}', text) is not None
        )
        return has_file

    def _is_folder_open(self, text: str) -> bool:
        """FOLDER_OPEN: "open folder", "downloads folder", "documents directory"
    """
        folder_words = ["folder", "dizin"]
        open_words = ["hungry", "show", "listele"]
        has_folder = any(w in text for w in folder_words)
        has_open = any(w in text for w in open_words)
        if has_folder and has_open:
            return True
        # like "open downloads" — known alias + open
        from tools.file_tool import FOLDER_ALIAS_MAP
        for alias in FOLDER_ALIAS_MAP.keys():
            if alias in text and "hungry" in text:
                return True
        return False

    def _extract_file_ref(self, text: str) -> str:
        """Extract the file name or path from the text."""
        # Filename with extension
        m = re.search(r'[\w\-]+\.\w{2,4}', text)
        if m:
            return m.group(0)
        return ""

    def _extract_folder_name(self, text: str) -> str:
        """Extract folder name from text."""
        # Bilinen alias'lar
        from tools.file_tool import FOLDER_ALIAS_MAP
        for alias in FOLDER_ALIAS_MAP.keys():
            if alias in text:
                return alias
        # get before the word "folder"
        m = re.search(r'(.+?)\s+(?:folder|folder|directory|directory)\s*(?:open|show)?', text)
        if m:
            return m.group(1).strip()
        return text.replace("folder", "").replace("folder", "").replace("hungry", "").strip()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  LEARNING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def record_outcome(self, tool_tag: str, success: bool, latency_ms: float = 0.0):
        """Alias for validation tests."""
        self.record_execution(tool_tag, success, latency_ms)

    def record_execution(self, tool_tag: str, success: bool, latency_ms: float = 0.0,
                         context: str = ""):
        if tool_tag not in self.profiles:
            self.profiles[tool_tag] = ToolProfile(tag=tool_tag)

        p = self.profiles[tool_tag]
        p.total_calls += 1
        if success:
            p.successes += 1
        else:
            p.failures += 1

        if latency_ms > 0:
            if p.avg_latency_ms == 0:
                p.avg_latency_ms = latency_ms
            else:
                p.avg_latency_ms = p.avg_latency_ms * 0.8 + latency_ms * 0.2

        p.last_used = time.time()

        if context:
            old = p.context_scores.get(context, 0.5)
            p.context_scores[context] = old * 0.7 + (1.0 if success else 0.0) * 0.3

        self._save_profiles()

    def get_tool_stats(self) -> Dict[str, Any]:
        stats = {}
        for tag, p in self.profiles.items():
            stats[tag] = {
                "calls": p.total_calls,
                "success_rate": round(p.success_rate, 2),
                "reliability": round(p.reliability_score, 2),
                "avg_latency_ms": round(p.avg_latency_ms, 1)
            }
        return stats

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PERSISTENCE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _load_profiles(self):
        try:
            if os.path.exists(self.PROFILE_PATH):
                with open(self.PROFILE_PATH, 'r') as f:
                    data = json.load(f)
                    for tag, pdata in data.items():
                        self.profiles[tag] = ToolProfile(**pdata)
                logger.info(f"Loaded {len(self.profiles)} tool profiles.")
        except Exception as e:
            logger.warning(f"Failed to load tool profiles: {e}")

    def _save_profiles(self):
        try:
            os.makedirs(os.path.dirname(self.PROFILE_PATH), exist_ok=True)
            data = {}
            for tag, p in self.profiles.items():
                data[tag] = {"tag": p.tag, "total_calls": p.total_calls,
                             "successes": p.successes, "failures": p.failures,
                             "avg_latency_ms": p.avg_latency_ms, "last_used": p.last_used,
                             "context_scores": p.context_scores}
            with open(self.PROFILE_PATH, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save tool profiles: {e}")
