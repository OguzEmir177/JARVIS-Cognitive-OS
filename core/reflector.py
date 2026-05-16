"""
[V8.0] J.A.R.V.I.S. Rule-Based Reflector
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Görev sonrası değerlendirme motoru.

Sorumluluklar:
    - Ne yaptım? / Ne işe yaradı? / Ne başarısız oldu? /
      Sonraki seferde ne değişir? sorularını cevapla
    - Sonucu ChromaDB'ye episodic memory olarak kaydet
    - Gelecek planlamada context olarak sun

Tasarım Kararları:
    Neden kural-tabanlı (LLM değil)?
    → Groq free tier: 30 req/min, 6000 token/min.
      Her görevde reflection LLM çağrısı bütçeyi patlatır.
    → Basit başarı/hata → deterministik şablonlar yeterli.
    → Ambiguous durumlar nadirdir → opsiyonel LLM flag var.

    Neden 4 soru formatı?
    → "What did I do? What worked? What failed? What to change?"
      — standart reflective learning framework.
    → Şablon metin ChromaDB'ye düşünce → ileride semantic
      retrieval ile benzer görevlerde context olarak kullanılır.

Edge Cases:
    - TaskState.tool_history boşsa → "tool kullanılmadı" notu
    - Tüm tool'lar başarılıysa → kısa pozitif summary
    - Tüm tool'lar başarısızsa → detaylı hata analizi
    - Kısmi başarı → "ambiguous" flag → opsiyonel LLM reflection
"""

import logging
from typing import Any, Dict, List, Optional

from core.state_manager import TaskState
from core.memory import MemoryManager

logger = logging.getLogger("JARVIS.Reflector")


class Reflector:
    """
    Kural-tabanlı reflection engine.

    engine.py ile uyumlu API:
        reflector = Reflector(memory=memory, brain=brain)
        result = reflector.reflect(task_state)
        # result → {"summary": str, "task_type": str,
        #            "outcome": str, "tool_used": str}
        # veya None (reflection gerekmiyorsa)

    Attributes:
        memory:  MemoryManager reference (episodic write için)
        brain:   GroqBrain reference (opsiyonel LLM reflection için)
    """

    def __init__(
        self,
        memory: Optional[MemoryManager] = None,
        brain: Optional[Any] = None,  # GroqBrain, circular import'u önlemek için Any
    ) -> None:
        self.memory = memory
        self.brain = brain

    async def reflect(self, task_state: TaskState) -> Optional[Dict[str, str]]:
        """
        Görev sonrası kural-tabanlı reflection üretir.

        Args:
            task_state: Tamamlanmış veya başarısız TaskState

        Returns:
            Reflection dict:
                {
                    "summary":    str — 4 sorunun cevabını içeren özet metin
                    "task_type":  str — görev türü (web/desktop/system/mixed)
                    "outcome":    str — "success" | "failure" | "partial"
                    "tool_used":  str — kullanılan ana tool (virgülle ayrılmış)
                }
            None — reflection üretilecek bir şey yoksa
                   (ör: boş tool_history, görev henüz bitmemiş)

        Edge Cases:
            - is_terminal == False → None (görev bitmemiş, reflection yok)
            - tool_history boş → genel sohbet, reflection skip
            - Tüm tool'lar başarılı → kısa pozitif not
            - Tüm tool'lar başarısız → detaylı hata notu
            - Kısmi başarı → "partial" outcome
        """
        # Guard: Görev henüz terminal durumda değilse reflection üretme
        if not task_state.is_terminal:
            logger.debug(
                f"Reflection atlandı: task {task_state.id} "
                f"henüz terminal değil ({task_state.status})"
            )
            return None

        # Guard: Tool kullanılmadıysa (saf sohbet) reflection üretme
        history = task_state.tool_history
        if not history:
            logger.debug(
                f"Reflection atlandı: task {task_state.id} "
                f"tool_history boş (saf sohbet)"
            )
            return None

        # ── ANALİZ ──
        tools_used = [h.get("tool", "unknown") for h in history]
        successes = [h for h in history if h.get("success", False)]
        failures = [h for h in history if not h.get("success", True)]
        total_duration = sum(h.get("duration_ms", 0) for h in history)

        # ── OUTCOME BELİRLEME ──
        outcome = self._determine_outcome(
            total=len(history),
            success_count=len(successes),
            failure_count=len(failures),
        )

        # ── TASK TYPE ──
        task_type = self._infer_task_type(tools_used)

        # ── TOOL USED (virgülle ayrılmış) ──
        unique_tools = list(dict.fromkeys(tools_used))  # order-preserving unique
        tool_used_str = ", ".join(unique_tools)

        # ── 4 SORUNUN CEVABI ──
        summary = self._build_summary(
            goal=task_state.goal,
            outcome=outcome,
            tools_used=unique_tools,
            successes=successes,
            failures=failures,
            total_duration=total_duration,
            last_error=task_state.last_error,
        )

        logger.info(
            f"Reflection üretildi: task={task_state.id}, "
            f"outcome={outcome}, tools={tool_used_str}"
        )

        reflection_dict = {
            "summary": summary,
            "task_type": task_type,
            "outcome": outcome,
            "tool_used": tool_used_str,
        }

        # [V8.1] Importance Scoring & Pruning
        importance = 0.6 # Default
        if outcome == "failure":
            importance = 0.2
        elif "music" in task_type or "spotify" in tool_used_str.lower():
            importance = 0.4 # Rutin görevler
        
        # ── BUDAMA (Pruning) ──
        if importance < 0.3:
            logger.info(f"Reflection budandı (Importance={importance} < 0.3): task={task_state.id}")
            return reflection_dict

        # Epizodik hafızaya kayıt İPTAL EDİLDİ (Token limitini korumak ve çöp veriyi engellemek için)
        # Öğrenme işlemleri zaten AdaptiveLearner tarafından JSON'a kaydediliyor.
        return reflection_dict

    async def reflect_with_llm(
        self, task_state: TaskState, hint: str = ""
    ) -> Optional[Dict[str, str]]:
        """
        Ambiguous durumlar için LLM destekli reflection.

        Bu metod sadece engine tarafından açıkça çağrıldığında devreye girer.
        Normal akışta reflect() kural-tabanlı çalışır.

        Args:
            task_state: Görev durumu
            hint:       LLM'e ek bağlam (ör: "kısmi başarı sebebi belirsiz")

        Returns:
            Reflection dict veya None

        Edge Cases:
            - brain None ise → kural-tabanlı reflect()'e fallback
            - LLM timeout → kural-tabanlı reflect()'e fallback
            - LLM 429 → kural-tabanlı reflect()'e fallback
        """
        if self.brain is None:
            logger.warning(
                "LLM reflection istendi ama brain mevcut değil, "
                "kural-tabanlı fallback kullanılıyor."
            )
            return await self.reflect(task_state)

        # Kural-tabanlı base reflection'ı al
        base_reflection = await self.reflect(task_state)
        if base_reflection is None:
            return None

        # LLM'e sor: "Bu görev neden kısmen başarılı oldu?"
        try:
            prompt = (
                f"J.A.R.V.I.S. bir görev tamamladı.\n"
                f"Hedef: {task_state.goal}\n"
                f"Sonuç: {base_reflection['outcome']}\n"
                f"Kullanılan araçlar: {base_reflection['tool_used']}\n"
                f"Kural-tabanlı özet: {base_reflection['summary']}\n"
                f"Ek bağlam: {hint}\n\n"
                f"Bu görev hakkında kısa bir değerlendirme yaz. "
                f"Sonraki seferde ne farklı yapılmalı?"
            )

            # brain.think() artık async
            llm_response_obj = await self.brain.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=150,
                timeout=5.0,
            )
            llm_response = llm_response_obj.choices[0].message.content.strip()

            base_reflection["summary"] += f"\n[LLM INSIGHT]: {llm_response}"
            logger.info("LLM reflection başarıyla eklendi.")

        except Exception as e:
            logger.warning(f"LLM reflection başarısız (fallback): {e}")

        return base_reflection

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  INTERNAL — Reflection Building Blocks
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @staticmethod
    def _determine_outcome(
        total: int, success_count: int, failure_count: int
    ) -> str:
        """
        Başarı durumunu belirler.

        Returns:
            "success"  — tüm adımlar başarılı
            "failure"  — tüm adımlar başarısız
            "partial"  — karışık sonuç

        Edge Case:
            total == 0 → "success" (tool kullanılmadı = saf sohbet başarısı)
        """
        if total == 0:
            return "success"
        if failure_count == 0:
            return "success"
        if success_count == 0:
            return "failure"
        return "partial"

    @staticmethod
    def _infer_task_type(tools_used: List[str]) -> str:
        """
        Kullanılan tool'lardan görev türünü çıkarır.

        Mapping:
            GOOGLE_SEARCH, WEB_OPEN, YT_* → "web"
            APP_OPEN, APP_KILL, TAB_KILL   → "desktop"
            VISION, STRESS_TEST            → "system"
            Karışık                        → "mixed"
        """
        web_tools = {"GOOGLE_SEARCH", "WEB_OPEN", "YT_SEARCH", "YT_PLAY",
                     "WHATSAPP_MESSAGE", "WHATSAPP_DELETE"}
        desktop_tools = {"APP_OPEN", "APP_KILL", "TAB_KILL"}
        system_tools = {"VISION", "STRESS_TEST"}

        tool_set = set(tools_used)

        has_web = bool(tool_set & web_tools)
        has_desktop = bool(tool_set & desktop_tools)
        has_system = bool(tool_set & system_tools)

        categories = sum([has_web, has_desktop, has_system])

        if categories > 1:
            return "mixed"
        if has_web:
            return "web"
        if has_desktop:
            return "desktop"
        if has_system:
            return "system"
        return "unknown"

    @staticmethod
    def _build_summary(
        goal: str,
        outcome: str,
        tools_used: List[str],
        successes: List[Dict],
        failures: List[Dict],
        total_duration: int,
        last_error: Optional[str],
    ) -> str:
        """
        4 sorunun cevabını tek bir özet metne dönüştürür.

        Format:
            [NE YAPTIM] ...
            [NE İŞE YARADI] ...
            [NE BAŞARISIZ OLDU] ...
            [SONRAKİ SEFERDE] ...

        Edge Cases:
            - Hiç failure yoksa → "Başarısız olan yok"
            - Hiç success yoksa → "İşe yarayan yok"
            - last_error None → hata detayı atlanır
        """
        lines = []

        # 1. NE YAPTIM?
        tools_str = ", ".join(tools_used) if tools_used else "hiçbir araç"
        lines.append(
            f"[NE YAPTIM] Hedef: '{goal[:80]}'. "
            f"Kullanılan araçlar: {tools_str}. "
            f"Toplam süre: {total_duration}ms."
        )

        # 2. NE İŞE YARADI?
        if successes:
            success_tools = [s.get("tool", "?") for s in successes]
            lines.append(
                f"[NE İŞE YARADI] Başarılı araçlar: {', '.join(success_tools)}."
            )
        else:
            lines.append("[NE İŞE YARADI] İşe yarayan araç yok.")

        # 3. NE BAŞARISIZ OLDU?
        if failures:
            fail_tools = [f.get("tool", "?") for f in failures]
            error_detail = f" Son hata: {last_error}" if last_error else ""
            lines.append(
                f"[NE BAŞARISIZ OLDU] Başarısız araçlar: "
                f"{', '.join(fail_tools)}.{error_detail}"
            )
        else:
            lines.append("[NE BAŞARISIZ OLDU] Başarısız olan yok.")

        # 4. SONRAKİ SEFERDE NE DEĞİŞİR?
        if outcome == "success":
            lines.append(
                "[SONRAKİ SEFERDE] Aynı strateji "
                "tekrar kullanılabilir (başarılı kanıtlanmış)."
            )
        elif outcome == "failure":
            # Hangi fallback denenebilir?
            suggestion = (
                f"Alternatif araç veya farklı argüman denenebilir."
            )
            if last_error and "timeout" in last_error.lower():
                suggestion = "Timeout süresi artırılabilir veya daha hafif araç denenebilir."
            lines.append(f"[SONRAKİ SEFERDE] {suggestion}")
        else:  # partial
            lines.append(
                "[SONRAKİ SEFERDE] Başarısız adımlar için "
                "fallback zinciri gözden geçirilmeli."
            )

        return " ".join(lines)
