import speech_recognition as sr
import pygame
import math
import array

class SpeechToText:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 4000 # Gürültü kalkanı (Ortam gürültüsüne göre ayarlanacak)
        self.recognizer.dynamic_energy_threshold = True
        
        # Sabır ve Bütünlük Güncellemesi (Patience Logic)
        self.recognizer.pause_threshold = 1.2   # Cümle içi duraklamalarda hemen kesmesin (1.2 sn uygun)
        self.recognizer.phrase_threshold = 0.5  # Konuşma başlangıcını netleştirmek için 0.5 sn
        self.recognizer.non_speaking_duration = 0.5 
        
        # Beep için mixer başlatma (zaten tts'te yapılıyor ama burada da garantiye alalım)
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=1)

    def _play_beep(self):
        """Dı-dıt sesi: İki kısa bip sesi üretir ve çalar."""
        try:
            sample_rate = 44100
            def generate_tone(freq, duration_ms):
                num_samples = int(sample_rate * (duration_ms / 1000.0))
                buf = array.array('h', [0] * num_samples)
                for i in range(num_samples):
                    t = float(i) / sample_rate
                    # Sine wave at freq
                    buf[i] = int(16383 * math.sin(2 * math.pi * freq * t))
                return pygame.mixer.Sound(buffer=buf)

            # İki ardışık ses (Dı-dıt)
            beep1 = generate_tone(1000, 80)
            beep2 = generate_tone(1200, 80)
            
            channel = beep1.play()
            while channel.get_busy(): pygame.time.Clock().tick(10)
            
            # Kısa sessizlik
            pygame.time.delay(30)
            
            channel = beep2.play()
            while channel.get_busy(): pygame.time.Clock().tick(10)
        except Exception as e:
            print(f"[SESLİ GERİ BİLDİRİM HATASI]: Beep çalınamadı: {e}")

    def _do_listen(self, pause_threshold: float, phrase_time_limit: int, timeout: int = None, on_speech_end=None) -> str:
        """İç dinleme motoru. (Protocol Omega - v5.8)"""
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
                old_pause = self.recognizer.pause_threshold
                self.recognizer.pause_threshold = pause_threshold
                
                # Dinleme (Zaman aşımı kontrolü)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                
                # [V5.10] ANLIK GERİ BİLDİRİM: Kayıt bittiği an (cloud öncesi) tetikle
                if on_speech_end:
                    on_speech_end()
                    
                self.recognizer.pause_threshold = old_pause  
                
                # Sesi Google'a gönder (Zaman aşımı ile)
                # recognize_google içinde timeout desteği kısıtlıdır, bu yüzden dış süzgeç kullanıyoruz
                text = self.recognizer.recognize_google(audio, language="tr-TR")
                
                # --- [V5.8] NOISE SHIELD & FILLER FILTER ---
                if not text: return None
                
                # Çok kısa (1-2 karakter) veya anlamsız gürültüleri filtrele
                clean_text = text.lower().strip()
                noise_words = ["ıı", "öö", "ee", "ııı", "ööö", "eee", "şey", "yani", "hıh", "ehm"]
                
                # Eğer girdi sadece gürültü kelimelerinden oluşuyorsa reddet
                if clean_text in noise_words or len(clean_text) < 2:
                    print(f"[NOISE_SHIELD] Gereksiz girdi reddedildi: '{text}'")
                    return None
                
                # Kelime listesindeki gürültüleri metinden temizle (opsiyonel ama daha temiz olur)
                for nw in noise_words:
                    clean_text = clean_text.replace(f" {nw} ", " ").replace(f" {nw}", "").replace(f"{nw} ", "")
                # -------------------------------------------
                
                if text and text.strip():
                    print(f"Sen (Sesli): {text}")
                return text.strip()
                
        except (sr.UnknownValueError, sr.WaitTimeoutError):
            return None
        except Exception as e:
            # Kritik olmayan hatalarda sessiz kal, log bas
            print(f"[STT_OMEGA]: {str(e)}")
            return None

    def reset_recognizer(self):
        """Kritik reset: Nesne tamamen sıfırlanır."""
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 4000
        self.recognizer.pause_threshold = 1.2

    def listen(self, timeout: int = 5, on_speech_end=None) -> str:
        """Normal mod: 1.2 sn sessizlikte cümleyi kapatır, max 15 sn."""
        return self._do_listen(pause_threshold=1.2, phrase_time_limit=15, timeout=timeout, on_speech_end=on_speech_end)

    def listen_dictation(self, on_speech_end=None) -> str:
        """Dikte modu: 2 sn sessizlikte kapatır, max 45 sn. WhatsApp mesajları için."""
        print("\n[J.A.R.V.I.S. DİKTE MODU] Mesajı tamamen söyleyin, bitince bekleyin...")
        return self._do_listen(pause_threshold=2.0, phrase_time_limit=45, on_speech_end=on_speech_end)
