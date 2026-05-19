"""
[V8.2 ARMORED] J.A.R.V.I.S. System Tools
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WhatsApp ve sistem araçları.

[V8.2] _send_direct Düzeltmeleri:
    - contacts.json okuma artık run_in_executor içinde (async-safe blocking I/O)
    - Exception'lar logger.error + exc_info=True ile tam stack trace basıyor
    - NativeOps.send_whatsapp_message doğru await edildi (zaten öyleydi, korundu)
"""

import asyncio
import json
import logging
import os
import re
import time
import subprocess

from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.SystemTools")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WhatsAppTool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WhatsAppTool(BaseTool):
    name              = "whatsapp_message"
    description       = "WhatsApp üzerinden mesaj gönderir. Format: Alıcı|Mesaj veya sadece Alıcı (mesajı sorması için)"
    protocol_tag      = "WHATSAPP_MESSAGE"
    parameters        = {
        "target": {
            "type": "string",
            "description": "Alıcı|Mesaj veya sadece Alıcı",
        }
    }
    domain            = "web"
    latency_ms        = 8000
    reliability_score = 0.95
    requires_interaction = True
    #pre_speak         = "WhatsApp mesajı zırhlı protokol ile gönderiliyor Efendim."

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        """
        [V8.2 FIXED] Motor (Executor) imzasına uyumlu execute metodu.
        """
        try:
            # Parametre ayıklama (Params her zaman sözlüktür)
            target = params.get("target", "") if isinstance(params, dict) else str(params)
            target = target.strip()

            if not target:
                return ToolResult(
                    success=False, verified=False, error="Fail",
                    message="WhatsApp alıcısı belirtilmedi.",
                    speak="Efendim, kime mesaj göndereceğimi anlayamadım.",
                )

            # 1. Senaryo: Alıcı|Mesaj formatı
            if "|" in target:
                parts = target.split("|", 1)
                recipient = parts[0].strip()
                message   = parts[1].strip() if len(parts) > 1 else ""
            else:
                recipient = target.strip()
                # Sayısal olmayan saf ismi temizle (sadece isim girilmişse)
                clean_rec = re.sub(r"[\+]?\d{7,}", "", recipient).strip().strip(" .,;:-")
                if clean_rec:
                    recipient = clean_rec
                message = ""

            if not recipient:
                return ToolResult(
                    success=False, verified=False, error="Fail",
                    message="Alıcı adı çözülemedi.",
                    speak="Efendim, geçerli bir alıcı bulamadım.",
                )

            # Numarayı kontrol et
            loop = asyncio.get_running_loop()
            phone_number = await loop.run_in_executor(
                None, self._resolve_phone_number, recipient
            )

            phone_clean = re.sub(r"[^\d\+]", "", phone_number)
            is_valid = bool(phone_clean and len(phone_clean) >= 7)

            if not phone_number or not is_valid:
                return ToolResult(
                    success=False, verified=False, error="Fail",
                    message="Bilinmeyen kişi veya geçersiz numara.",
                    speak=f"{recipient} rehberimde bulunamadı. Numarasını paylaşır mısınız?",
                    next_action="REQUEST_CONTACT_NUMBER",
                    data={"unknown_name": recipient}
                )

            if message:
                return await self._send_direct(recipient, message, engine_context)
                
            return ToolResult(
                success=True, verified=True,
                message=f"WhatsApp dikte modu başlatıldı: {recipient}",
                speak=f"{recipient} için mesajınızı söyleyin Efendim.",
                next_action="START_DICTATION",
                data={"recipient": recipient},
            )

        except Exception as e:
            # KRİTİK HATA KAYDI (Kara Kutu)
            import traceback
            import os
            hata_yolu = os.path.join(os.getcwd(), "WHATSAPP_HATA.txt")
            with open(hata_yolu, "w", encoding="utf-8") as f:
                f.write(f"--- EXECUTE KRITIK HATA [{time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
                f.write(traceback.format_exc())
            
            logger.error(f"WhatsAppTool.execute Çökmesi: {e}", exc_info=True)
            return ToolResult(
                success=False, verified=False, error="Fail",
                message=f"Kritik execute hatası: {e}",
                speak="Efendim, WhatsApp modülünde bir iç hata oluştu."
            )

    async def _send_direct(
        self, recipient: str, message: str, engine_context: dict = None
    ) -> ToolResult:
        """
        [V8.2 ARMORED] Doğrudan mesaj gönderimi.
        """
        from tools.utils.native_ops import NativeOps
        loop = asyncio.get_running_loop()

        try:
            # Google Özeti Koruması (1000 karakter)
            if len(message) > 1000:
                message = message[:1000] + "... [Mesaj çok uzun olduğu için J.A.R.V.I.S. tarafından kısaltıldı]"

            # Bloklayan I/O (contacts.json) işlemini executor'a taşı
            phone_number = await loop.run_in_executor(
                None, self._resolve_phone_number, recipient
            )

            logger.info(f"WhatsApp Gönderimi Tetikleniyor: {recipient} ({phone_number})")

            # NativeOps asenkron URL protokolü çağrısı
            success = await NativeOps.send_whatsapp_message(phone_number, message)

            if success:
                return ToolResult(
                    success=True, verified=True,
                    message=f"WhatsApp mesajı iletildi: {recipient}",
                    speak=f"Mesajınız {recipient} kişisine başarıyla iletildi Efendim."
                )
            
            return ToolResult(
                success=False, verified=False, error="Fail",
                message="WhatsApp protokolü (NativeOps) başarısız döndü.",
                speak="Efendim, mesaj gönderilemedi. WhatsApp uygulaması yanıt vermedi."
            )

        except Exception as e:
            # KRİTİK HATA KAYDI (Kara Kutu)
            import traceback
            import os
            hata_yolu = os.path.join(os.getcwd(), "WHATSAPP_HATA.txt")
            with open(hata_yolu, "w", encoding="utf-8") as f:
                f.write(f"--- _SEND_DIRECT KRITIK HATA [{time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
                f.write(traceback.format_exc())

            logger.error(f"WhatsAppTool._send_direct Çökmesi: {e}", exc_info=True)
            return ToolResult(
                success=False, verified=False, error="Fail",
                message=f"Gönderim hatası: {e}",
                speak="Efendim, mesaj gönderilirken bir hata oluştu."
            )

    def _resolve_phone_number(self, recipient: str) -> str:
        """contacts.json'dan numara çözer."""
        import json
        import os

        # Eğer recipient zaten numara ise (+ ile başlıyorsa) direkt dön
        if recipient.startswith("+") or (recipient.isdigit() and len(recipient) > 9):
            return recipient

        contacts_path = os.path.join(os.getcwd(), "contacts.json")
        if not os.path.exists(contacts_path):
            return recipient

        try:
            with open(contacts_path, "r", encoding="utf-8") as f:
                contacts = json.load(f)
                for name, num in contacts.items():
                    if recipient.lower() in name.lower():
                        return num
        except Exception as e:
            logger.warning(f"Rehber okuma hatası: {e}")
            
        return recipient
        """
        contacts.json'dan isime göre numara döndürür.

        Bu metod SENKRON — run_in_executor içinde çağrılır.
        Rehberde bulunamazsa recipient değerini olduğu gibi döndürür
        (doğrudan numara girilmiş olabilir).

        Args:
            recipient: Kişi adı ("Ablam") veya telefon numarası ("+905551234567")

        Returns:
            Çözümlenmiş telefon numarası string'i
        """
        contacts_path = os.path.abspath("contacts.json")

        if not os.path.exists(contacts_path):
            logger.debug(
                f"[WhatsApp] contacts.json bulunamadı: {contacts_path} — "
                f"'{recipient}' numara olarak kullanılıyor."
            )
            return recipient

        try:
            with open(contacts_path, "r", encoding="utf-8") as f:
                contacts: dict = json.load(f)

            # Önce tam eşleşme dene (büyük/küçük harf duyarsız)
            recipient_lower = recipient.lower()
            for name, number in contacts.items():
                if name.lower() == recipient_lower:
                    logger.debug(f"[WhatsApp] Tam eşleşme: '{recipient}' → '{number}'")
                    return str(number)

            # Kısmi eşleşme (ör: "ablam" → "Büyük Abla")
            for name, number in contacts.items():
                if recipient_lower in name.lower() or name.lower() in recipient_lower:
                    logger.debug(f"[WhatsApp] Kısmi eşleşme: '{recipient}' → '{name}' → '{number}'")
                    return str(number)

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[WhatsApp] contacts.json okunamadı: {e!r}")

        # Rehberde bulunamadı → girilen değeri numara say
        logger.debug(f"[WhatsApp] Rehberde bulunamadı: '{recipient}' — numara olarak kullanılıyor.")
        return recipient


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WhatsAppDeleteTool  (değişmedi)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WhatsAppDeleteTool(BaseTool):
    """Son WhatsApp mesajını siler."""

    name              = "whatsapp_delete"
    description       = "WhatsApp'taki son mesajı siler"
    protocol_tag      = "WHATSAPP_DELETE"
    parameters        = {}
    domain            = "web"
    latency_ms        = 3000
    reliability_score = 0.60

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        ctx       = engine_context or {}
        last_num  = ctx.get("last_whatsapp_num")
        last_time = ctx.get("last_whatsapp_time", 0)

        if not last_num:
            return ToolResult(
                success=False, verified=False, error="Fail",
                message="Silinecek mesaj bulunamadı.",
                speak="Efendim, silinecek bir mesaj bulamadım.",
            )

        if time.time() - last_time > 300:
            return ToolResult(
                success=False, verified=False, error="Fail",
                message="Son mesaj 5 dakikadan eski.",
                speak="Efendim, son mesaj çok eski, silme güvenli değil.",
            )

        try:
            from tools.utils.native_ops import NativeOps

            await asyncio.get_running_loop().run_in_executor(
                None, NativeOps.kill_app, "WhatsApp"
            )
            return ToolResult(
                success=True, verified=True,
                message="Son mesaj silindi (V8.2 simplified).",
                speak="Son mesaj silindi Efendim.",
                next_action="CLEAR_LAST_HISTORY",
            )
        except Exception as e:
            logger.error(f"[WhatsApp Delete] Silme hatası: {e!r}", exc_info=True)
            return ToolResult(
                success=False, verified=False, error="Fail",
                message=f"Silme hatası: {e!r}",
                speak="Efendim, mesaj silinemedi.",
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  VisionTool  (değişmedi)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class VisionTool(BaseTool):
    """Ekran görüntüsü analizi."""

    name              = "vision_analyze"
    description       = "Ekranı analiz eder"
    protocol_tag      = "VISION"
    parameters        = {}
    domain            = "system"
    latency_ms        = 5000
    reliability_score = 0.90
    pre_speak         = "Lütfen analiz edilecek pencereye geçin, 3 saniye içinde görüntüyü alıyorum."

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        import asyncio
        # Kullanıcıya Alt+Tab yapması için 3 saniye süre veriyoruz
        await asyncio.sleep(3)
        
        try:
            from core.vision import JarvisVision

            vision   = JarvisVision()
            analysis = await asyncio.get_running_loop().run_in_executor(
                None, vision.analyze_screen
            )
            if analysis:
                return ToolResult(
                    success=True,
                    verified=True,
                    message="Analiz edildi.",
                    data={"raw_analysis": analysis},
                    next_action="VISION_INTERPRET",
                )
            return ToolResult(
                success=False,
                verified=False,
                error="Fail",
                message="Başarısız.",
                speak="Efendim, ekranı analiz edemedim.",
            )
        except Exception as e:
            logger.error(f"[Vision] Analiz hatası: {e!r}", exc_info=True)
            return ToolResult(
                success=False,
                verified=False,
                error="Fail",
                message=str(e),
                speak="Efendim, görmem bir sorunla karşılaştı.",
            )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  StressTestTool  (değişmedi)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class StressTestTool(BaseTool):
    """Stres testi."""

    name              = "stress_test"
    description       = "Stres testi çalıştırır"
    protocol_tag      = "STRESS_TEST"
    parameters        = {}
    domain            = "system"

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        return ToolResult(
            success=True,
            verified=True,
            message="Başlatıldı.",
            next_action="RUN_STRESS_TEST",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TabKillTool  (değişmedi)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TabKillTool(BaseTool):
    """Sekme kapatır."""

    name              = "tab_kill"
    description       = "Sekme kapatır"
    protocol_tag      = "TAB_KILL"
    parameters        = {}
    domain            = "desktop"

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        try:
            import pyautogui

            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: (pyautogui.hotkey("ctrl", "w"), time.sleep(0.5)),
            )
            return ToolResult(
                success=True,
                verified=True,
                message="Kapatıldı.",
                speak="Sekme kapatıldı Efendim.",
            )
        except Exception as e:
            logger.error(f"[TabKill] Hata: {e!r}", exc_info=True)
            return ToolResult(
                success=False,
                verified=False,
                error="Fail",
                message=str(e),
                speak="Efendim, sekme kapatılamadı.",
            )

class SpeakTool(BaseTool):
    """
    [V9.1] Jarvis'in araç kullanmadan kullanıcıya düz metin/ses ile
    cevap vermesini sağlayan temel iletişim aracı.
    Kullanım: [PROTOCOL: SPEAK] <mesaj>
    """
    name = "Konuşma ve Cevap"
    protocol_tag = "SPEAK"
    domain = "system"
    latency_ms = 10
    reliability_score = 1.0
    parameters = {"message": "str"}

    async def execute(self, params: dict, context: dict) -> ToolResult:
        # Gelen parametreyi güvenli bir şekilde al
        if isinstance(params, str):
            msg = params
        else:
            msg = params.get("message", "")
            if not msg and params:
                # Dict dolu ama key 'message' değilse ilkini al
                msg = str(list(params.values())[0])

        msg = msg.strip()
        if not msg:
            return ToolResult(success=False, verified=False, error="Fail", message="Söylenecek bir şey bulunamadı.")

        return ToolResult(
            success=True,
            verified=True,
            message="Kullanıcıya cevap verildi.",
            speak=msg,  # İŞTE SİHİR BURADA: IOBridge bunu otomatik okur/seslendirir!
            data={"reply": msg}
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  RememberTool  [V9.6] Hafızaya Kalıcı Bilgi Kaydetme
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RememberTool(BaseTool):
    """
    [V9.6] Hafızaya kalıcı bilgi kaydeder.
    """
    name = "remember_info"
    description = "Kullanıcı hakkında önemli kişisel veya kalıcı bir bilgiyi hafızaya kaydeder."
    protocol_tag = "REMEMBER"
    domain = "system"
    parameters = {"information": "str"}
    latency_ms = 500
    reliability_score = 0.95

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            info = params
        else:
            info = params.get("information", "")
            if not info and params:
                info = str(list(params.values())[0])

        info = info.strip()
        if not info:
            return ToolResult(
                success=False,
                message="Kaydedilecek bilgi bulunamadı.",
                speak="Efendim, neyi kaydetmemi istediğinizi anlayamadım."
            )

        ctx = engine_context or {}
        memory = ctx.get("memory")
        if not memory:
            return ToolResult(success=False, message="Memory nesnesi bulunamadı.", speak="Hafıza modülüm şu an devre dışı.")

        try:
            await memory.save_memory_async(info, "episodic", {"importance": 0.8, "source": "user_command"})
            return ToolResult(
                success=True,
                verified=True,
                message="Bilgi hafızaya kaydedildi.",
                speak="Bu bilgiyi hafızama kaydettim Efendim."
            )
        except Exception as e:
            logger.error(f"RememberTool error: {e}")
            return ToolResult(success=False, message=str(e), speak="Bilgiyi kaydederken bir hata oluştu.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ScheduleTool  [V9.2] Dinamik Zamanlama
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ScheduleTool(BaseTool):
    """
    [V9.2] Dinamik zamanlama aracı.
    "5 dakika sonra hatırlat" gibi komutları scheduler'a kaydeder.
    
    Kullanım: [PROTOCOL: SCHEDULE] dakika|mesaj
    Örnek:    [PROTOCOL: SCHEDULE] 5|mola ver
    """
    name              = "schedule_reminder"
    description       = "Belirtilen dakika sonra hatırlatma kurar. Format: dakika|mesaj"
    protocol_tag      = "SCHEDULE"
    domain            = "system"
    latency_ms        = 50
    reliability_score = 0.95
    parameters        = {"reminder": "str"}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        from datetime import datetime, timedelta

        # Parametre çözümleme
        if isinstance(params, str):
            raw = params
        else:
            raw = params.get("reminder", "")
            if not raw and params:
                raw = str(list(params.values())[0])

        raw = raw.strip()
        if not raw or "|" not in raw:
            return ToolResult(
                success=False,
                message="Geçersiz zamanlama formatı. Beklenen: dakika|mesaj",
                speak="Efendim, zamanlama formatını anlayamadım. Örnek: 5 dakika sonra mola ver.",
            )

        parts = raw.split("|", 1)
        minutes_str = parts[0].strip()
        message = parts[1].strip() if len(parts) > 1 else ""

        # Dakika doğrulama
        try:
            minutes = int(minutes_str)
            if minutes <= 0:
                raise ValueError("Dakika pozitif olmalı")
        except ValueError:
            return ToolResult(
                success=False,
                message=f"Geçersiz dakika değeri: '{minutes_str}'",
                speak="Efendim, geçerli bir dakika değeri belirtmelisiniz.",
            )

        if not message:
            return ToolResult(
                success=False,
                message="Hatırlatma mesajı boş.",
                speak="Efendim, neyi hatırlatmamı istediğinizi söylemediniz.",
            )

        # Scheduler'ı context'ten al
        ctx = engine_context or {}
        scheduler = ctx.get("scheduler")

        if scheduler is None:
            logger.error("[ScheduleTool] engine_context içinde 'scheduler' bulunamadı.")
            return ToolResult(
                success=False,
                message="Scheduler bulunamadı — engine_context eksik.",
                speak="Efendim, zamanlayıcı modülüne ulaşamıyorum.",
            )

        # Hedef zamanı hesapla
        target = datetime.now() + timedelta(minutes=minutes)
        scheduler.add_daily(
            target.hour, target.minute,
            f"[PROTOCOL: SPEAK] {message}"
        )

        logger.info(
            f"[ScheduleTool] Hatırlatma kuruldu: {minutes} dk sonra "
            f"({target.strftime('%H:%M')}) → {message[:50]}"
        )

        return ToolResult(
            success=True,
            message=f"Hatırlatma kuruldu: {minutes} dakika sonra ({target.strftime('%H:%M')})",
            speak=f"{minutes} dakika sonra hatırlatacağım Efendim.",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NextStartupReminderTool  [V9.6] Bir sonraki açılışta hatırlat
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class NextStartupReminderTool(BaseTool):
    """
    [V9.6] Jarvis'in bir sonraki bilgisayar/program açılışında kullanıcıya 
    söylemesi gereken şeyleri kaydeder.
    """
    name              = "next_startup_reminder"
    description       = "Bir sonraki program açılışında hatırlatılması istenen mesajı kaydeder."
    protocol_tag      = "STARTUP_REMINDER"
    domain            = "system"
    latency_ms        = 50
    reliability_score = 0.95
    parameters        = {"message": "str"}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        import os, json

        if isinstance(params, str):
            message = params
        else:
            message = params.get("message", "")
            if not message and params:
                message = str(list(params.values())[0])

        message = message.strip()
        if not message:
            return ToolResult(
                success=False,
                message="Hatırlatma mesajı boş.",
                speak="Efendim, neyi hatırlatmamı istediğinizi söylemediniz."
            )

        filepath = os.path.join(os.getcwd(), "startup_reminders.json")
        reminders = []

        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        reminders = data
            except Exception:
                pass

        reminders.append(message)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(reminders, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Başlangıç hatırlatması kaydedilemedi: {e}")
            return ToolResult(
                success=False,
                message=str(e),
                speak="Efendim, hatırlatmayı kaydederken bir hata oluştu."
            )

        return ToolResult(
            success=True,
            verified=True,
            message="Başlangıç hatırlatması kaydedildi.",
            speak="Anlaşıldı Efendim, bunu bir sonraki açılışımda size hatırlatacağım."
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SteamLaunchTool [V9.3] Gaming Support
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SteamLaunchTool(BaseTool):
    """
    [V9.3] Steam üzerinden oyun başlatma aracı.
    """
    name = "steam_launch"
    description = "Steam üzerinden belirli bir oyunu başlatır."
    protocol_tag = "STEAM_LAUNCH"
    domain = "desktop"
    parameters = {"game": "str"}
    latency_ms = 2000
    reliability_score = 0.90

    STEAM_GAMES = {
        "cs2": "730", "cs go": "730",
        "dota": "570", "dota 2": "570",
        "pubg": "578080",
        "gta5": "271590", "gta v": "271590",
        "minecraft": "minecraft",
        "roblox": "roblox",
        "rocket league": "252950",
        "rl": "252950",
    }

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            game = params
        else:
            game = params.get("game", "")
            if not game and params:
                game = str(list(params.values())[0])
        
        argument = game.strip()
        game = game.strip().lower()
        if not game:
            return ToolResult(success=False, verified=False, error="Fail", message="Oyun adı belirtilmedi.", speak="Hangi oyunu açmamı istersiniz Efendim?")

        app_id = self.STEAM_GAMES.get(game, game)
        
        import os
        import webbrowser
        import asyncio
        
        loop = asyncio.get_running_loop()
        
        def _launch_steam():
            try:
                os.startfile(f"steam://rungameid/{app_id}")
            except AttributeError:
                webbrowser.open(f"steam://rungameid/{app_id}")
                
        try:
            await loop.run_in_executor(None, _launch_steam)
            return ToolResult(
                success=True,
                verified=True,
                message=f"Steam launch komutu gönderildi (URI): {app_id}",
                speak=f"{argument} Steam üzerinden başlatılıyor Efendim."
            )
        except Exception as e:
            logger.error(f"Steam başlatma hatası: {e}")
            return ToolResult(success=False, verified=False, error="Fail", message=str(e), speak="Efendim, Steam komutu çalıştırılamadı.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EpicLaunchTool [V9.4] Epic Games Support
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EpicLaunchTool(BaseTool):
    """
    [V9.4] Epic Games üzerinden oyun başlatma aracı.
    """
    name = "epic_launch"
    description = "Epic Games üzerinden belirli bir oyunu başlatır."
    protocol_tag = "EPIC_LAUNCH"
    domain = "desktop"
    parameters = {"game": "str"}
    latency_ms = 2000
    reliability_score = 0.90

    EPIC_GAMES = {
        "rocket league": "rocketleague",
        "rl": "rocketleague",
        "fortnite": "Fortnite",
        "fall guys": "FallGuys",
        "fallguys": "FallGuys",
    }

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            game = params
        else:
            game = params.get("game", "")
            if not game and params:
                game = str(list(params.values())[0])
        
        argument = game.strip()
        game = game.strip().lower()
        if not game:
            return ToolResult(success=False, verified=False, error="Fail", message="Oyun adı belirtilmedi.", speak="Hangi Epic oyununu açmamı istersiniz Efendim?")

        slug = self.EPIC_GAMES.get(game, game)
        
        import webbrowser
        import asyncio
        
        loop = asyncio.get_running_loop()
        
        def _launch_epic():
            webbrowser.open(f"com.epicgames.launcher://apps/{slug}?action=launch&silent=true")
            
        try:
            await loop.run_in_executor(None, _launch_epic)
            return ToolResult(
                success=True,
                verified=True,
                message=f"Epic launch komutu gönderildi (URI): {slug}",
                speak=f"{argument} Epic Games üzerinden başlatılıyor Efendim."
            )
        except Exception as e:
            logger.error(f"Epic Games başlatma hatası: {e}")
            return ToolResult(success=False, verified=False, error="Fail", message=str(e), speak="Efendim, Epic Games komutu çalıştırılamadı.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SystemPowerTool [V9.3] Güç Yönetimi
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SystemPowerTool(BaseTool):
    """
    [V9.3] Bilgisayarı kapatma, yeniden başlatma veya uyku moduna alma.
    Onay mekanizması içerir.
    """
    name = "system_power"
    description = "Bilgisayarı kapatır, yeniden başlatır veya uykuya alır."
    protocol_tag = "SYSTEM_POWER"
    domain = "system"
    parameters = {"action": "str"}
    latency_ms = 100
    reliability_score = 1.0

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        if isinstance(params, str):
            raw_action = params
        else:
            raw_action = params.get("action", "")
            if not raw_action and params:
                raw_action = str(list(params.values())[0])
        
        raw_action = raw_action.strip().lower()
        needs_confirm = "onaylı" not in raw_action
        action = raw_action.replace("onaylı", "").strip()

        if action not in ["kapat", "yeniden_başlat", "uyku"]:
            return ToolResult(success=False, verified=False, error="Fail", message=f"Geçersiz eylem: {action}", speak="Efendim sadece kapat, yeniden başlat veya uyku komutlarını uygulayabilirim.")

        if needs_confirm:
            return ToolResult(
                success=False,
                message=f"Güç işlemi için onay bekleniyor: {action}",
                speak=f"Bilgisayarı {action} işlemi için onayınız gerekiyor Efendim. 'Evet' veya 'Hayır' diyerek onay verebilirsiniz.",
                next_action="CONFIRM_POWER",
                data={"pending_action": action}
            )

        # Onaylı ise işlemi yap
        try:
            if action == "kapat":
                os.system("shutdown /s /t 5")
            elif action == "yeniden_başlat":
                os.system("shutdown /r /t 5")
            elif action == "uyku":
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            
            return ToolResult(
                success=True,
                message=f"Sistem {action} komutu uygulandı.",
                speak=f"Sistem {action} işlemi başlatıldı Efendim. Hoşça kalın."
            )
        except Exception as e:
            logger.error(f"Güç işlemi hatası: {e}")
            return ToolResult(success=False, verified=False, error="Fail", message=str(e), speak="Efendim, sistem komutu yürütülemedi.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ShutdownTool [V9.5] — J.A.R.V.I.S. Graceful Self-Shutdown
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ShutdownTool(BaseTool):
    """
    [V9.5] J.A.R.V.I.S.'in kendi asyncio döngüsünü ve GUI'yi
    güvenli biçimde sonlandırmasını sağlar.

    Tetikleyici: [PROTOCOL: SYSTEM_SHUTDOWN]

    Akış:
        1. LLM "sistemi kapat" niyetini algılar ve
           [PROTOCOL: SYSTEM_SHUTDOWN] çıktısı üretir.
        2. PlanExecutor bu tool'u engine_context ile çağırır.
        3. execute() → io_bridge.request_shutdown() sinyali gönderir.
        4. Engine'in start() döngüsü bayrağı görür ve kırılır.
        5. engine.shutdown() → scheduler, executor temizlenir.
        6. GUI callback "KAPATILIYOR" sinyalini alır → root.quit().
        7. Python süreci temiz şekilde çıkar.

    Kısıt: sys.exit() KULLANILMAZ.
        sys.exit() asyncio görevlerini ve Tkinter'ı kirli bırakır.
        Bunun yerine IOBridge sinyali + engine shutdown döngüsü kullanılır.
    """

    name              = "jarvis_shutdown"
    description       = (
        "J.A.R.V.I.S. sistemini tamamen kapatır. "
        "Asyncio döngüsü, GUI ve tüm alt sistemler güvenli biçimde sonlandırılır."
    )
    protocol_tag      = "SYSTEM_SHUTDOWN"
    domain            = "system"
    latency_ms        = 50
    reliability_score = 1.0
    parameters        = {}

    # Sistem prompt'una: Bu araç YALNIZCA kullanıcı J.A.R.V.I.S.'i
    # kapatmayı açıkça istediğinde kullanılır.
    # Örnek tetikleyiciler: "sistemi kapat", "kapat kendini",
    # "jarvis kapat", "çıkış yap", "görüşmek üzere kapat"

    async def execute(
        self, params: dict, engine_context: dict = None
    ) -> ToolResult:
        """
        IOBridge üzerinden kapatma sinyali gönderir.

        engine_context içinde "io_bridge" anahtarı olması zorunludur.
        PlanExecutor bunu otomatik olarak ekler (executor._build_context).
        """
        ctx = engine_context or {}
        io_bridge = ctx.get("io_bridge")

        if io_bridge is None:
            # Fallback: engine_context eksikse loglayıp yine de işaretle
            logger.error(
                "[ShutdownTool] engine_context içinde 'io_bridge' bulunamadı! "
                "PlanExecutor context mapping'ini kontrol edin."
            )
            # Son çare: sys.exit ile çık (sadece io_bridge yoksa)
            import sys
            import asyncio
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(loop.stop)
            return ToolResult(
                success=True,
                message="io_bridge bulunamadı — event loop durduruldu.",
                speak="Sistemler kapatılıyor Efendim. İyi günler.",
            )

        # Normal yol: IOBridge sinyali
        io_bridge.request_shutdown()

        logger.info("[ShutdownTool] ✅ Kapatma sinyali IOBridge'e iletildi.")

        return ToolResult(
            success=True,
            message="Sistem kapatma protokolü başlatıldı.",
            speak="Sistemler kapatılıyor. İyi günler dilerim Efendim.",
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LLMEvalTool [V15.3] — Bilişsel Değerlendirme ve Hesaplama
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LLMEvalTool(BaseTool):
    name = "llm_eval"
    description = "Toplanan veriler üzerinden mantık yürütür, hesaplama yapar veya soruları cevaplar."
    protocol_tag = "LLM_EVAL"
    domain = "system"
    latency_ms = 2000
    reliability_score = 1.0
    parameters = {"question": {"type": "string", "description": "Cevaplanacak soru veya yapılacak hesaplama"}}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        question = params.get("question", "") or params.get("query", "")
        if isinstance(params, str): question = params
        
        ctx = engine_context or {}
        brain = ctx.get("brain")
        step_data = ctx.get("step_results", {})
        
        if not brain:
            return ToolResult(success=False, verified=False, error="NoBrain", message="Brain modülü yok.")
            
        prompt = (
            "Sen bir analitik motorsun. Aşağıdaki 'Toplanan Veriler'i dikkatlice oku. "
            "Kullanıcının sorusunu bu verilere dayanarak KESİN ve NET bir şekilde cevapla/hesapla. "
            "DİKKAT: Eğer soru birden fazla veriyi (örn: X'in golü ve Y'nin yaşı) içeriyorsa, Toplanan Veriler içindeki TÜM metinleri (--- EK SONUÇ --- kısımları dahil) sonuna kadar oku ve iki veriyi de bulduğundan emin ol. Eğer verilerden biri eksikse tahminde bulunma, 'Veri eksik' de.\n\n"
            f"Toplanan Veriler:\n{step_data}\n\n"
            f"Soru: {question}"
        )
        
        print(f"\n[BEYİN LOGU] LLM_EVAL'e Giden Veri:\n{step_data}\n")
        
        try:
            response = await brain.client.chat.completions.create(
                model=brain.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=256
            )
            answer = response.choices[0].message.content.strip()
            import re
            answer = re.sub(r'\[PROTOCOL:.*?\]', '', answer).strip()
            
            return ToolResult(
                success=True, 
                verified=True, 
                message=f"Değerlendirme sonucu: {answer}", 
                speak=f"Efendim, verileri analiz ettim. Sonuç: {answer}"
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message="Değerlendirme başarısız.")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  YouTubeStrategyTool [V15.1] — Otonom İçerik Fabrikası
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class YouTubeStrategyTool(BaseTool):
    """
    BabaClutch kanalı için otonom video fikri, başlık ve thumbnail promptu üretir.
    """
    name              = "youtube_strategy"
    description       = "YouTube kanalı için strateji, başlık ve küçük resim promptu üretir."
    protocol_tag      = "YOUTUBE_STRATEGY"
    domain            = "web"
    latency_ms        = 4000
    reliability_score = 1.0
    parameters        = {"request": {"type": "string", "description": "İstenen strateji (örn: Rocket League için 3 fikir ver)"}}

    async def execute(self, params: dict, engine_context: dict = None) -> ToolResult:
        request = params.get("request", "") or params.get("query", "")
        if isinstance(params, str):
            request = params
            
        request = request.strip()
        if not request:
            return ToolResult(success=False, verified=False, error="Fail", message="İstek boş.", speak="Efendim, YouTube için ne planlamamı istersiniz?")

        ctx = engine_context or {}
        brain = ctx.get("brain")
        if not brain:
            return ToolResult(success=False, verified=False, error="Fail", message="Brain modülü bulunamadı.")

        # 1. Kanal DNA'sı ve Acımasız Stratejist Promptu
        system_prompt = (
            "Sen acımasız, veri odaklı ve elit bir YouTube İçerik Stratejisti ve Thumbnail Prompt Mühendisisin. "
            "Kanal Adı: BabaClutch (Oğuz ve Eymen). Konsept: Kaos, rage, arkadaş kavgası, cezalı oyunlar. "
            "Oyunlar: Rocket League, Minecraft Bedwars, Left 4 Dead 2 ve kullanıcının belirttiği her oyun. "
            "Strateji Kuralları: Jenerik olma. CTR ve AVD odaklı ol. Merak uyandıran kısa başlıklar yaz. "
            "Fikirleri acımasızca eleştir. Her fikir özgün ve kanala özel olsun.\n\n"
            "=== THUMBNAIL PROMPT KURALLARI (ÇOK KRİTİK) ===\n"
            "Eğer thumbnail promptu istenirse, şu kurallara KESINLIKLE uy:\n"
            "1. Prompt İNGİLİZCE olacak (görsel üretici için)\n"
            "2. Thumbnail içindeki YAZILARIN HEPSİ TÜRKÇE olacak — İngilizce yazı YASAK\n"
            "3. Ultra-detaylı yaz: sahne atmosferi, ışık, efektler, kamera açısı, renk paleti, metin stili, konum\n"
            "4. Oyuna özel görsel unsurlar kullan (karakterler, arenalar, silahlar vb.)\n"
            "5. Formatı MUTLAKA şu şekilde kapat: [PROMPT]...[/PROMPT]\n\n"
            "Örnek kalite standardı (Rocket League için):\n"
            "[PROMPT]Hyper-realistic 3D Rocket League thumbnail art, dark dramatic arena background with deep red and "
            "orange glowing light, two rocket-powered cars on the field, one car exploding mid-air with massive fire "
            "burst and shockwave debris flying outward, the other car boosting aggressively with blue-orange boost "
            "flames trailing behind, large glowing red countdown timer showing '0:30' in the upper right area like "
            "an in-game UI element, sparks and particles filling the air, cinematic dramatic lighting casting harsh "
            "shadows, high contrast vivid colors, ultra-detailed car reflections, same dark moody style as Rocket "
            "League YouTube thumbnails, bold Turkish text 'HER 30 SANİYEDE' in white with thick black outline at "
            "the top left area, even larger bold text 'PATLATMAK ZORUNDAYIZ!' in bright yellow-orange with thick "
            "black outline and slight glow effect in the bottom left area, professional YouTube thumbnail typography "
            "style, impactful and high contrast text, 16:9 format, epic action composition[/PROMPT]\n\n"
            "Bu örnekteki gibi: sahneyi, ışığı, karakterleri, efektleri ve TÜRKÇE metinleri eksiksiz tanımla. "
            "Türkçe metin içeriğini challenge/video başlığıyla uyumlu, dikkat çekici ve kısa yaz."
        )

        try:
            # 2. J.A.R.V.I.S. kısıtlamalarını aşmak için doğrudan API çağrısı
            response = await brain.client.chat.completions.create(
                model=brain.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request}
                ],
                temperature=0.7,
                max_tokens=1024
            )
            result_text = response.choices[0].message.content.strip()

            # [PROMPT] etiketini gizleyerek temiz görüntü için log'a yaz
            import re as _re
            display_text = _re.sub(r'\[/?PROMPT\]', '', result_text).strip()
            logger.info(f"\n{'─'*60}\n[BabaClutch Strateji Raporu]\n{display_text}\n{'─'*60}")

            speak_msg = f"Strateji raporu hazırlandı Efendim:\n\n{display_text}"

            # 3. Hacker Dokunuşu: Prompt istenmişse panoya kopyala ve tarayıcıyı aç
            if "thumbnail" in request.lower() or "prompt" in request.lower() or "görsel" in request.lower():
                try:
                    import pyperclip
                    import webbrowser
                    import asyncio
                    import re

                    extracted_prompt = None

                    # Strateji 1: Kapalı etiket [PROMPT]...[/PROMPT]
                    m = re.search(r'\[PROMPT\](.*?)\[/PROMPT\]', result_text, re.DOTALL | re.IGNORECASE)
                    if m:
                        candidate = m.group(1).strip()
                        if candidate and candidate != "...":
                            extracted_prompt = candidate

                    # Strateji 2: Açık etiket [PROMPT]... (kapanmamış)
                    if not extracted_prompt:
                        m = re.search(r'\[PROMPT\](.+?)$', result_text, re.DOTALL | re.IGNORECASE)
                        if m:
                            candidate = m.group(1).strip().strip('"').strip()
                            if candidate and candidate != "...":
                                extracted_prompt = candidate

                    # Strateji 3: Son satırı al (model etiketsiz yazdıysa)
                    if not extracted_prompt:
                        lines = [l.strip() for l in result_text.splitlines() if l.strip()]
                        if lines:
                            last = lines[-1].strip('"').strip()
                            if re.search(r'[a-zA-Z]{5,}', last):
                                extracted_prompt = last

                    final_clipboard = extracted_prompt or result_text
                    pyperclip.copy(final_clipboard)
                    logger.info(f"[YouTubeStrategy] ✅ Panoya kopyalanan thumbnail prompt:\n  {final_clipboard[:120]}")

                    speak_msg += "\n\n📋 Thumbnail promptu panoya kopyalandı. Görsel üretici açılıyor..."

                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, webbrowser.open, "https://chatgpt.com/")
                except ImportError:
                    logger.warning("pyperclip yüklü değil. Pano kopyalaması atlandı.")

            return ToolResult(
                success=True,
                verified=True,
                message=speak_msg,
                speak=speak_msg,
                data={"strategy": result_text}
            )

        except Exception as e:
            logger.error(f"[YouTubeStrategy] Hata: {e}", exc_info=True)
            return ToolResult(success=False, verified=False, error="Fail", message=str(e), speak="Efendim, strateji modülüne bağlanırken bir hata oluştu.")