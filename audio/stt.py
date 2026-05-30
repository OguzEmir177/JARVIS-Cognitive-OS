"""
[V13.0] J.A.R.V.I.S. — Typeless-Grade Speech-to-Text Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Architecture:
    1. Microphone recording  → speech_recognition (same PyAudio backend)
    2. Transcription         → Groq Whisper Large-v3-Turbo (ultra-fast, flawless Turkish)
    3. AI Polisher           → Groq LLM or Gemini (filler/noise cleanup + punctuation)
    4. Fallback              → Google Web Speech API (if internet/API cuts out)

Timing Philosophy:
    - Be PATIENT with pauses INSIDE speech (pause_threshold)
    - Cut and process QUICKLY when speech ENDS (non_speaking_duration)
    - Prevent infinite wait with phrase_time_limit
"""

import speech_recognition as sr
import pygame
import math
import array
import struct
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
    logger.warning("[STT] groq package not found — Whisper disabled, Google fallback active.")

# ── Gemini SDK (AI Polisher alternatifi) ──
_HAS_GEMINI = False
try:
    import google.generativeai as genai
    _HAS_GEMINI = True
except ImportError:
    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AI POLISHER — The Secret of Typeless
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
    """Polishes raw transcription text using Groq LLM."""
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
        # LLM sometimes wraps in quotes, clean up
        if polished.startswith('"') and polished.endswith('"'):
            polished = polished[1:-1]
        if polished.startswith("'") and polished.endswith("'"):
            polished = polished[1:-1]
        return polished
    except Exception as e:
        logger.warning(f"[AI_POLISHER] Groq LLM polishing error: {e}")
        return None


def _polish_with_gemini(raw_text: str, api_key: str) -> Optional[str]:
    """Polishes raw transcription text using Gemini (Groq backup)."""
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
        logger.warning(f"[AI_POLISHER] Gemini polishing error: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WHISPER HALLUCINATION SHIELD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Known ghost texts produced by Whisper in silence/noise.
# Checked after converting to lowercase.
_WHISPER_HALLUCINATION_PATTERNS = [
    "altyazı m.k.",
    "altyazı m.k",
    "altyazılar m.k.",
    "alt yazı m.k.",
    "alt yazı m.k",
    "altyazı mk",
    "alt yazı: m. k.",
    "alt yazı: m.k.",
    "altyazı",
    "alt yazı",
    "abone ol",
    "abone olun",
    "like atın",
    "beğenmeyi unutmayın",
    "teşekkürler",
    "teşekkür ederim",
    "izlediğiniz için teşekkürler",
    "thanks for watching",
    "thank you for watching",
    "subscribe",
    "like and subscribe",
    "...",
    ".",
    ",",
    "!",
    "?",
]


def _is_whisper_hallucination(text: str) -> bool:
    """
    Detects ghost texts produced by Whisper in silence.
    Performs exact or partial match checks.
    """
    if not text:
        return True
    
    cleaned = text.lower().strip().rstrip('.').strip()
    
    # Empty or very short (1-2 chars) → likely noise
    if len(cleaned) < 2:
        return True
    
    # Consists only of punctuation?
    if all(c in '.,!?;:-…\'"()[] ' for c in cleaned):
        return True
    
    # Exact match with known hallucination patterns
    for pattern in _WHISPER_HALLUCINATION_PATTERNS:
        if cleaned == pattern.lower().rstrip('.'):
            return True
    
    # Short texts (≤4 words) CONTAINING "altyazı" or "alt yazı"
    if len(cleaned.split()) <= 4:
        if "altyazı" in cleaned or "alt yazı" in cleaned:
            return True
    
    return False


def _calculate_audio_rms(audio: sr.AudioData) -> float:
    """
    Calculates the RMS (Root Mean Square) value of audio data.
    This value measures the actual "loudness" of the sound.
    Silence ≈ 0-300, speech ≈ 500-10000+
    """
    try:
        raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
        # 16-bit signed integer samples
        num_samples = len(raw_data) // 2
        if num_samples == 0:
            return 0.0
        samples = struct.unpack(f'<{num_samples}h', raw_data)
        # RMS hesapla
        sum_squares = sum(s * s for s in samples)
        rms = math.sqrt(sum_squares / num_samples)
        return rms
    except Exception as e:
        logger.warning(f"[RMS] Could not calculate audio level: {e}")
        return 9999.0  # Pass on error (better than false positive)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN STT CLASS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SpeechToText:
    """
    Typeless-Grade Speech-to-Text Engine.

    Pipeline:
        Microphone → WAV bytes → Groq Whisper → AI Polisher → Clean Text
        (Fallback: Microphone → Google Web Speech API → Basic Filter → Text)
    """

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 4000

        # ── [V13.1] Mute Flag — Completely disables microphone in text mode ──
        self._muted: bool = False

        # ── Timing Philosophy ──
        # pause_threshold: How many seconds to tolerate pauses INSIDE speech
        #   → 1.4s = don't cut immediately during thinking pauses
        # non_speaking_duration: Time needed to decide "silence has started"
        #   → 0.6s = detect end of speech quickly
        # phrase_threshold: Min duration to accept as start of speech
        #   → 0.4s = filter out very short click sounds
        self.recognizer.pause_threshold = 1.4
        self.recognizer.phrase_threshold = 0.4
        self.recognizer.non_speaking_duration = 0.6

        # ── API Keys ──
        self._groq_api_key = os.getenv("GROQ_API_KEY")
        self._gemini_api_key = os.getenv("GEMINI_API_KEY")

        # ── Groq Client (cached to avoid repeated instantiation) ──
        self._groq_client: Optional[Groq] = None
        if _HAS_GROQ and self._groq_api_key:
            try:
                self._groq_client = Groq(api_key=self._groq_api_key)
                logger.info("[STT] Groq Whisper engine ready.")
            except Exception as e:
                logger.warning(f"[STT] Could not create Groq client: {e}")

        # Initialize mixer for beep sound
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=1)

        # Hangi motor aktif olduğunu logla
        if self._groq_client:
            print("[STT] Engine: Groq Whisper Large-v3-Turbo + AI Polisher (Typeless Mode)")
        else:
            print("[STT] Engine: Google Web Speech API (Fallback -- Groq API key not found)")

    # ─────────────────────────────────────────────────────────────────────────
    # BEEP SOUND EFFECT
    # ─────────────────────────────────────────────────────────────────────────

    def _play_beep(self):
        """Di-dit sound: Generates and plays two short beep tones."""
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
            print(f"[AUDIO FEEDBACK ERROR]: Beep could not play: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # GROQ WHISPER TRANSCRIPTION
    # ─────────────────────────────────────────────────────────────────────────

    def _transcribe_with_whisper(self, audio: sr.AudioData) -> Optional[str]:
        """
        Transcribes audio data using the Groq Whisper API.
        The returned text is raw transcription — not yet polished.
        """
        if not self._groq_client:
            return None

        try:
            # AudioData → WAV bytes (in memory, no disk I/O)
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

            # API returns direct string in text format
            text = transcription.strip() if isinstance(transcription, str) else str(transcription).strip()
            return text if text else None

        except Exception as e:
            logger.warning(f"[STT_WHISPER] Groq Whisper error: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # AI POLISHER (TYPELESS MODE)
    # ─────────────────────────────────────────────────────────────────────────

    def _polish_text(self, raw_text: str) -> str:
        """
        Polishes raw transcription text with AI.
        Polisher is skipped for short commands (≤5 words) — prevents unnecessary delay.
        """
        if not raw_text:
            return raw_text

        # No need for polisher on short, clean texts
        word_count = len(raw_text.split())
        if word_count <= 5:
            return self._basic_noise_filter(raw_text)

        # Priority: Groq LLM → Gemini → Basic Filter
        if self._groq_api_key:
            polished = _polish_with_groq(raw_text, self._groq_api_key)
            if polished:
                return polished

        if _HAS_GEMINI and self._gemini_api_key:
            polished = _polish_with_gemini(raw_text, self._gemini_api_key)
            if polished:
                return polished

        # Worst case: basic filter
        return self._basic_noise_filter(raw_text)

    def _basic_noise_filter(self, text: str) -> str:
        """Basic filler/noise filter — activates when AI is unavailable."""
        if not text:
            return text

        clean = text.strip()
        noise_words = ["ıı", "öö", "ee", "ııı", "ööö", "eee", "şey", "yani", "hıh", "ehm", "hım"]

        # Consists only of noise?
        if clean.lower() in noise_words or len(clean) < 2:
            return ""

        # Remove noise words
        for nw in noise_words:
            clean = clean.replace(f" {nw} ", " ").replace(f" {nw}", "").replace(f"{nw} ", "")

        # Remove extra spaces
        clean = " ".join(clean.split())
        return clean.strip()

    # ─────────────────────────────────────────────────────────────────────────
    # GOOGLE FALLBACK
    # ─────────────────────────────────────────────────────────────────────────

    def _transcribe_with_google(self, audio: sr.AudioData) -> Optional[str]:
        """Google Web Speech API fallback — used when Groq fails."""
        try:
            text = self.recognizer.recognize_google(audio, language="tr-TR")
            return text.strip() if text else None
        except (sr.UnknownValueError, sr.RequestError):
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN LISTENING ENGINE
    # ─────────────────────────────────────────────────────────────────────────

    def _do_listen(self, pause_threshold: float, phrase_time_limit: int,
                   timeout: int = None, on_speech_end=None, use_polisher: bool = True) -> str:
        """
        Internal listening engine — Typeless Grade (V13.1)

        Pipeline:
            0. Mute check — microphone does NOT open in text mode
            1. Open microphone, adapt to ambient noise
            2. Stop recording when silence detected for pause_threshold seconds
            3. Transcription with Groq Whisper (fallback: Google)
            4. Text polishing with AI Polisher (for long texts)
            5. Return clean, punctuated text
        """
        # [V13.1] Audio detection completely disabled in text mode
        if self._muted:
            return None

        try:
            with sr.Microphone() as source:
                # Quick adaptation to ambient noise (0.5s is enough)
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

                # Temporarily set pause_threshold for this session
                old_pause = self.recognizer.pause_threshold
                self.recognizer.pause_threshold = pause_threshold

                # ── Listening ──
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit
                )

                # Recording done — give immediate feedback
                if on_speech_end:
                    on_speech_end()

                # Restore pause_threshold to previous value
                self.recognizer.pause_threshold = old_pause

                # [V13.1 FIX] If muted during listening (switched to text mode),
                # discard audio immediately.
                if self._muted:
                    return None

                # ── [V13.2] RMS Energy Check — Don't send silent audio to API ──
                audio_rms = _calculate_audio_rms(audio)
                logger.debug(f"[RMS] Audio level: {audio_rms:.0f}")
                
                # RMS < 350 → microphone is open but nobody is speaking
                # This threshold catches silence in most environments.
                # Can be adjusted via self.min_rms_threshold if needed.
                _MIN_RMS = 350
                if audio_rms < _MIN_RMS:
                    logger.debug(f"[RMS_SHIELD] Audio too low ({audio_rms:.0f} < {_MIN_RMS}), skipping.")
                    return None

                # ── Transcription Pipeline ──
                raw_text = None

                # 1. Try with Groq Whisper
                if self._groq_client:
                    raw_text = self._transcribe_with_whisper(audio)
                    if raw_text:
                        logger.debug(f"[WHISPER_RAW] {raw_text}")

                # 2. Google fallback if Whisper fails
                if not raw_text:
                    raw_text = self._transcribe_with_google(audio)
                    if raw_text:
                        logger.debug(f"[GOOGLE_RAW] {raw_text}")

                # No engine returned a result
                if not raw_text:
                    return None

                # ── [V13.2] Whisper Hallucination Shield ──
                if _is_whisper_hallucination(raw_text):
                    print(f"[HALLUCINATION_SHIELD] Whisper ghost text rejected: '{raw_text}'")
                    return None

                # ── Noise Shield: Consists only of noise? ──
                clean_check = raw_text.lower().strip()
                noise_only = ["ıı", "öö", "ee", "ııı", "ööö", "eee", "hıh", "ehm", "hım"]
                if clean_check in noise_only or len(clean_check) < 2:
                    print(f"[NOISE_SHIELD] Unnecessary input rejected: '{raw_text}'")
                    return None

                # ── AI Polisher (Typeless Mode) ──
                if use_polisher:
                    final_text = self._polish_text(raw_text)
                else:
                    final_text = self._basic_noise_filter(raw_text)

                if not final_text or not final_text.strip():
                    return None

                final_text = final_text.strip()
                
                # [V13.1 FIX] Text mode may have been activated while API calls were running.
                # Check again at the final stage; if muted, discard.
                if self._muted:
                    return None
                    
                print(f"You (Voice): {final_text}")
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
        """Critical reset: Completely resets the Recognizer object."""
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 4000
        self.recognizer.pause_threshold = 1.4
        self.recognizer.phrase_threshold = 0.4
        self.recognizer.non_speaking_duration = 0.6

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC API — Called by Engine
    # ─────────────────────────────────────────────────────────────────────────

    def listen(self, timeout: int = 5, on_speech_end=None) -> str:
        """
        Normal command mode.

        Timing:
            pause_threshold   = 1.4s → Tolerance for pauses within speech
            phrase_time_limit = 20s  → Max speech duration in one take
            Polisher          = Skipped for short commands, activated for longer ones
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
        Dictation mode — Long messages, WhatsApp, note-taking.

        Timing:
            pause_threshold   = 2.5s → Patient with long thinking pauses
            phrase_time_limit = 60s  → Up to 1 minute of uninterrupted speech
            Polisher          = Full capacity (filler cleanup + punctuation)
        """
        print("\n[J.A.R.V.I.S. DICTATION MODE] Speak the full message, then wait...")
        return self._do_listen(
            pause_threshold=2.5,
            phrase_time_limit=60,
            on_speech_end=on_speech_end,
            use_polisher=True
        )
