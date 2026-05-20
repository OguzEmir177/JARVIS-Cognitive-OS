import asyncio
import logging
import uuid
from datetime import datetime

logger = logging.getLogger("JARVIS.Watcher")


class ProactiveWatcher:
    """
    [10/10 v2] J.A.R.V.I.S. Otonom Bekçi Modülü — Adaptive Vision + Davranış Kalibrasyonu

    Yenilikler (v2):
    ─────────────────────────────────────────────────────────────────
    [4] VISION "SÜREKLİ ANALİZ" — Dinamik Aralık Sistemi:
        + Sabit 5 dk yerine ihtiyaca göre otomatik hızlanan/yavaşlayan döngü
        + Ekranda değişim algılandığında aralık kısalır (hızlı gözlem)
        + Ekran stabil kaldığında aralık uzar (kaynak tasarrufu)
        + Min/max aralık sınırları güvenlik için korunur

    [5] PROAKTİF DAVRANIŞ KALİBRASYONU:
        + Konuşma/susma eşiği hassas ayarlandı
        + Saat dilimine göre proaktiflik seviyesi değişir
        + Ardışık sessizlik sayacı: çok uzun susarsa bile gözlem paylaşır
        + Gereksiz gevezelik önleyici sıkı kurallar

    Mevcut (korunan):
    + Vision sonucu GUI'ye kart olarak gönderiliyor
    + Proaktif eylem gerçekleştiğinde Mission Control'e özet kart ekleniyor
    + Vision status callback üzerinden HUD görsel durumu güncelleniyor
    """

    # ── Dinamik Aralık Sabitleri ──────────────────────────────────────────
    MIN_INTERVAL_SECONDS = 300       # Minimum gözlem aralığı: 5 dakika (Limit koruma)
    MAX_INTERVAL_SECONDS = 1800      # Maksimum gözlem aralığı: 30 dakika
    DEFAULT_INTERVAL_SECONDS = 900   # Varsayılan başlangıç: 15 dakika

    # Hızlanma/yavaşlama çarpanları
    SPEEDUP_FACTOR = 0.6    # Değişim algılandığında aralığı %60'a düşür
    SLOWDOWN_FACTOR = 1.3   # Stabil durumdaysa aralığı %130'a çıkar

    # Benzerlik eşiği — bu oranın altında fark varsa "değişim yok" sayılır
    SIMILARITY_THRESHOLD = 0.85

    # [V13.1] Stabil ekranda API çağrısı atlama eşiği
    # Bu kadar ardışık stabil döngü sonrası brain.think() ÇAĞRILMAZ
    STABLE_SKIP_THRESHOLD = 3

    # ── Davranış Kalibrasyonu Sabitleri ───────────────────────────────────
    MAX_CONSECUTIVE_SILENCE = 6     # 6 döngü ardışık susarsa, gözlem özeti paylaş
    
    # Saat dilimi bazlı proaktiflik seviyeleri
    PROACTIVITY_LEVELS = {
        "quiet":    {"hours": range(0, 8),   "speak_threshold": "critical_only"},
        "morning":  {"hours": range(8, 12),  "speak_threshold": "helpful"},
        "active":   {"hours": range(12, 18), "speak_threshold": "normal"},
        "evening":  {"hours": range(18, 22), "speak_threshold": "moderate"},
        "late":     {"hours": range(22, 24), "speak_threshold": "low"},
    }

    def __init__(self, engine, interval_minutes: int = 5):
        self.engine = engine
        self._running = False

        # Dinamik aralık durumu
        self._current_interval = self.DEFAULT_INTERVAL_SECONDS
        self._last_screen_summary: str = ""
        self._consecutive_stable = 0       # Ardışık stabil döngü sayacı
        self._consecutive_silence = 0      # Ardışık sessiz kalma sayacı
        self._total_observations = 0       # Toplam gözlem sayısı
        self._total_actions = 0            # Toplam proaktif eylem sayısı

        from core.vision import JarvisVision
        self.vision = JarvisVision()

    async def run(self):
        self._running = True
        logger.info(
            f"[WATCHER] Otonom Bekçi başlatıldı. "
            f"(Dinamik aralık: {self.MIN_INTERVAL_SECONDS}s – {self.MAX_INTERVAL_SECONDS}s)"
        )

        while self._running:
            try:
                # Dinamik aralık kullan
                await asyncio.sleep(self._current_interval)
                if not self._running:
                    break

                logger.info(
                    f"[WATCHER] Proaktif düşünce döngüsü tetiklendi. "
                    f"(Aralık: {self._current_interval:.0f}s | "
                    f"Gözlem #{self._total_observations + 1})"
                )
                await self._trigger_proactive_thought()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WATCHER] Döngü Hatası: {e}")
                await asyncio.sleep(60)

    async def _trigger_proactive_thought(self):
        now = datetime.now()
        self._total_observations += 1

        # 1. Gece modu — tamamen susma
        if now.hour < 8 or now.hour >= 23:
            logger.info("[WATCHER] Gece modu. Proaktif eylem askıya alındı.")
            # Gece modunda aralığı maksimuma çek
            self._current_interval = self.MAX_INTERVAL_SECONDS
            return

        # 2. Son hafızayı al
        recent_memory = "HAFIZA BOŞ"
        if self.engine.memory:
            recent_memory = str(self.engine.memory.get_recent_memories(3))
            if len(recent_memory) > 2000:
                recent_memory = "... " + recent_memory[-2000:]

        # 3. Ekran Analizi (Lokal ve Ücretsiz Pencere Takibi)
        logger.info("[WATCHER] Gözlem yapılıyor (Lokal Pencere Analizi)...")
        # API kotasını bitirmemek için ekran görüntüsü almak yerine aktif pencereyi okuyoruz
        situation = {"active_app": "Unknown", "active_window": "Unknown"}
        if hasattr(self.engine, 'cognitive_core') and self.engine.cognitive_core:
            situation = self.engine.cognitive_core.world_state.get_situation_assessment()
            
        active_app = situation.get("active_app", "Bilinmiyor")
        active_win = situation.get("active_window", "Bilinmiyor")
        
        if active_app != "Unknown" and active_win != "Unknown":
            screen_summary = f"Kullanıcı şu an '{active_app}' uygulamasında '{active_win}' penceresi üzerinde çalışıyor."
        else:
            screen_summary = "Ekranda belirgin bir uygulama yok veya masaüstünde."

        # ── [İYİLEŞTİRME] DİNAMİK ARALIK HESAPLAMASI ─────────────────────────
        screen_changed = self._detect_screen_change(screen_summary)
        self._adjust_interval(screen_changed)

        # Ekran analizi sonucunu GUI Vision Status göstergesine ilet
        if hasattr(self.engine, 'io_bridge') and self.engine.io_bridge:
            try:
                interval_info = f" [Aralık: {self._current_interval:.0f}s]"
                self.engine.io_bridge.update_vision_status(
                    summary=(screen_summary + interval_info) if screen_summary else "Ekranda anlamlı içerik bulunamadı.",
                    screenshot_path=None
                )
            except Exception as e:
                logger.warning(f"[WATCHER] Vision status gönderilemedi: {e}")

        # ── [V13.1] STABİL EKRAN KORUMASI — API Limit Kalkanı ─────────
        # Ekran uzun süredir değişmediyse (oyun, film, AFK vb.)
        # brain.think() çağrısı YAPMA — API kotasını koru
        if self._consecutive_stable >= self.STABLE_SKIP_THRESHOLD:
            logger.info(
                f"[WATCHER] Ekran {self._consecutive_stable} döngüdür stabil — "
                f"API çağrısı atlandı (limit koruma). Aralık: {self._current_interval:.0f}s"
            )
            # Sadece lokal gözlem kartı gönder, API çağrısı yapma
            if screen_summary and len(screen_summary) > 30:
                self._send_vision_card(now, screen_summary + " [API Atlandı — Stabil]", silent=True)
            return

        # ── [5] DAVRANIŞ KALİBRASYONU — Proaktiflik Seviyesi ────────────
        proactivity = self._get_proactivity_level(now)

        # 4. Otonom Prompt — Kalibre edilmiş
        watcher_prompt = self._build_calibrated_prompt(
            now, screen_summary, recent_memory, proactivity
        )

        try:
            response = await self.engine.brain.think(watcher_prompt, bypass_history=True)

            silence_variants = ["[SILENCE]", "[SİLENCE]", "SİLENCE", "SILENCE"]
            if any(v in response.upper() for v in silence_variants):
                self._consecutive_silence += 1
                logger.info(
                    f"[WATCHER] Bekçi sessiz kalmayı tercih etti. "
                    f"(Ardışık sessizlik: {self._consecutive_silence}/{self.MAX_CONSECUTIVE_SILENCE})"
                )

                # [5] Kalibrasyon: Çok uzun sessiz kalırsa gözlem özeti paylaş
                if self._consecutive_silence >= self.MAX_CONSECUTIVE_SILENCE:
                    if screen_summary and len(screen_summary) > 30:
                        self._send_vision_card(now, screen_summary, silent=True)
                        self._consecutive_silence = 0  # Sayacı sıfırla
                elif screen_summary and screen_summary.strip() and len(screen_summary) > 30:
                    # Normal döngüde de kart gönder (sadece içerik varsa)
                    self._send_vision_card(now, screen_summary, silent=True)
                return

            response = self.engine._sanitize_llm_output(response)
            if not response.strip():
                return

            # Proaktif eylem başarılı
            self._consecutive_silence = 0
            self._total_actions += 1
            logger.info(
                f"[WATCHER] Bekçi proaktif eylem başlattı! "
                f"(Toplam eylem: {self._total_actions})"
            )

            # Proaktif eylem özetini Mission Control'e kart olarak ekle
            self._send_watcher_action_card(now, screen_summary, response)

            task_id = str(uuid.uuid4())[:8]
            task_state = self.engine.state_manager.create_task(task_id=task_id, goal="[OTONOM EYLEM]")

            plan = await self.engine.plan_executor.detect_and_parse_plan(response, watcher_prompt)
            if plan:
                await self.engine.plan_executor.execute_plan(task_state, plan)
            else:
                protocol_start = response.find("[PROTOCOL:")
                if protocol_start >= 0:
                    await self.engine.plan_executor.execute_single(task_state, response[protocol_start:])
                else:
                    await self.engine.io_bridge.speak(response)

            self.engine.state_manager.complete_task(task_id)

            # Proaktif eylem sonrası gözlem aralığını kısalt (aktif durum)
            self._current_interval = max(
                self.MIN_INTERVAL_SECONDS,
                self._current_interval * self.SPEEDUP_FACTOR
            )

        except Exception as e:
            logger.error(f"[WATCHER] Proaktif düşünce sırasında hata: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # [4] DİNAMİK ARALIK YÖNETİMİ
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_screen_change(self, current_summary: str) -> bool:
        """
        Önceki ve şimdiki ekran özetini karşılaştırarak değişim olup olmadığını belirler.
        Basit kelime bazlı Jaccard benzerliği kullanır — hızlı ve yeterince doğru.
        """
        if not self._last_screen_summary or not current_summary:
            self._last_screen_summary = current_summary or ""
            return True  # İlk gözlem, varsayılan olarak "değişim" say

        prev_words = set(self._last_screen_summary.lower().split())
        curr_words = set(current_summary.lower().split())

        if not prev_words or not curr_words:
            self._last_screen_summary = current_summary
            return True

        intersection = prev_words & curr_words
        union = prev_words | curr_words
        similarity = len(intersection) / len(union) if union else 1.0

        self._last_screen_summary = current_summary

        changed = similarity < self.SIMILARITY_THRESHOLD
        if changed:
            self._consecutive_stable = 0
            logger.info(
                f"[WATCHER] Ekran değişimi algılandı! "
                f"(Benzerlik: {similarity:.2f} < {self.SIMILARITY_THRESHOLD})"
            )
        else:
            self._consecutive_stable += 1
            logger.debug(
                f"[WATCHER] Ekran stabil. "
                f"(Benzerlik: {similarity:.2f}, Ardışık stabil: {self._consecutive_stable})"
            )

        return changed

    def _adjust_interval(self, screen_changed: bool) -> None:
        """
        Ekran durumuna göre gözlem aralığını ayarlar.

        Değişim varsa → hızlan (aralığı kısalt)
        Stabil ise   → yavaşla (aralığı uzat)
        """
        if screen_changed:
            new_interval = self._current_interval * self.SPEEDUP_FACTOR
        else:
            new_interval = self._current_interval * self.SLOWDOWN_FACTOR

        # Sınırları uygula
        new_interval = max(self.MIN_INTERVAL_SECONDS, min(self.MAX_INTERVAL_SECONDS, new_interval))

        if new_interval != self._current_interval:
            logger.info(
                f"[WATCHER] Aralık güncellendi: {self._current_interval:.0f}s → {new_interval:.0f}s "
                f"({'⚡ Hızlandı' if screen_changed else '🐢 Yavaşladı'})"
            )
        self._current_interval = new_interval

    # ─────────────────────────────────────────────────────────────────────────
    # [5] PROAKTİF DAVRANIŞ KALİBRASYONU
    # ─────────────────────────────────────────────────────────────────────────

    def _get_proactivity_level(self, now: datetime) -> dict:
        """
        Saat dilimine göre proaktiflik seviyesini belirler.
        Her seviyenin farklı konuşma eşiği vardır.
        """
        for level_name, level_data in self.PROACTIVITY_LEVELS.items():
            if now.hour in level_data["hours"]:
                return {"name": level_name, **level_data}
        return {"name": "normal", "speak_threshold": "normal", "hours": range(0, 24)}

    def _build_calibrated_prompt(self, now: datetime, screen_summary: str,
                                  recent_memory: str, proactivity: dict) -> str:
        """
        [5] Davranış kalibrasyonu uygulanmış otonom prompt oluşturur.

        Kalibrasyon Kuralları:
        ──────────────────────────────────────────────────────────
        critical_only : SADECE sistem hatası, çökme veya acil durum varsa konuş
        low           : Sadece gerçekten önemli hatırlatma veya ciddi hata varsa konuş
        moderate      : Önemli bilgi veya faydalı gözlem varsa konuş
        helpful       : Yardımcı olabilecek fikirler için nazikçe konuşabilir
        normal        : Standart proaktiflik — hata, hatırlatma, öneri
        """
        level_name = proactivity.get("name", "normal")
        threshold = proactivity.get("speak_threshold", "normal")

        # Kalibrasyon talimatları — her seviye için farklı ton ve eşik
        calibration_rules = {
            "critical_only": (
                "⚠️ KRİTİK MOD: Sadece ve SADECE şu durumlarda konuş:\n"
                "  - Ekranda bir HATA/ÇÖKME/MAVİ EKRAN varsa\n"
                "  - Acil bir hatırlatma (alarm) tetiklenmişse\n"
                "Bunların dışında MUTLAKA [SILENCE] yaz. Gece saatlerinde kullanıcıyı asla rahatsız etme."
            ),
            "low": (
                "🔇 DÜŞÜK PROAKTİFLİK: Konuşma eşiğin çok yüksek.\n"
                "  Sadece şu durumlarda konuş:\n"
                "  - Kritik bir hata veya güvenlik uyarısı varsa\n"
                "  - Zamanı gelen acil bir hatırlatma varsa\n"
                "  Geç saatte kullanıcı muhtemelen dinleniyor. Gereksiz bilgilendirme YAPMA."
            ),
            "moderate": (
                "🔉 ORTA PROAKTİFLİK: Denge modunda çalış.\n"
                "  Konuş eğer:\n"
                "  - Kullanıcının işine yarayacak net ve somut bir gözlemin varsa\n"
                "  - Bir hata algıladıysan ve çözüm önerebiliyorsan\n"
                "  - Zamanı gelen bir hatırlatma varsa\n"
                "  Genel gözlem veya sohbet YAPMA. Kısa ve öz konuş."
            ),
            "helpful": (
                "🔊 YARDIMCI MOD: Sabah enerjisi, nazikçe faydalı olabilirsin.\n"
                "  Konuş eğer:\n"
                "  - Kullanıcı bir şey üzerinde çalışıyorsa ve yardımcı bir ipucun varsa\n"
                "  - Hata, uyarı veya hatırlatma varsa\n"
                "  - Motivasyon verici kısa bir gözlemin varsa\n"
                "  AMA: Gereksiz gevezelik, gereksiz övgü veya boş tekrarlar YASAK."
            ),
            "normal": (
                "🎯 STANDART PROAKTİFLİK: Normal çalışma saatleri.\n"
                "  Konuş eğer:\n"
                "  - Ekranda bir hata algıladıysan ve çözüm önerebiliyorsan\n"
                "  - Kullanıcının işine yarayan somut bir gözlem/bilgi varsa\n"
                "  - Zamanı gelen bir hatırlatma varsa\n"
                "  - Kullanıcı bir videoyu/görevi bitirmiş ve tebrik etmek mantıklıysa\n"
                "  KONUŞMA eğer:\n"
                "  - Ekran normal ve stabil ise\n"
                "  - Söyleyecek gerçekten değerli bir şeyin yoksa\n"
                "  - Son konuşmandan bu yana anlamlı bir değişiklik olmadıysa"
            ),
        }

        calibration = calibration_rules.get(threshold, calibration_rules["normal"])

        # İstatistik özeti
        stats_line = (
            f"[WATCHER İSTATİSTİK] "
            f"Toplam gözlem: {self._total_observations} | "
            f"Toplam proaktif eylem: {self._total_actions} | "
            f"Ardışık sessizlik: {self._consecutive_silence} | "
            f"Mevcut aralık: {self._current_interval:.0f}s | "
            f"Proaktiflik seviyesi: {level_name.upper()}"
        )

        watcher_prompt = (
            "[OTONOM GÖZLEM MODU]\n"
            f"Şu an saat: {now.strftime('%H:%M')}. Sen J.A.R.V.I.S.'in otonom 'Watcher' (Bekçi) modülüsün.\n"
            "Şu an kullanıcı sana bir şey sormadı. Kendi inisiyatifinle arka planda uyandın.\n\n"

            f"[ŞU ANKİ EKRAN DURUMU]\nKullanıcının ekranında şu an bu var: {screen_summary}\n\n"

            f"[SON KAYDEDİLEN HAFIZALAR]\n{recent_memory}\n\n"

            f"[DAVRANIŞ KALİBRASYONU — {level_name.upper()} MOD]\n"
            f"{calibration}\n\n"

            f"{stats_line}\n\n"

            "GÖREVİN:\n"
            "1. Ekran durumuna bak. Kullanıcı bir HATA alıyorsa veya kritik bir durumda yardıma ihtiyacı varsa "
            "proaktif olarak söze girip yardım teklif et.\n"
            "2. Hafızaya bak. Hatırlatman gereken acil bir şey varsa söyle.\n"
            "3. Eğer gerçekten önemli ve kullanıcının işine yarayacak bir fikrin varsa, [PROTOCOL: SPEAK] kullanarak "
            "nazikçe araya gir.\n"
            "4. Eğer her şey normalse ve rahatsız edecek kadar önemli bir konu YOKSA, hiçbir şey söyleme ve "
            "SADECE [SILENCE] yaz.\n\n"

            "⚠️ KALİBRASYON KURALLARI (KESİNLİKLE UYULMALI):\n"
            "• ASLA gereksiz gevezelik yapma. 'Güzel bir gün', 'her şey yolunda' gibi boş cümleler YASAK.\n"
            "• ASLA 'ekranınızı kontrol ettim, sorun yok' gibi gereksiz raporlar verme.\n"
            "• ASLA teknik detay paylaşma (hangi modülün çalıştığı, API durumu vb.)\n"
            "• Bir önceki döngüde söylediğin şeyi TEKRAR ETME.\n"
            "• Konuşacaksan 1-2 CÜMLE ile sınırlı kal. Uzun konuşma YASAK.\n"
            "• Şüphen varsa DAİMA [SILENCE] tercih et. Yanlış alarm vermektense sessiz kal."
        )

        return watcher_prompt

    # ─────────────────────────────────────────────────────────────────────────
    # GUI KART GÖNDERİMİ (Korunan fonksiyonlar)
    # ─────────────────────────────────────────────────────────────────────────

    def _send_vision_card(self, now: datetime, screen_summary: str, silent: bool = False):
        """
        [10/10] Ekran analizi özetini Mission Control'e gönderir.
        silent=True: sadece analiz raporu (eylemsiz gözlem)
        """
        if not (hasattr(self.engine, 'io_bridge') and self.engine.io_bridge):
            return
        try:
            prefix = "🔍 Gözlem Özeti" if silent else "👁 Ekran Analizi"
            interval_str = f"{self._current_interval:.0f}s"
            title = f"{prefix}  —  {now.strftime('%H:%M')}  [{interval_str}]"
            content = screen_summary[:400] + ("..." if len(screen_summary) > 400 else "")
            self.engine.io_bridge.display_card(title, content)
        except Exception as e:
            logger.warning(f"[WATCHER] Vision kartı gönderilemedi: {e}")

    def _send_watcher_action_card(self, now: datetime, screen_summary: str, action_response: str):
        """
        [10/10] Proaktif eylem gerçekleştiğinde Mission Control'e özet kart ekler.
        """
        if not (hasattr(self.engine, 'io_bridge') and self.engine.io_bridge):
            return
        try:
            title = f"⚡ Proaktif Eylem  —  {now.strftime('%H:%M')}"
            screen_part = (screen_summary[:120] + "...") if len(screen_summary) > 120 else screen_summary
            action_part = (action_response[:200] + "...") if len(action_response) > 200 else action_response
            content = (
                f"📺 Gözlem: {screen_part}\n\n"
                f"🤖 Tepki: {action_part}"
            )
            self.engine.io_bridge.display_card(title, content)
        except Exception as e:
            logger.warning(f"[WATCHER] Eylem kartı gönderilemedi: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # KONTROL
    # ─────────────────────────────────────────────────────────────────────────

    def stop(self):
        self._running = False

    def get_stats(self) -> dict:
        """Watcher istatistiklerini döndürür (debug/GUI için)."""
        return {
            "current_interval": self._current_interval,
            "total_observations": self._total_observations,
            "total_actions": self._total_actions,
            "consecutive_silence": self._consecutive_silence,
            "consecutive_stable": self._consecutive_stable,
            "running": self._running,
        }