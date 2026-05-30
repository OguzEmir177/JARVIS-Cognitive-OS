import pygame
import threading
import asyncio
import os
import tempfile
import edge_tts
import logging

# [V15.5] Çeviri önbelleği — aynı cümle bir kez çevrilir, sonraki çağrılarda anında döner
_TRANSLATION_CACHE: dict = {}

class TextToSpeech:
    def __init__(self):
        # Sesi oynatmak için pygame başlatıyoruz
        pygame.mixer.init()
        
    def speak(self, text: str):
        # Her halükarda sesi RyanNeural (İngiliz Jarvis) yapacağız
        voice = "en-GB-RyanNeural"
        
        # Daemon thread kullanıyoruz
        thread = threading.Thread(target=self._play_audio, args=(text, voice), daemon=True)
        thread.start()
        
    def _play_audio(self, text: str, voice: str):
        temp_path = None
        try:
            # RyanNeural için default hız ve perde (karizmatik)
            rate = "+0%"
            pitch = "+0Hz"
            
            # Geçici mp3 dosyası oluştur
            fp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            fp.close()
            temp_path = fp.name
            
            # Edge-TTS Asenkron Çalıştırma ve Çeviri
            async def generate_speech():
                global _TRANSLATION_CACHE
                speech_text = text

                # ── Çeviri Önbellği + 429 Retry ──────────────────────────
                if text in _TRANSLATION_CACHE:
                    speech_text = _TRANSLATION_CACHE[text]
                else:
                    import urllib.request
                    import urllib.parse
                    import urllib.error
                    import json as _json
                    import time as _time

                    def _do_translate() -> str:
                        encoded = urllib.parse.quote(text)
                        url = (
                            "https://translate.googleapis.com/translate_a/single"
                            f"?client=gtx&sl=tr&tl=en&dt=t&q={encoded}"
                        )
                        req = urllib.request.Request(
                            url, headers={"User-Agent": "Mozilla/5.0"}
                        )
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            raw = resp.read().decode("utf-8")
                        data = _json.loads(raw)
                        return "".join(part[0] for part in data[0] if part[0])

                    try:
                        translated = _do_translate()
                        if translated:
                            _TRANSLATION_CACHE[text] = translated
                            speech_text = translated
                    except urllib.error.HTTPError as e:
                        if e.code == 429:
                            # Rate limit — 3 saniye bekle ve 2 kez dene
                            for retry_count in range(2):
                                # logging.warning(f"TTS: 429 Rate Limit (Deneme {retry_count+1}), 3s bekleniyor...")
                                await asyncio.sleep(3)
                                try:
                                    translated = _do_translate()
                                    if translated:
                                        _TRANSLATION_CACHE[text] = translated
                                        speech_text = translated
                                        break
                                except Exception:
                                    continue
                        else:
                            pass # logging.warning(f"TTS Çeviri HTTP hatası ({e.code}): {e} — orijinal metin kullanılıyor")
                    except Exception as e:
                        pass # logging.warning(f"TTS Çeviri hatası: {e} — orijinal metin kullanılıyor")
                # ─────────────────────────────────────────────────────────
                    
                retries = 3
                for attempt in range(retries):
                    try:
                        communicate = edge_tts.Communicate(speech_text, voice, rate=rate, pitch=pitch)
                        # asyncio.wait_for ile her deneme için 15 sn timeout ekle (uzun cümleler için)
                        await asyncio.wait_for(communicate.save(temp_path), timeout=15)
                        return True
                    except Exception as e:
                        if attempt < retries - 1:
                            # print(f"[SES_YENİDEN_DENEME] Deneme {attempt+1} başarısız: {e}. Tekrar deneniyor...")
                            await asyncio.sleep(0.5)
                        else:
                            raise e
                return False
                
            asyncio.run(generate_speech())
            
            # Oluşturulan dosyayı Pygame ile oynat
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()
            else:
                raise Exception("Ses dosyası oluşturulamadı.")
            
            # Ses bitene kadar bekle (Sadece bu thread donar, ana GUI donmaz)
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
                
        except Exception as e:
            # print(f"\n[SES MODÜLÜ HATASI]: edge-tts ile konuşma oluşturulamadı: {str(e)}")
            # [V8.2 FIXED] pyttsx3 fallback devre dışı bırakıldı. 
            # asyncio loop çakışması ve "run loop already started" hatalarını önlemek için sessizce devam ediliyor.
            # logging.warning(f"TTS başarısız (Internet/DNS?), sessizce devam ediliyor. Detay: {e}")
            return
            
        finally:
            pygame.mixer.music.unload()
            # Çöpleri temizle
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
