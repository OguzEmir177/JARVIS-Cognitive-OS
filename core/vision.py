import os
import pyautogui
import logging

logger = logging.getLogger("JARVIS.Vision")

class JarvisVision:
    """[V9.0] LOCAL VISION ENGINE (Zero API, Zero Quota)
    Reads on-screen text (OCR) and the active window."""
    ERROR_SENTINEL = "VISION_HATASI"

    def __init__(self):
        self.tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    def analyze_screen(self) -> str:
        """It reads the text on the screen and the active window locally."""
        try:
            # 1. Aktif Pencereyi Bul
            active_window = "Bilinmeyen Pencere"
            try:
                import pygetwindow as gw
                win = gw.getActiveWindow()
                if win: active_window = win.title
            except:
                pass

            # 2. Read On Screen (OCR)
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
                
                screenshot = pyautogui.screenshot()
                # Extract text from the screen
                text = pytesseract.image_to_string(screenshot, lang="tur+eng")
                
                # Clear spaces and get first 2000 characters (to avoid overwhelming LLM)
                clean_text = " ".join(text.split())[:2000]
                
                if not clean_text:
                    return f"Active Window: '{active_window}'. No readable text was found on the screen."
                    
                return f"Aktif Pencere: '{active_window}'.\nEkrandaki Metinler: {clean_text}"
                
            except FileNotFoundError:
                return f"Active Window: '{active_window}'. (Note: In order to read the text on the screen, you need to install 'Tesseract OCR' on your computer)."
            except Exception as e:
                logger.error(f"OCR Error: {e}")
                return f"Active Window: '{active_window}'. Text reading failed."
                
        except Exception as e:
            logger.error(f"[VISION] Local analysis failed: {e}")
            return f"Local display analysis error: {e}"

    def analyze_screen_for_context(self, context_prompt: str) -> str:
        return self.analyze_screen()
