import asyncio
import logging
import queue
from typing import Callable, Optional

logger = logging.getLogger("JARVIS.IOBridge")


class IOBridge:
    """J.A.R.V.I.S. v2 I/O Interface [10/10 Upgrade]

    New features:
    + display_chart_card() → Matplotlib sends card containing chart
    + update_vision_status() → Reports the status of the Vision module to the GUI
    + set_memory_notify_callback() → Triggers GUI toast on memory recording"""

    def __init__(self, config=None):
        self.config = config
        self._text_mode: bool = False
        self.text_input_queue: Optional[queue.Queue] = None

        self._tts_func: Optional[Callable] = None
        self._stt_func: Optional[Callable] = None
        self._stt_instance: Optional[object] = None
        self._gui_callback: Optional[Callable] = None

        # [V9.5] Graceful shutdown signal
        self._shutdown_requested: bool = False

        # [10/10] New callbacks
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

        # [V13.1] STT Mute/Unmute — Mute microphone completely in text mode
        if self._stt_instance and hasattr(self._stt_instance, "_muted"):
            self._stt_instance._muted = value
            if value:
                logger.info("[IOBridge] STT muted — text mode active, microphone disabled.")
            else:
                logger.info("[IOBridge] STT active — audio mode, microphone on.")

        if old_mode and not value:
            if self.text_input_queue:
                self.text_input_queue.put("")
                logger.info("[IOBridge] Queue woken up to switch to voice mode.")

    # ─────────────────────────────────────────────────────────────────────────
    # SETTERS
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
                logger.info("[IOBridge] 'Hard Reset' applied to STT engine.")
            except Exception as e:
                logger.warning(f"STT reset error: {e}")

    def set_gui_callback(self, callback: Callable) -> None:
        self._gui_callback = callback

    def set_card_callback(self, callback: Callable) -> None:
        """Text card: callback(title, content, image_path)"""
        self._card_callback = callback

    def set_chart_card_callback(self, callback: Callable) -> None:
        """[10/10] Graphics card callback.
        callback(title: str, data: dict, chart_type: str)

        chart_type values: "bar" | "line" | "pie" | "area"

        data format (example):
          bar/line/area:
            {"labels": [...], "values": [...], "ylabel": "Value"}
          Pie:
            {"labels": [...], "values": [...]}"""
        self._chart_card_callback = callback

    def set_vision_status_callback(self, callback: Callable) -> None:
        """[10/10] Called when the Vision module screen analysis is completed.
        callback(summary: str, screenshot_path: str | None)"""
        self._vision_status_callback = callback

    def set_memory_notify_callback(self, callback: Callable) -> None:
        """[10/10] Triggers toast notification in GUI when memory is saved.
        callback(text: str, memory_type: str, importance: float)"""
        self._memory_notify_callback = callback
    
    def set_memory_refresh_callback(self, callback: Callable) -> None:
        """[10/10] To refresh the GUI list after memory saving."""
        self._memory_refresh_callback = callback

    
    def set_map_card_callback(self, callback: Callable) -> None:
        """[MAP] Map card callback.
        callback(title: str, lat: float, lon: float, zoom: int)"""
        self._map_card_callback = callback

    def display_map_card(self, title: str, lat: float, lon: float, zoom: int = 13) -> None:
        """Sends map card to Mission Control.
        Usage example (from brain.py):
        engine.io_bridge.display_map_card("Office Location", 41.0082, 28.9784, zoom=14)"""
        if self._map_card_callback:
            try:
                self._map_card_callback(title, lat, lon, zoom)
            except Exception as e:
                logger.warning(f"Error showing map card: {e}")
        else:
            # Fallback: show coordinates as text card
            self.display_card(title, f"📍 Location: {lat:.5f}, {lon:.5f}")





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
        logger.info("[IOBridge] 🔴 Shutdown protocol initiated.")
        self.update_gui("SHUTTING DOWN")
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
                logger.error(f"[IOBridge] TTS Error (not masked): {e}")

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
                logger.warning("get_input: Written mode timeout (5 minutes).")
                return ""

        if self._stt_func:
            return await loop.run_in_executor(None, self._stt_func)

        return await loop.run_in_executor(None, input, ">>> ")

    # ─────────────────────────────────────────────────────────────────────────
    # GUI UPDATES
    # ─────────────────────────────────────────────────────────────────────────

    def update_gui(self, status: str) -> None:
        if self._gui_callback:
            try:
                self._gui_callback(status)
            except Exception as e:
                logger.warning(f"Error updating GUI: {e}")

    def display_card(self, title: str, content: str, image_path: str = None) -> None:
        """Mission Control card with text + optional image."""
        if self._card_callback:
            try:
                self._card_callback(title, content, image_path)
            except Exception as e:
                logger.warning(f"Error showing card: {e}")

    def display_chart_card(self, title: str, data: dict, chart_type: str = "bar") -> None:
        """[10/10] Create Matplotlib graphics card.

        Parameters:
          title : Card title
          data : {"labels": [...], "values": [...], "ylabel": "..."}
                       For a pie chart, only labels + values are enough
          chart_type : "bar" | "line" | "pie" | "area"

        Example usage (from brain.py):
          engine.io_bridge.display_chart_card(
              "Today's Tasks",
              {"labels": ["Bitti","Devam","Bekliyor"], "values": [3,1,2]},
              chart_type="pie"
          )"""
        if self._chart_card_callback:
            try:
                self._chart_card_callback(title, data, chart_type)
            except Exception as e:
                logger.warning(f"Error showing graphics card: {e}")
        else:
            # Fallback: show plain data as normal text card
            content_lines = []
            labels = data.get("labels", [])
            values = data.get("values", [])
            for lbl, val in zip(labels, values):
                content_lines.append(f"  {lbl}: {val}")
            self.display_card(title, "\n".join(content_lines) if content_lines else str(data))

    def update_vision_status(self, summary: str, screenshot_path: str = None) -> None:
        """[10/10] Called when the Vision module completes screen analysis.
        Updates the Vision Status indicator in the GUI and
        presents the analysis summary as a card."""
        if self._vision_status_callback:
            try:
                self._vision_status_callback(summary, screenshot_path)
            except Exception as e:
                logger.warning(f"Error while updating vision status: {e}")
        else:
            # Fallback: reflect the card to the log panel
            self.display_card("👁 Screen Analysis", summary, screenshot_path)

    def notify_memory_saved(self, text: str, memory_type: str, importance: float) -> None:
        """[10/10] Called by the memory module (via set_on_save_callback).
        In the GUI, a short "I learned ✓" toast triggers the notification."""
        if self._memory_notify_callback:
            try:
                self._memory_notify_callback(text, memory_type, importance)
            except Exception as e:
                logger.warning(f"Error showing memory notification: {e}")