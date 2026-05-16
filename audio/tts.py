import pygame
import threading
import asyncio
import os
import tempfile
import edge_tts
import logging

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
                speech_text = text
                # Türkçeyi İngilizceye çevir (Ryan'ın okuyabilmesi için)
                try:
                    from googletrans import Translator
                    translator = Translator()
                    # Googletrans 4.x asenkron veya senkron olabilir, garantilemek için try/await
                    tr_result = translator.translate(text, src='tr', dest='en')
                    if hasattr(tr_result, "__await__"):
                        tr_result = await tr_result
                    if tr_result and tr_result.text:
                        speech_text = tr_result.text
                except Exception as e:
                    logging.warning(f"TTS Çeviri hatası: {e}")
                    pass # Çeviri çökerse orijinal metinle devam et
                    
                retries = 3
                for attempt in range(retries):
                    try:
                        communicate = edge_tts.Communicate(speech_text, voice, rate=rate, pitch=pitch)
                        # asyncio.wait_for ile her deneme için 15 sn timeout ekle (uzun cümleler için)
                        await asyncio.wait_for(communicate.save(temp_path), timeout=15)
                        return True
                    except Exception as e:
                        if attempt < retries - 1:
                            print(f"[SES_YENİDEN_DENEME] Deneme {attempt+1} başarısız: {e}. Tekrar deneniyor...")
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
            print(f"\n[SES MODÜLÜ HATASI]: edge-tts ile konuşma oluşturulamadı: {str(e)}")
            # [V8.2 FIXED] pyttsx3 fallback devre dışı bırakıldı. 
            # asyncio loop çakışması ve "run loop already started" hatalarını önlemek için sessizce devam ediliyor.
            logging.warning(f"TTS başarısız (Internet/DNS?), sessizce devam ediliyor. Detay: {e}")
            return
            
        finally:
            pygame.mixer.music.unload()
            # Çöpleri temizle
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
