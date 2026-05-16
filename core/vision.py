import os
import pyautogui
import logging

logger = logging.getLogger("JARVIS.Vision")

class JarvisVision:
    """
    [V9.0] LOKAL VİZYON MOTORU (Sıfır API, Sıfır Kota)
    Ekrandaki metinleri (OCR) ve aktif pencereyi okur.
    """
    ERROR_SENTINEL = "VISION_HATASI"

    def __init__(self):
        self.tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    def analyze_screen(self) -> str:
        """Ekrandaki yazıları ve aktif pencereyi lokal olarak okur."""
        try:
            # 1. Aktif Pencereyi Bul
            active_window = "Bilinmeyen Pencere"
            try:
                import pygetwindow as gw
                win = gw.getActiveWindow()
                if win: active_window = win.title
            except:
                pass

            # 2. Ekrandaki Yazıları Oku (OCR)
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
                
                screenshot = pyautogui.screenshot()
                # Ekrandaki metni çıkar
                text = pytesseract.image_to_string(screenshot, lang="tur+eng")
                
                # Boşlukları temizle ve ilk 2000 karakteri al (LLM'i boğmamak için)
                clean_text = " ".join(text.split())[:2000]
                
                if not clean_text:
                    return f"Aktif Pencere: '{active_window}'. Ekranda okunabilir bir metin bulunamadı."
                    
                return f"Aktif Pencere: '{active_window}'.\nEkrandaki Metinler: {clean_text}"
                
            except FileNotFoundError:
                return f"Aktif Pencere: '{active_window}'. (Not: Ekrandaki yazıları okuyabilmem için bilgisayarınıza 'Tesseract OCR' kurmanız gerekmektedir)."
            except Exception as e:
                logger.error(f"OCR Hatası: {e}")
                return f"Aktif Pencere: '{active_window}'. Metin okuma başarısız oldu."
                
        except Exception as e:
            logger.error(f"[VISION] Lokal analiz başarısız: {e}")
            return f"Lokal ekran analizi hatası: {e}"

    def analyze_screen_for_context(self, context_prompt: str) -> str:
        return self.analyze_screen()
