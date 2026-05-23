"""
[V14.0] J.A.R.V.I.S. Adaptive Learning System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Otonom öğrenme motoru. J.A.R.V.I.S.'in bilinmeyen komutları
kendi kendine öğrenmesini ve hatalarından ders çıkarmasını sağlar.

Capabilities:
    1. Strategy Recording — Başarılı görevlerin stratejisini kaydeder
    2. Unknown Command Learning — Bilinmeyen komutları LLM ile çözer ve öğrenir
    3. Failure Adaptation — Başarısızlık sonrası alternatif yol bulur
    4. Repeat Detection — Kullanıcının tekrar ettiği komutları tespit eder
    5. Dynamic Skill Synthesis — Öğrenilen stratejileri kalıcı beceriye dönüştürür

Architecture:
    AdaptiveLearner
    ├── StrategyStore (JSON-based persistent strategy memory)
    ├── RepeatDetector (short-term command dedup)
    ├── SkillSynthesizer (learned strategies → reusable skills)
    └── LLM Fallback (asks brain for unknown commands)
"""

import asyncio
import json
import os
import time
import logging
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("JARVIS.AdaptiveLearner")

STRATEGY_DB_PATH = "memory_db/learned_strategies.json"


@dataclass
class LearnedStrategy:
    """Öğrenilmiş bir görev stratejisi."""
    command_pattern: str      # Kullanıcının orijinal komutu (normalize)
    tool_chain: List[str]     # Kullanılan araç zinciri [APP_OPEN, WEB_SEARCH, ...]
    arguments: List[str]      # Her araç için argüman
    success_count: int = 0    # Kaç kez başarılı oldu
    failure_count: int = 0    # Kaç kez başarısız oldu
    last_used: float = 0.0    # Son kullanım zamanı
    created_at: float = 0.0   # Oluşturulma zamanı

    @property
    def confidence(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total

    @property
    def is_reliable(self) -> bool:
        """Strateji güvenilir mi? (en az 2 başarı, %70+ başarı oranı)"""
        return self.success_count >= 2 and self.confidence >= 0.7


class AdaptiveLearner:
    """
    [V14.0] J.A.R.V.I.S. Otonom Öğrenme Motoru
    
    Kullanım:
        learner = AdaptiveLearner()
        
        # Başarılı strateji kaydet
        learner.record_success("youtube aç", ["APP_OPEN"], ["youtube"])
        
        # Sonraki sefer aynı komut geldiğinde
        strategy = learner.find_strategy("youtube'u aç")
        if strategy:
            # Doğrudan stratejiyi uygula
            ...
        
        # Bilinmeyen komut için LLM'den öğren
        plan = await learner.learn_unknown_command(brain, "ekranı kaydet", available_tools)
    """

    def __init__(self):
        self.strategies: Dict[str, LearnedStrategy] = {}
        self._recent_commands: List[Dict[str, Any]] = []  # Son 10 komut (repeat detection)
        self._max_recent = 10
        self._load_strategies()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  STRATEGY RECORDING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def record_success(self, user_input: str, tools_used: List[str], 
                       arguments: List[str]) -> None:
        """
        Başarılı bir görevin stratejisini kaydeder.
        Aynı komut tekrar geldiğinde bu strateji öncelikle uygulanır.
        """
        key = self._normalize_command(user_input)
        
        if key in self.strategies:
            strategy = self.strategies[key]
            strategy.success_count += 1
            strategy.last_used = time.time()
            # Eğer farklı bir tool chain kullanıldıysa ve bu da başarılıysa, güncelle
            if tools_used != strategy.tool_chain:
                # Yeni chain daha kısaysa tercih et
                if len(tools_used) <= len(strategy.tool_chain):
                    strategy.tool_chain = tools_used
                    strategy.arguments = arguments
        else:
            self.strategies[key] = LearnedStrategy(
                command_pattern=key,
                tool_chain=tools_used,
                arguments=arguments,
                success_count=1,
                last_used=time.time(),
                created_at=time.time(),
            )
        
        self._prune_strategies()
        self._schedule_save()
        logger.info(f"[ÖĞRENME] Strateji kaydedildi: '{key}' → {tools_used}")

    def record_failure(self, user_input: str, tools_used: List[str]) -> None:
        """Başarısız stratejiyi kaydeder (gelecekte aynı yolu tekrarlamamak için)."""
        key = self._normalize_command(user_input)
        
        if key in self.strategies:
            self.strategies[key].failure_count += 1
            self.strategies[key].last_used = time.time()
            self._prune_strategies()
            self._schedule_save()
            logger.info(f"[ÖĞRENME] Başarısız strateji kaydedildi: '{key}' (failures={self.strategies[key].failure_count})")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  STRATEGY LOOKUP
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def find_strategy(self, user_input: str) -> Optional[LearnedStrategy]:
        """
        Kullanıcı komutuyla eşleşen öğrenilmiş strateji arar.
        
        Eşleştirme: 
          1. Exact match (normalize edilmiş)
          2. Fuzzy match (kelime kesişimi %60+)
        
        Returns: LearnedStrategy veya None
        """
        key = self._normalize_command(user_input)
        
        # 1. Exact match
        if key in self.strategies:
            strategy = self.strategies[key]
            if strategy.is_reliable:
                logger.info(f"[ÖĞRENME] Exact match bulundu: '{key}' → {strategy.tool_chain} (güven={strategy.confidence:.0%})")
                return strategy
        
        # 2. Fuzzy match — kelime kesişimi
        input_words = set(key.split())
        if len(input_words) < 2:
            return None
            
        best_match = None
        best_overlap = 0.0
        
        for pattern, strategy in self.strategies.items():
            if not strategy.is_reliable:
                continue
            pattern_words = set(pattern.split())
            if not pattern_words:
                continue
            overlap = len(input_words & pattern_words) / max(len(input_words), len(pattern_words))
            if overlap > 0.6 and overlap > best_overlap:
                best_match = strategy
                best_overlap = overlap
        
        if best_match:
            logger.info(f"[ÖĞRENME] Fuzzy match bulundu: '{key}' ≈ '{best_match.command_pattern}' (overlap={best_overlap:.0%})")
            return best_match
        
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  UNKNOWN COMMAND LEARNING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def learn_unknown_command(self, brain, user_input: str, 
                                     available_tools: List[str]) -> Optional[Dict[str, Any]]:
        """
        Bilinmeyen bir komutu LLM'e sorarak öğrenir.
        
        Iron Dome bilinmeyen protokol engellediğinde çağrılır.
        LLM'e "mevcut araçlarla bu komutu nasıl yapabilirim?" diye sorar.
        
        Returns:
            {"tool": "APP_OPEN", "argument": "notepad"} veya None
        """
        tools_list = ", ".join(available_tools)
        
        prompt = (
            f"[SİSTEM TALİMATI — ARAÇ SEÇİMİ]\n"
            f"Kullanıcı şunu istedi: \"{user_input}\"\n"
            f"Mevcut araçların: {tools_list}\n\n"
            f"Bu isteği yerine getirmek için hangi aracı hangi argümanla kullanmalısın?\n"
            f"SADECE şu JSON formatında cevap ver, başka bir şey yazma:\n"
            f'{{\"tool\": \"TOOL_TAG\", \"argument\": \"argüman\"}}\n'
            f"Eğer hiçbir araçla yapılamıyorsa: {{\"tool\": \"SPEAK\", \"argument\": \"Bu işlemi yapma yeteneğim henüz yok.\"}}"
        )
        
        try:
            response = await brain.think(prompt, bypass_history=True)
            
            # JSON çıkar
            json_match = re.search(r'\{.*?\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                tool = data.get("tool", "").upper()
                argument = data.get("argument", "")
                
                if tool and tool in available_tools:
                    logger.info(f"[ÖĞRENME] Bilinmeyen komut çözüldü: '{user_input}' → {tool} {argument}")
                    
                    # Öğrenilen stratejiyi kaydet
                    self.record_success(user_input, [tool], [argument])
                    
                    return {"tool": tool, "argument": argument}
                elif tool == "SPEAK":
                    return {"tool": "SPEAK", "argument": argument}
                    
        except Exception as e:
            logger.warning(f"[ÖĞRENME] Bilinmeyen komut çözülemedi: {e}")
        
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  REPEAT DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def detect_repeat(self, user_input: str) -> Optional[str]:
        """
        Kullanıcının kısa süre içinde aynı komutu tekrar edip etmediğini kontrol eder.
        
        Logda görüldüğü gibi: kullanıcı "naber.txt oluştur" yazıyor, yanıt yok,
        15 saniye sonra tekrar yazıyor. Bu, önceki denemenin başarısız olduğu anlamına gelir.
        
        Returns:
            Önceki komutun task_id'si (tekrar varsa) veya None
        """
        key = self._normalize_command(user_input)
        now = time.time()
        
        # Son 30 saniye içinde aynı komut var mı?
        for cmd in reversed(self._recent_commands):
            if now - cmd["time"] > 30:
                break
            if cmd["key"] == key:
                logger.info(f"[ÖĞRENME] TEKRAR TESPİT EDİLDİ: '{key}' ({now - cmd['time']:.0f}s önce de girildi)")
                return cmd.get("task_id")
        
        # Yeni komutu kaydet
        self._recent_commands.append({"key": key, "time": now, "input": user_input})
        if len(self._recent_commands) > self._max_recent:
            self._recent_commands = self._recent_commands[-self._max_recent:]
        
        return None

    def update_recent_task_id(self, user_input: str, task_id: str) -> None:
        """Son komutun task_id'sini günceller (repeat detection için)."""
        key = self._normalize_command(user_input)
        for cmd in reversed(self._recent_commands):
            if cmd["key"] == key:
                cmd["task_id"] = task_id
                break

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SKILL PROMPT GENERATION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_learned_rules_prompt(self, limit: int = 10) -> str:
        """
        Öğrenilmiş stratejileri LLM prompt'una enjekte edilebilecek
        format da döndürür. Brain'in system_injection'ına eklenir.
        """
        reliable = [s for s in self.strategies.values() if s.is_reliable]
        if not reliable:
            return ""
        
        # En çok kullanılan ve en güvenilir stratejileri seç
        reliable.sort(key=lambda s: (-s.success_count, -s.confidence))
        top = reliable[:limit]
        
        lines = ["[ÖĞRENİLMİŞ STRATEJİLER]"]
        for s in top:
            tools_str = " → ".join(s.tool_chain)
            lines.append(f"  • '{s.command_pattern}' → {tools_str} (başarı: {s.success_count}x)")
        
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Öğrenme sistemi istatistikleri."""
        total = len(self.strategies)
        reliable = sum(1 for s in self.strategies.values() if s.is_reliable)
        total_successes = sum(s.success_count for s in self.strategies.values())
        total_failures = sum(s.failure_count for s in self.strategies.values())
        
        return {
            "total_strategies": total,
            "reliable_strategies": reliable,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "recent_commands": len(self._recent_commands),
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  INTERNAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _normalize_command(text: str) -> str:
        """
        Komutu normalize eder — küçük harf, gereksiz boşluk temizle,
        Türkçe suffix'leri basitleştir.
        """
        text = text.strip().lower()
        # Çoklu boşlukları tekle
        text = re.sub(r'\s+', ' ', text)
        # Yaygın Türkçe suffix'leri kaldır (basit stemming)
        text = re.sub(r"'?[yıiuü]$", "", text)  # "chrome'u" → "chrome"
        text = re.sub(r"'?[yıiuü]n[ıiuü]$", "", text)  # "chrome'unu" → "chrome"
        return text.strip()

    def _prune_strategies(self, max_strategies: int = 200) -> None:
        """Memory Leak'i önlemek için en az kullanılan/güvenilmeyen stratejileri budar."""
        if len(self.strategies) > max_strategies:
            # Güvenilirlik ve son kullanım zamanına göre sırala
            sorted_strats = sorted(
                self.strategies.values(), 
                key=lambda s: (s.is_reliable, s.last_used), 
                reverse=True
            )
            self.strategies = {s.command_pattern: s for s in sorted_strats[:max_strategies]}

    def _load_strategies(self) -> None:
        """Strateji veritabanını dosyadan yükler (Fail-Fast)."""
        try:
            if os.path.exists(STRATEGY_DB_PATH):
                with open(STRATEGY_DB_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, sdata in data.items():
                        self.strategies[key] = LearnedStrategy(**sdata)
                logger.info(f"[ÖĞRENME] {len(self.strategies)} strateji yüklendi.")
        except json.JSONDecodeError as e:
            logger.error(f"[ÖĞRENME] Strateji DB bozuk (JSON hatası): {e} — Temiz başlıyor.")
        except Exception as e:
            logger.error(f"[ÖĞRENME] Strateji yükleme kritik hatası: {e}")

    def _save_strategies(self) -> None:
        """Strateji veritabanını dosyaya kaydeder (senkron — run_in_executor ile çağırılmalı)."""
        try:
            os.makedirs(os.path.dirname(STRATEGY_DB_PATH), exist_ok=True)
            data = {}
            for key, strategy in self.strategies.items():
                data[key] = asdict(strategy)
            with open(STRATEGY_DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # debug→error: Disk yazma hatalarını asla sessizce yutma (Fail-Fast prensibi)
            logger.error(f"[ÖĞRENME] Strateji kaydetme HATASI: {e}")

    def _schedule_save(self) -> None:
        """
        [V14.1] Async-Safe Disk Yazma Zamanlayıcısı.
        Event loop varsa I/O'yu ThreadPool'a atar (event-loop bloklamasını önler).
        Loop yoksa (test/startup) direkt senkron çalışır.
        """
        try:
            loop = asyncio.get_running_loop()
            # Async bağlamda: I/O'yu thread pool'a at
            loop.run_in_executor(None, self._save_strategies)
        except RuntimeError:
            # Event loop yok (ör: test ortamı, __init__) — senkron yaz
            self._save_strategies()
