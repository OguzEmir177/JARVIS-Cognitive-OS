import asyncio
import logging
import queue
from typing import Callable, Optional

logger = logging.getLogger("JARVIS.IOBridge")


class IOBridge:
    """
    J.A.R.V.I.S. v2 I/O Arayüzü  [10/10 Upgrade]

    Yeni özellikler:
    + display_chart_card()      → Matplotlib grafik içeren kart gönderir
    + update_vision_status()    → Vision modülünün durumunu GUI'ye bildirir
    + set_memory_notify_callback() → Hafıza kaydında GUI toast tetikler
    """

    def __init__(self, config=None):
        self.config = config
        self._text_mode: bool = False
        self.text_input_queue: Optional[queue.Queue] = None

        self._tts_func: Optional[Callable] = None
        self._stt_func: Optional[Callable] = None
        self._stt_instance: Optional[object] = None
        self._gui_callback: Optional[Callable] = None

        # [V9.5] Graceful shutdown sinyali
        self._shutdown_requested: bool = False

        # [10/10] Yeni callback'ler
        self._card_callback: Optional[Callable] = None
        self._chart_card_callback: Optional[Callable] = None   # (title, data, chart_type)
        self._vision_status_callback: Optional[Callable] = None  # (status_text, image_b64)
        self._memory_notify_callback: Optional[Callable] = None  # (text, mem_type, importance)
        self._memory_refresh_callback: Optional[Callable] = None # ()
        self._map_card_callback: Optional[Callable] = None       # (title, lat, lon, zoom)

    # ─────────────────────────────────────────────────────────────────────────
    # TEXT MODE
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def text_mode(self) -> bool:
        return self._text_mode

    @text_mode.setter
    def text_mode(self, value: bool) -> None:
        old_mode = self._text_mode
        self._text_mode = value
        if old_mode and not value:
            if self.text_input_queue:
                self.text_input_queue.put("")
                logger.info("[IOBridge] Sesli moda geçiş için kuyruk uyandırıldı.")

    # ─────────────────────────────────────────────────────────────────────────
    # SETTER'LAR
    # ─────────────────────────────────────────────────────────────────────────

    def set_tts(self, tts_func: Callable) -> None:
        self._tts_func = tts_func

    def set_stt(self, stt_func: Callable) -> None:
        self._stt_func = stt_func

    def set_stt_instance(self, instance: object) -> None:
        self._stt_instance = instance

    def reset_audio_engine(self) -> None:
        if self._stt_instance and hasattr(self._stt_instance, "reset_recognizer"):
            try:
                self._stt_instance.reset_recognizer()
                logger.info("[IOBridge] STT motoruna 'Hard Reset' uygulandı.")
            except Exception as e:
                logger.warning(f"STT reset hatası: {e}")

    def set_gui_callback(self, callback: Callable) -> None:
        self._gui_callback = callback

    def set_card_callback(self, callback: Callable) -> None:
        """Metin kartı: callback(title, content, image_path)"""
        self._card_callback = callback

    def set_chart_card_callback(self, callback: Callable) -> None:
        """
        [10/10] Grafik kartı callback'i.
        callback(title: str, data: dict, chart_type: str)

        chart_type değerleri: "bar" | "line" | "pie" | "area"

        data formatı (örnek):
          bar/line/area:
            {"labels": [...], "values": [...], "ylabel": "Değer"}
          pie:
            {"labels": [...], "values": [...]}
        """
        self._chart_card_callback = callback

    def set_vision_status_callback(self, callback: Callable) -> None:
        """
        [10/10] Vision modülü ekran analizi tamamlandığında çağrılır.
        callback(summary: str, screenshot_path: str | None)
        """
        self._vision_status_callback = callback

    def set_memory_notify_callback(self, callback: Callable) -> None:
        """
        [10/10] Hafıza kaydedildiğinde GUI'de toast bildirimi tetikler.
        callback(text: str, memory_type: str, importance: float)
        """
        self._memory_notify_callback = callback
    
    def set_memory_refresh_callback(self, callback: Callable) -> None:
        """[10/10] Hafıza kaydı sonrası GUI listesini yenilemek için."""
        self._memory_refresh_callback = callback

    
    def set_map_card_callback(self, callback: Callable) -> None:
        """
        [MAP] Harita kartı callback'i.
        callback(title: str, lat: float, lon: float, zoom: int)
        """
        self._map_card_callback = callback

    def display_map_card(self, title: str, lat: float, lon: float, zoom: int = 13) -> None:
        """
        Mission Control'e harita kartı gönderir.
        Kullanım örneği (brain.py'den):
        engine.io_bridge.display_map_card("Ofis Konumu", 41.0082, 28.9784, zoom=14)
        """
        if self._map_card_callback:
            try:
                self._map_card_callback(title, lat, lon, zoom)
            except Exception as e:
                logger.warning(f"Harita kartı gösterilirken hata: {e}")
        else:
            # Fallback: koordinatları metin kartı olarak göster
            self.display_card(title, f"📍 Konum: {lat:.5f}, {lon:.5f}")





    # ─────────────────────────────────────────────────────────────────────────
    # SHUTDOWN
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def request_shutdown(self) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        logger.info("[IOBridge] 🔴 Kapatma protokolü başlatıldı.")
        self.update_gui("KAPATILIYOR")
        if self.text_input_queue is not None:
            try:
                self.text_input_queue.put("__SHUTDOWN__")
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # I/O
    # ─────────────────────────────────────────────────────────────────────────

    async def speak(self, text: str) -> None:
        try:
            print(f"[J.A.R.V.I.S.]: {text}")
        except UnicodeEncodeError:
            # Fallback to ascii/safe characters if terminal doesn't support UTF-8
            safe_text = text.encode('ascii', 'replace').decode('ascii')
            print(f"[J.A.R.V.I.S.]: {safe_text}")
        if self._tts_func:
            try:
                await asyncio.get_running_loop().run_in_executor(None, self._tts_func, text)
            except Exception as e:
                logger.error(f"[IOBridge] TTS Hatası (maskelenmedi): {e}")

    async def get_input(self) -> str:
        loop = asyncio.get_running_loop()

        if self.text_input_queue is not None:
            try:
                return self.text_input_queue.get_nowait()
            except queue.Empty:
                pass

        if self.text_mode and self.text_input_queue is not None:
            self.update_gui("YAZILI MOD")
            _TEXT_INPUT_TIMEOUT_S = 300

            def _blocking_get() -> str:
                try:
                    return self.text_input_queue.get(timeout=_TEXT_INPUT_TIMEOUT_S)
                except queue.Empty:
                    return ""

            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, _blocking_get),
                    timeout=_TEXT_INPUT_TIMEOUT_S + 10,
                )
                return result or ""
            except asyncio.TimeoutError:
                logger.warning("get_input: Yazılı mod zaman aşımı (5 dakika).")
                return ""

        if self._stt_func:
            return await loop.run_in_executor(None, self._stt_func)

        return await loop.run_in_executor(None, input, ">>> ")

    # ─────────────────────────────────────────────────────────────────────────
    # GUI GÜNCELLEMELERİ
    # ─────────────────────────────────────────────────────────────────────────

    def update_gui(self, status: str) -> None:
        if self._gui_callback:
            try:
                self._gui_callback(status)
            except Exception as e:
                logger.warning(f"GUI güncellenirken hata: {e}")

    def display_card(self, title: str, content: str, image_path: str = None) -> None:
        """Metin + isteğe bağlı görsel içeren Mission Control kartı."""
        if self._card_callback:
            try:
                self._card_callback(title, content, image_path)
            except Exception as e:
                logger.warning(f"Kart gösterilirken hata: {e}")

    def display_chart_card(self, title: str, data: dict, chart_type: str = "bar") -> None:
        """
        [10/10] Matplotlib grafik kartı oluştur.

        Parametreler:
          title      : Kart başlığı
          data       : {"labels": [...], "values": [...], "ylabel": "..."}
                       Pasta grafik için sadece labels + values yeterli
          chart_type : "bar" | "line" | "pie" | "area"

        Örnek kullanım (brain.py'den):
          engine.io_bridge.display_chart_card(
              "Bugünkü Görevler",
              {"labels": ["Bitti","Devam","Bekliyor"], "values": [3,1,2]},
              chart_type="pie"
          )
        """
        if self._chart_card_callback:
            try:
                self._chart_card_callback(title, data, chart_type)
            except Exception as e:
                logger.warning(f"Grafik kartı gösterilirken hata: {e}")
        else:
            # Fallback: normal metin kartı olarak düz veri göster
            content_lines = []
            labels = data.get("labels", [])
            values = data.get("values", [])
            for lbl, val in zip(labels, values):
                content_lines.append(f"  {lbl}: {val}")
            self.display_card(title, "\n".join(content_lines) if content_lines else str(data))

    def update_vision_status(self, summary: str, screenshot_path: str = None) -> None:
        """
        [10/10] Vision modülü ekran analizini tamamladığında çağrılır.
        GUI'deki Vision Durumu göstergesini günceller ve
        analiz özetini bir kart olarak sunar.
        """
        if self._vision_status_callback:
            try:
                self._vision_status_callback(summary, screenshot_path)
            except Exception as e:
                logger.warning(f"Vision status güncellenirken hata: {e}")
        else:
            # Fallback: kartı log paneline yansıt
            self.display_card("👁 Ekran Analizi", summary, screenshot_path)

    def notify_memory_saved(self, text: str, memory_type: str, importance: float) -> None:
        """
        [10/10] Hafıza modülü tarafından çağrılır (set_on_save_callback üzerinden).
        GUI'de kısa "Öğrendim ✓" toast bildirimi tetikler.
        """
        if self._memory_notify_callback:
            try:
                self._memory_notify_callback(text, memory_type, importance)
            except Exception as e:
                logger.warning(f"Hafıza bildirimi gösterilirken hata: {e}")