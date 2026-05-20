"""
[V13.0] J.A.R.V.I.S. — Typeless-Grade Speech-to-Text Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mimari:
    1. Mikrofon kaydı  → speech_recognition (aynı PyAudio altyapısı)
    2. Transkripsiyon   → Groq Whisper Large-v3-Turbo (ultra hızlı, kusursuz Türkçe)
    3. AI Polisher      → Groq LLM veya Gemini (dolgu/gürültü temizleme + noktalama)
    4. Fallback         → Google Web Speech API (internet/API kesilirse)

Zamanlama Felsefesi:
    - Konuşma İÇİNDE duraksamalara SABIR göster (pause_threshold)
    - Konuşma BİTTİĞİNDE hızlıca kes ve işle (non_speaking_duration)
    - phrase_time_limit ile sonsuz beklemeyi engelle
"""

import speech_recognition as sr
import pygame
import math
import array
import os
import io
import logging
from typing import Optional

logger = logging.getLogger("JARVIS.STT")

# ── Groq SDK ──
_HAS_GROQ = False
try:
    from groq import Groq
    _HAS_GROQ = True
except ImportError:
    logger.warning("[STT] groq paketi bulunamadı — Whisper devre dışı, Google fallback aktif.")

# ── Gemini SDK (AI Polisher alternatifi) ──
_HAS_GEMINI = False
try:
    import google.generativeai as genai
    _HAS_GEMINI = True
except ImportError:
    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AI POLISHER — Typeless'ın Sırrı
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_POLISHER_SYSTEM_PROMPT = """Sen bir Türkçe metin düzelticisin. Görevin, sesli dikte ile elde edilmiş ham metni pürüzsüz, akıcı Türkçe'ye dönüştürmek.

Kurallar:
1. Dolgu kelimelerini ("ıı", "eee", "şey", "yani", "hım", "hıh", "ehm", "öö", "ööö", "ııı") metinden tamamen SİL.
2. Tekrar eden kelimeleri ve yarım kalan/düzeltilmiş ifadeleri temizle.
3. KENDİNİ DÜZELTME TESPİTİ: Konuşmacı bir kelime/ifade söyleyip hemen ardından düzeltiyorsa ("yarın pazartesi ay şey salı günü buluşalım"), yanlış söylenen kısmı SİL ve sadece düzeltilmiş/son halini kullan (→ "Yarın salı günü buluşalım."). Bu tür kalıpları tanı:
   - "X ay şey Y" → Y'yi kullan
   - "X yani Y" → Y'yi kullan
   - "X yok yok Y" → Y'yi kullan
   - "X değil Y" → Y'yi kullan (bağlama göre)
   - "X pardon Y" → Y'yi kullan
4. Uygun yerlere noktalama işaretleri (nokta, virgül, soru işareti, ünlem) ekle.
5. Cümle başlarını büyük harfle yaz.
6. Anlamı KESİNLİKLE değiştirme, sadece formu düzelt.
7. Eğer metin zaten temiz ve düzgünse, AYNEN döndür.
8. Sadece düzeltilmiş metni döndür — açıklama, yorum veya ek bilgi EKLEME.
9. Metin bir J.A.R.V.I.S. AI asistanına verilen sesli komut olabilir. Komut niteliğini koru."""


def _polish_with_groq(raw_text: str, api_key: str) -> Optional[str]:
    """Groq LLM ile ham transkripsiyon metnini parlatır."""
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _POLISHER_SYSTEM_PROMPT},
                {"role": "user", "content": raw_text}
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        polished = response.choices[0].message.content.strip()
        # LLM bazen tırnak içine alıyor, temizle
        if polished.startswith('"') and polished.endswith('"'):
            polished = polished[1:-1]
        if polished.startswith("'") and polished.endswith("'"):
            polished = polished[1:-1]
        return polished
    except Exception as e:
        logger.warning(f"[AI_POLISHER] Groq LLM parlatma hatası: {e}")
        return None


def _polish_with_gemini(raw_text: str, api_key: str) -> Optional[str]:
    """Gemini ile ham transkripsiyon metnini parlatır (Groq yedek)."""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            f"{_POLISHER_SYSTEM_PROMPT}\n\nMetin:\n{raw_text}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=1024,
            )
        )
        polished = response.text.strip()
        if polished.startswith('"') and polished.endswith('"'):
            polished = polished[1:-1]
        if polished.startswith("'") and polished.endswith("'"):
            polished = polished[1:-1]
        return polished
    except Exception as e:
        logger.warning(f"[AI_POLISHER] Gemini parlatma hatası: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANA STT SINIFI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SpeechToText:
    """
    Typeless-Grade Speech-to-Text Engine.

    Pipeline:
        Mikrofon → WAV bytes → Groq Whisper → AI Polisher → Temiz Metin
        (Fallback: Mikrofon → Google Web Speech API → Temel Filtre → Metin)
    """

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 4000

        # ── [V13.1] Mute Flag — Yazılı modda mikrofonu tamamen devre dışı bırakır ──
        self._muted: bool = False

        # ── Zamanlama Felsefesi ──
        # pause_threshold: Konuşma İÇİNDE duraksamalara kaç sn tolerans
        #   → 1.4 sn = düşünme duraksamalarında hemen kesme
        # non_speaking_duration: "Sessizlik başladı" kararı için gereken süre
        #   → 0.6 sn = konuşma bittiğinde hızlıca algıla
        # phrase_threshold: Ses başlangıcı olarak kabul için min süre
        #   → 0.4 sn = çok kısa tıklama seslerini filtrele
        self.recognizer.pause_threshold = 1.4
        self.recognizer.phrase_threshold = 0.4
        self.recognizer.non_speaking_duration = 0.6

        # ── API Anahtarları ──
        self._groq_api_key = os.getenv("GROQ_API_KEY")
        self._gemini_api_key = os.getenv("GEMINI_API_KEY")

        # ── Groq Client (tekrar tekrar oluşturmamak için cache) ──
        self._groq_client: Optional[Groq] = None
        if _HAS_GROQ and self._groq_api_key:
            try:
                self._groq_client = Groq(api_key=self._groq_api_key)
                logger.info("[STT] Groq Whisper motoru hazır.")
            except Exception as e:
                logger.warning(f"[STT] Groq client oluşturulamadı: {e}")

        # Beep için mixer başlatma
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=1)

        # Hangi motor aktif olduğunu logla
        if self._groq_client:
            print("[STT] Motor: Groq Whisper Large-v3-Turbo + AI Polisher (Typeless Modu)")
        else:
            print("[STT] Motor: Google Web Speech API (Fallback -- Groq API anahtari bulunamadi)")

    # ─────────────────────────────────────────────────────────────────────────
    # BEEP SES EFEKTİ
    # ─────────────────────────────────────────────────────────────────────────

    def _play_beep(self):
        """Dı-dıt sesi: İki kısa bip sesi üretir ve çalar."""
        try:
            sample_rate = 44100
            def generate_tone(freq, duration_ms):
                num_samples = int(sample_rate * (duration_ms / 1000.0))
                buf = array.array('h', [0] * num_samples)
                for i in range(num_samples):
                    t = float(i) / sample_rate
                    buf[i] = int(16383 * math.sin(2 * math.pi * freq * t))
                return pygame.mixer.Sound(buffer=buf)

            beep1 = generate_tone(1000, 80)
            beep2 = generate_tone(1200, 80)

            channel = beep1.play()
            while channel.get_busy(): pygame.time.Clock().tick(10)
            pygame.time.delay(30)
            channel = beep2.play()
            while channel.get_busy(): pygame.time.Clock().tick(10)
        except Exception as e:
            print(f"[SESLİ GERİ BİLDİRİM HATASI]: Beep çalınamadı: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # GROQ WHISPER TRANSKRİPSİYON
    # ─────────────────────────────────────────────────────────────────────────

    def _transcribe_with_whisper(self, audio: sr.AudioData) -> Optional[str]:
        """
        Ses verisini Groq Whisper API ile transkripsiyon yapar.
        Döndürülen metin ham transkripsiyon — henüz parlatılmamış.
        """
        if not self._groq_client:
            return None

        try:
            # AudioData → WAV bytes (bellekte, disk I/O yok)
            wav_bytes = audio.get_wav_data(convert_rate=16000, convert_width=2)
            wav_buffer = io.BytesIO(wav_bytes)
            wav_buffer.name = "audio.wav"

            transcription = self._groq_client.audio.transcriptions.create(
                file=("audio.wav", wav_buffer),
                model="whisper-large-v3-turbo",
                language="tr",
                response_format="text",
                temperature=0.0,
            )

            # API text formatında direkt string döndürür
            text = transcription.strip() if isinstance(transcription, str) else str(transcription).strip()
            return text if text else None

        except Exception as e:
            logger.warning(f"[STT_WHISPER] Groq Whisper hatası: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # AI POLISHER (TYPELESS MODU)
    # ─────────────────────────────────────────────────────────────────────────

    def _polish_text(self, raw_text: str) -> str:
        """
        Ham transkripsiyon metnini AI ile parlatır.
        Kısa komutlarda (≤5 kelime) polisher atlanır — gereksiz gecikmeyi önler.
        """
        if not raw_text:
            return raw_text

        # Kısa ve temiz metinlerde polisher'a gerek yok
        word_count = len(raw_text.split())
        if word_count <= 5:
            return self._basic_noise_filter(raw_text)

        # Öncelik: Groq LLM → Gemini → Temel Filtre
        if self._groq_api_key:
            polished = _polish_with_groq(raw_text, self._groq_api_key)
            if polished:
                return polished

        if _HAS_GEMINI and self._gemini_api_key:
            polished = _polish_with_gemini(raw_text, self._gemini_api_key)
            if polished:
                return polished

        # En kötü senaryo: temel filtre
        return self._basic_noise_filter(raw_text)

    def _basic_noise_filter(self, text: str) -> str:
        """Temel dolgu/gürültü filtresi — AI yoksa devreye girer."""
        if not text:
            return text

        clean = text.strip()
        noise_words = ["ıı", "öö", "ee", "ııı", "ööö", "eee", "şey", "yani", "hıh", "ehm", "hım"]

        # Sadece gürültüden ibaret mi?
        if clean.lower() in noise_words or len(clean) < 2:
            return ""

        # Gürültü kelimelerini temizle
        for nw in noise_words:
            clean = clean.replace(f" {nw} ", " ").replace(f" {nw}", "").replace(f"{nw} ", "")

        # Fazla boşlukları temizle
        clean = " ".join(clean.split())
        return clean.strip()

    # ─────────────────────────────────────────────────────────────────────────
    # GOOGLE FALLBACK
    # ─────────────────────────────────────────────────────────────────────────

    def _transcribe_with_google(self, audio: sr.AudioData) -> Optional[str]:
        """Google Web Speech API fallback — Groq başarısız olursa kullanılır."""
        try:
            text = self.recognizer.recognize_google(audio, language="tr-TR")
            return text.strip() if text else None
        except (sr.UnknownValueError, sr.RequestError):
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # ANA DİNLEME MOTORU
    # ─────────────────────────────────────────────────────────────────────────

    def _do_listen(self, pause_threshold: float, phrase_time_limit: int,
                   timeout: int = None, on_speech_end=None, use_polisher: bool = True) -> str:
        """
        İç dinleme motoru — Typeless Grade (V13.1)

        Pipeline:
            0. Mute kontrolü — yazılı moddayken mikrofon AÇILMAZ
            1. Mikrofonu aç, ortam gürültüsüne adapte ol
            2. pause_threshold süresince sessizlik algılanınca kaydı bitir
            3. Groq Whisper ile transkripsiyon (fallback: Google)
            4. AI Polisher ile metin parlatma (uzun metinlerde)
            5. Temiz, noktalamalı Türkçe metin döndür
        """
        # [V13.1] Yazılı moddayken ses algılama tamamen devre dışı
        if self._muted:
            return None

        try:
            with sr.Microphone() as source:
                # Ortam gürültüsüne hızlı adaptasyon (0.5 sn yeterli)
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

                # Bu oturum için pause_threshold'u geçici ayarla
                old_pause = self.recognizer.pause_threshold
                self.recognizer.pause_threshold = pause_threshold

                # ── Dinleme ──
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit
                )

                # Kayıt bitti — anında geri bildirim ver
                if on_speech_end:
                    on_speech_end()

                # pause_threshold'u eski haline döndür
                self.recognizer.pause_threshold = old_pause

                # [V13.1 FIX] Eğer dinleme işlemi sırasında mute edildiysek (yazılı moda geçildiyse)
                # sesi işleme, hemen iptal et.
                if self._muted:
                    return None

                # ── Transkripsiyon Pipeline ──
                raw_text = None

                # 1. Groq Whisper ile dene
                if self._groq_client:
                    raw_text = self._transcribe_with_whisper(audio)
                    if raw_text:
                        logger.debug(f"[WHISPER_RAW] {raw_text}")

                # 2. Whisper başarısızsa Google fallback
                if not raw_text:
                    raw_text = self._transcribe_with_google(audio)
                    if raw_text:
                        logger.debug(f"[GOOGLE_RAW] {raw_text}")

                # Hiçbir motor sonuç vermedi
                if not raw_text:
                    return None

                # ── Noise Shield: Sadece gürültüden ibaret mi? ──
                clean_check = raw_text.lower().strip()
                noise_only = ["ıı", "öö", "ee", "ııı", "ööö", "eee", "hıh", "ehm", "hım"]
                if clean_check in noise_only or len(clean_check) < 2:
                    print(f"[NOISE_SHIELD] Gereksiz girdi reddedildi: '{raw_text}'")
                    return None

                # ── AI Polisher (Typeless Modu) ──
                if use_polisher:
                    final_text = self._polish_text(raw_text)
                else:
                    final_text = self._basic_noise_filter(raw_text)

                if not final_text or not final_text.strip():
                    return None

                final_text = final_text.strip()
                
                # [V13.1 FIX] İşlemler (API vs.) sürerken yazılı moda geçilmiş olabilir
                # En son aşamada tekrar kontrol et, kapalıysa çöpe at.
                if self._muted:
                    return None
                    
                print(f"Sen (Sesli): {final_text}")
                return final_text

        except (sr.UnknownValueError, sr.WaitTimeoutError):
            return None
        except Exception as e:
            print(f"[STT_OMEGA]: {str(e)}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # RESET
    # ─────────────────────────────────────────────────────────────────────────

    def reset_recognizer(self):
        """Kritik reset: Recognizer nesnesini tamamen sıfırlar."""
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 4000
        self.recognizer.pause_threshold = 1.4
        self.recognizer.phrase_threshold = 0.4
        self.recognizer.non_speaking_duration = 0.6

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC API — Engine tarafından çağrılır
    # ─────────────────────────────────────────────────────────────────────────

    def listen(self, timeout: int = 5, on_speech_end=None) -> str:
        """
        Normal komut modu.

        Zamanlama:
            pause_threshold  = 1.4 sn → Konuşma içi duraklama toleransı
            phrase_time_limit = 20 sn → Tek seferde max konuşma süresi
            Polisher          = Kısa komutlarda atlanır, uzunlarda devreye girer
        """
        return self._do_listen(
            pause_threshold=1.4,
            phrase_time_limit=20,
            timeout=timeout,
            on_speech_end=on_speech_end,
            use_polisher=True
        )

    def listen_dictation(self, on_speech_end=None) -> str:
        """
        Dikte modu — Uzun mesajlar, WhatsApp, not yazma.

        Zamanlama:
            pause_threshold  = 2.5 sn → Uzun düşünme duraksamalarına sabır
            phrase_time_limit = 60 sn → 1 dakikaya kadar kesintisiz konuşma
            Polisher          = Tam kapasite (dolgu temizleme + noktalama)
        """
        print("\n[J.A.R.V.I.S. DİKTE MODU] Mesajı tamamen söyleyin, bitince bekleyin...")
        return self._do_listen(
            pause_threshold=2.5,
            phrase_time_limit=60,
            on_speech_end=on_speech_end,
            use_polisher=True
        )
