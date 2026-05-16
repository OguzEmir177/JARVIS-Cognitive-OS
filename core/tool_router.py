"""
[V15.0] J.A.R.V.I.S. Deterministic Semantic Tool Router
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Routing pipeline:
  STAGE 1: KEYWORD-FIRST deterministic matching (priority rules)
  STAGE 2: SEMANTIC embedding matching (fuzzy fallback)
  STAGE 3: AMBIGUITY gate → LLM fallback

V15.0 Değişiklikleri:
  - FILE_* intent'leri %99 doğruluk ile ayrılıyor
  - FOLDER_OPEN vs APP_OPEN kesin ayrım
  - FILE_WRITE context-aware: path|content formatı
  - FILE_DELETE tam implementasyon
  - Overengineering kaldırıldı, determinism öncelikli
"""
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
                         "haritada göster", "burası neresi", "koordinatları bul", "yol tarifi",
                         "harita", "İstanbul harita", "haritada İstanbul", "şehri haritada göster"],
            "CHART_SHOW": ["create data chart", "visualize statistics", "draw graph",
                           "grafik oluştur", "verileri görselleştir", "tablo yap", "istatistik"],
            "APP_OPEN": ["launch application", "open program", "start software",
                         "uygulamayı başlat", "programı aç", "çalıştır",
                         "spotify aç", "youtube aç", "chrome aç", "discord aç",
                         "steam aç", "tarayıcı aç", "uygulamayı aç"],
            "APP_KILL": ["close application", "terminate process", "stop program",
                         "uygulamayı kapat", "sonlandır", "durdur", "programı kapat"],
            "WEB_SEARCH": ["search internet", "find information online",
                           "internette ara", "bilgi bul", "araştır", "google",
                           "ne demek", "nedir", "kaç yaşında", "kimdir"],
            "YT_SEARCH": ["search youtube", "find video", "youtube'da ara", "video bul"],
            "YT_PLAY": ["play youtube video", "watch video", "youtube'da oynat", "video izle"],
            "WHATSAPP_MESSAGE": ["send whatsapp message", "mesaj gönder", "whatsapp yaz", "mesaj at"],
            "REMEMBER": ["remember this", "save to memory", "bunu hatırla", "kaydet"],
            "SYSTEM_POWER": ["shutdown computer", "restart", "bilgisayarı kapat", "yeniden başlat"],
            "WEB_OPEN": ["open website", "go to url", "siteyi aç", "adrese git", "web sitesini aç"],
            "FILE_LATEST": ["find latest downloaded file", "son indirilen dosya",
                            "en son ne indirdim", "son dosyayı bul", "indirdiğim son dosya"],
            "FILE_CREATE": ["create file", "dosya oluştur", "txt oluştur", "yeni dosya", "dosya yarat"],
            "FILE_WRITE": ["write to file", "dosyaya yaz", "dosya içeriği ekle", "içine yaz"],
            "FILE_READ": ["read file", "dosya oku", "dosya içeriği", "ne yazıyor"],
            "FILE_DELETE": ["delete file", "dosya sil", "dosyayı kaldır", "sil dosyayı"],
            "FOLDER_OPEN": ["open folder", "klasör aç", "dizini aç", "klasörü aç"],
            "YOUTUBE_STRATEGY": ["youtube stratejisi", "video fikri", "thumbnail promptu", "challenge fikri", "kanal planı", "youtube planla"],
            "ANALIZ_PRO": ["analiz pro'ya bağlan", "analiz uygulaması", "sunucu sağlık durumu", "analiz durumu", "analiz bağlantısı"],
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
    #  PRIORITY ORDER (yüksekten düşüğe):
    #    1. FILE operations (en spesifik)
    #    2. FOLDER operations
    #    3. SOHBET / chat (LLM'e bırak)
    #    4. APP operations
    #    5. Web/search operations
    #    6. System operations
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _keyword_route(self, user_input: str) -> Optional[RouteMatch]:
        # Nokta, ünlem ve soru işaretlerini temizle ki Regex anchor'ları ($) bozulmasın
        text = user_input.strip().lower().rstrip('.!?')

        # ── 1. FILE_DELETE: "X sil", "dosyayı sil", "test.txt'yi sil" ──
        # ÖNCE kontrol et — "dosya" + "sil" kombinasyonu kesin delete
        if self._is_file_delete(text):
            file_ref = self._extract_file_ref(text)
            return RouteMatch(
                tool_tag="FILE_DELETE",
                params={"file_path": file_ref},
                confidence=0.99, is_forced=True,
                reasoning=f"FILE_DELETE: sil keyword + dosya ref"
            )

        # ── 2. FILE_READ: "oku", "içeriği göster", "ne yazıyor" ──
        if self._is_file_read(text):
            file_ref = self._extract_file_ref(text)
            return RouteMatch(
                tool_tag="FILE_READ",
                params={"file_path": file_ref},
                confidence=0.99, is_forced=True,
                reasoning=f"FILE_READ: oku keyword"
            )

        # ── 3. FILE_WRITE: "X'e/içine Y yaz", "dosyaya ekle" ──
        if self._is_file_write(text):
            return RouteMatch(
                tool_tag="FILE_WRITE",
                params={"file_path_and_content": user_input},
                confidence=0.99, is_forced=True,
                reasoning="FILE_WRITE: yaz/ekle keyword"
            )

        # ── 4. FILE_CREATE: "oluştur", "yarat" + dosya bağlamı ──
        if self._is_file_create(text):
            return RouteMatch(
                tool_tag="FILE_CREATE",
                params={"file_path": user_input},
                confidence=0.99, is_forced=True,
                reasoning="FILE_CREATE: oluştur/yarat keyword"
            )

        # ── 5. FILE_LATEST: "son indirilen" ──
        if "son indiri" in text or ("son" in text and "dosya" in text and "indiri" in text):
            return RouteMatch(
                tool_tag="FILE_LATEST",
                params={"dir_path": "indirilenler"},
                confidence=0.98, is_forced=True,
                reasoning="FILE_LATEST: son indirilen keyword"
            )

        # ── 6. FOLDER_OPEN: klasör açma — APP_OPEN'dan ÖNCE kontrol et ──
        if self._is_folder_open(text):
            folder_name = self._extract_folder_name(text)
            return RouteMatch(
                tool_tag="FOLDER_OPEN",
                params={"folder_path": folder_name},
                confidence=0.99, is_forced=True,
                reasoning=f"FOLDER_OPEN: klasör keyword → {folder_name}"
            )

        # ── 7. SOHBET / BİLGİ / MATEMATİK → LLM ──
        chat_patterns = [
            r'\b(merhaba|selam|naber|nasılsın|teşekkür|sağol|mükemmel)\b',
            r'\b(sen kimsin|neler yapabilirsin|kendinden bahset)\b',
            r'\b(topla|çıkar|çarp|böl|hesapla|kaç eder|asal|matematik)\b',
        ]
        for pat in chat_patterns:
            if re.search(pat, text):
                return None

        # ── 8. APP_KILL: "X kapat" ──
        kill_patterns = [
            r'^(.+?)(?:\'?[yıiuü])\s+kapat$',
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
                # klasör kapatma değilse
                if "klasör" not in app_name and "dosya" not in app_name:
                    return RouteMatch(tool_tag="APP_KILL", params={"query": app_name},
                                      confidence=0.98, is_forced=True)

        # ── 9. APP_OPEN: "X aç", "X başlat", "X çalıştır" ──
        open_patterns = [
            r"^(.+?)(?:'?[yıiuü])\s+aç$",
            r"^(.+?)\s+aç$",
            r"^(.+?)(?:'?[yıiuü])\s+başlat$",
            r"^(.+?)\s+başlat$",
            r"^(.+?)(?:'?[yıiuü])\s+çalıştır$",
            r"^(.+?)\s+çalıştır$",
            r"^aç\s+(.+)$",
        ]
        for pat in open_patterns:
            m = re.match(pat, text)
            if m:
                app_name = m.group(1).strip()
                # Arama fiilleri kontrolü
                if any(text.endswith(w) for w in ['arat', ' ara', 'araştır']):
                    break
                # Klasör/dosya içeriyorsa → APP_OPEN değil
                if "klasör" in app_name or "dizin" in app_name:
                    break
                if app_name and len(app_name) >= 2:
                    return RouteMatch(
                        tool_tag="APP_OPEN",
                        params={"query": app_name},
                        confidence=0.98, is_forced=True,
                        reasoning=f"APP_OPEN: '{app_name} aç'"
                    )

        # ── 10. YT_SEARCH ──
        yt_search = re.match(r"youtube'?(?:da|ta|de|te)\s+(ara|arat|bul)\s*(.*)$", text)
        if yt_search:
            query = yt_search.group(2).strip() or user_input
            return RouteMatch(tool_tag="YT_SEARCH", params={"query": query},
                              confidence=0.95, is_forced=True, reasoning="YT_SEARCH")

        # ── 11. WEB_SEARCH ──
        search_patterns = [
            r'^(.+?)\s+araştır$',
            r'^(.+?)(?:\'?[yıiuü])\s+araştır$',
            r'^(.+?)\s+nedir$',
            r'^(.+?)\s+ne\s+demek$',
            r'^(.+?)\s+kimdir$',
            r'^(.+?)\s+kaç\s+yaşında$',
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
            r'(.+?)(?:\'?[yeaıiuü])[nea]?\s+mesaj\s+(?:at|gönder|yaz)',
            r'mesaj\s+(?:at|gönder|yaz)\s+(.+)',
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

        # ── 15. YOUTUBE_STRATEGY (KESİN YÖNLENDİRME) ──
        youtube_keywords = ["thumbnail", "video fikri", "challenge", "youtube planla", "kanal stratejisi"]
        # Eğer 'youtube' geçiyorsa ama yanında 'aç', 'uygulama', 'başlat' gibi app_open kelimeleri YOKSA stratejist ol.
        is_youtube_strategy = any(w in text for w in youtube_keywords) or ("youtube" in text and not any(kw in text for kw in ["aç", "uygulama", "başlat", "çalıştır"]))
        
        if is_youtube_strategy:
            return RouteMatch(tool_tag="YOUTUBE_STRATEGY", params={"request": user_input},
                              confidence=0.99, is_forced=True, reasoning="YOUTUBE_STRATEGY keyword")

        # ── 16. ANALIZ PRO (KESİN YÖNLENDİRME) ──
        analiz_keywords = ["analiz pro", "analiz uygulaması", "sunucu sağlık", "bağlantı testi", "kanal raporu", "son durum", "trendleri araştır", "rakip analizi"]
        # Eğer 'aç', 'başlat', 'çalıştır' varsa bu bir APP_OPEN isteğidir, ping atma!
        is_analiz_pro = any(w in text for w in analiz_keywords) and not any(kw in text for kw in ["aç", "başlat", "çalıştır"])
        
        if is_analiz_pro:
            return RouteMatch(tool_tag="ANALIZ_PRO", params={"query": user_input},
                              confidence=0.99, is_forced=True, reasoning="ANALIZ_PRO keyword")

        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  INTENT DETECTION HELPERS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _is_file_delete(self, text: str) -> bool:
        """
        FILE_DELETE: "dosya/txt sil", "test.txt'yi sil", "dosyayı sil"
        Hariç: "chrome sil" (uygulama kaldır), "discord sil" vb.
        """
        has_sil = "sil" in text
        if not has_sil:
            return False
        # "dosya" veya ".txt"/".py"/".json" gibi uzantı içeriyorsa dosya silme
        has_file_indicator = (
            "dosya" in text or
            "txt" in text or
            re.search(r'\.\w{2,4}', text) is not None or
            "dosyayı" in text or
            "dosyasını" in text
        )
        return has_file_indicator

    def _is_file_read(self, text: str) -> bool:
        """
        FILE_READ: "dosya oku", "test.txt oku", "dosyayı oku", "içeriğini göster"
        """
        read_keywords = ["oku", "içeriğini göster", "ne yazıyor", "içeriği ne"]
        has_read = any(kw in text for kw in read_keywords)
        if not has_read:
            return False
        # "dosya" ya da uzantı ya da context kelimesi
        context_keywords = ["dosya", "txt", "içerik"]
        has_file = (
            any(kw in text for kw in context_keywords) or
            re.search(r'\.\w{2,4}', text) is not None
        )
        return has_file

    def _is_file_write(self, text: str) -> bool:
        """
        FILE_WRITE: "X içine Y yaz", "dosyaya ekle", "içine yaz"
        Hariç: Sadece "yaz" tek başına (konuşma komutu olabilir)
        """
        write_keywords = ["içine yaz", "dosyaya yaz", "dosyaya ekle", "içerik ekle", "yaz içine"]
        if any(kw in text for kw in write_keywords):
            return True
        # "X yaz" kalıbı — context dosya içeriyorsa
        if "yaz" in text and (
            "dosya" in text or
            re.search(r'\.\w{2,4}', text) is not None or
            "içine" in text
        ):
            return True
        return False

    def _is_file_create(self, text: str) -> bool:
        """
        FILE_CREATE: "dosya oluştur", "test.txt oluştur", "masaüstünde X oluştur"
        Hariç: "plan oluştur" (belge değil), "liste yarat" vb.
        """
        create_keywords = ["oluştur", "yarat"]
        has_create = any(kw in text for kw in create_keywords)
        if not has_create:
            return False
        # Dosya bağlamı
        file_keywords = ["txt", "dosya", "metin", "belge", ".py", ".json", ".md", ".log"]
        has_file = (
            any(kw in text for kw in file_keywords) or
            re.search(r'\.\w{2,4}', text) is not None
        )
        return has_file

    def _is_folder_open(self, text: str) -> bool:
        """
        FOLDER_OPEN: "klasör aç", "indirilenler klasörü", "belgeler dizini"
        """
        folder_words = ["klasör", "dizin"]
        open_words = ["aç", "göster", "listele"]
        has_folder = any(w in text for w in folder_words)
        has_open = any(w in text for w in open_words)
        if has_folder and has_open:
            return True
        # "indirilenler aç" gibi — bilinen alias + aç
        from tools.file_tool import FOLDER_ALIAS_MAP
        for alias in FOLDER_ALIAS_MAP.keys():
            if alias in text and "aç" in text:
                return True
        return False

    def _extract_file_ref(self, text: str) -> str:
        """Metinden dosya adını veya path'ini çıkar."""
        # Uzantılı dosya adı
        m = re.search(r'[\w\-]+\.\w{2,4}', text)
        if m:
            return m.group(0)
        return ""

    def _extract_folder_name(self, text: str) -> str:
        """Metinden klasör adını çıkar."""
        # Bilinen alias'lar
        from tools.file_tool import FOLDER_ALIAS_MAP
        for alias in FOLDER_ALIAS_MAP.keys():
            if alias in text:
                return alias
        # "klasör" kelimesinin öncesini al
        m = re.search(r'(.+?)\s+(?:klasörünü|klasörü|dizinini|dizini)\s*(?:aç|göster)?', text)
        if m:
            return m.group(1).strip()
        return text.replace("klasörünü", "").replace("klasörü", "").replace("aç", "").strip()

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
