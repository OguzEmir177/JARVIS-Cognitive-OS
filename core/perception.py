"""
[V12.0] J.A.R.V.I.S. True Visual Cognition Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real perception: OCR extraction, UI semantic parsing, entity detection,
region attention, adaptive scan frequency, active app understanding.
NOT just hash comparison.
"""
import asyncio, logging, time, os
import numpy as np
from typing import Dict, Any, List, Optional
from PIL import ImageGrab

logger = logging.getLogger("JARVIS.Perception")

# Optional heavy deps — graceful fallback
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    logger.warning("OpenCV not available — visual cognition degraded.")

try:
    import pytesseract
    # Windows default path
    _tess_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(_tess_path):
        pytesseract.pytesseract.tesseract_cmd = _tess_path
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    logger.debug("pytesseract not available — OCR disabled.")

try:
    import pygetwindow as gw
    HAS_GW = True
except ImportError:
    HAS_GW = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class PerceptionLayer:
    """
    [V12.0] REAL Visual Cognition Engine
    
    Capabilities:
    - Perceptual hashing for change detection (fast path)
    - OCR text extraction from screen regions
    - UI element detection via contour analysis
    - Active window + process tracking
    - Adaptive scan frequency (fast when active, slow when idle)
    - Region-of-interest attention tracking
    - System metrics collection
    """

    def __init__(self, event_bus, world_state):
        self.event_bus = event_bus
        self.world_state = world_state
        self._running = False

        # Vision module (for LLM-based analysis when needed)
        self._vision = None
        try:
            from core.vision import JarvisVision
            self._vision = JarvisVision()
        except Exception:
            pass

        # Perception state
        self._last_hash = None
        self._last_window_title = ""
        self._last_ocr_time = 0.0
        self._last_deep_analysis_time = 0.0

        # Adaptive timing
        self.base_interval = 3.0
        self.active_interval = 1.0
        self.current_interval = self.base_interval
        self.hash_threshold = 3  # Hamming distance for "significant change"

        # OCR settings
        self.ocr_interval = 15.0  # OCR every 15s max (expensive)
        self.deep_analysis_interval = 60.0  # Full LLM vision every 60s

        # Screen regions of interest
        self._roi_history: List[Dict[str, Any]] = []

    async def start(self):
        self._running = True
        logger.info("True Visual Cognition Engine started.")
        asyncio.create_task(self._perception_loop())

    def stop(self):
        self._running = False

    async def _perception_loop(self):
        """Main perception loop with multi-level analysis."""
        while self._running:
            try:
                now = time.time()

                # ── LEVEL 1: Window + Process Tracking (always) ──
                window_info = self._get_active_window_info()
                window_changed = window_info["title"] != self._last_window_title

                if window_changed:
                    logger.info(f"Context shift: {self._last_window_title} → {window_info['title']}")
                    self._last_window_title = window_info["title"]

                # ── LEVEL 2: Screen Capture + Hash (fast) ──
                screenshot = None
                frame = None
                significant_change = window_changed

                try:
                    screenshot = ImageGrab.grab()
                    if HAS_CV2:
                        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
                        current_hash = self._calculate_phash(frame)
                        if self._last_hash is not None:
                            diff = self._hamming_distance(self._last_hash, current_hash)
                            if diff >= self.hash_threshold:
                                significant_change = True
                        self._last_hash = current_hash
                except Exception as e:
                    logger.debug(f"Screen capture error: {e}")

                # ── LEVEL 3: OCR Extraction (periodic or on change) ──
                ocr_text = ""
                if significant_change and HAS_OCR and frame is not None:
                    if now - self._last_ocr_time > self.ocr_interval:
                        ocr_text = await self._extract_ocr(frame)
                        self._last_ocr_time = now

                # ── LEVEL 4: UI Element Detection (on change) ──
                ui_entities = []
                if significant_change and HAS_CV2 and frame is not None:
                    ui_entities = self._detect_ui_elements(frame)

                # ── LEVEL 5: Deep Semantic Analysis (CANCELLED) ──
                visual_summary = ""
                # This feature has been turned off because constantly sending photos to LLM in the background consumes API quotas.
                # Visual analysis will ONLY work via VisionTool when the user gives the "Analyze screen" command.

                # ── LEVEL 6: System Metrics ──
                sys_metrics = self._collect_system_metrics()

                # ── UPDATE WORLD STATE ──
                updates = {
                    "active_window": window_info["title"],
                    "active_app_name": window_info["app"],
                    "system_metrics": sys_metrics,
                }

                if ocr_text:
                    updates["ocr_text"] = ocr_text
                if visual_summary:
                    updates["visual_summary"] = visual_summary
                    updates["last_visual_update"] = now

                await self.world_state.update_state(updates)

                # Update entity registry
                if ui_entities:
                    self.world_state.update_visual_entities(ui_entities)

                # Infer user intent periodically (Now handled by HypothesisEngine/WorkflowEngine)
                # if window_changed:
                #    self.world_state.infer_user_intent()

                # ── ADAPTIVE FREQUENCY ──
                if significant_change:
                    self.current_interval = self.active_interval
                else:
                    self.current_interval = min(self.base_interval, self.current_interval + 0.3)

                # ── EMIT EVENTS ──
                if significant_change:
                    await self.event_bus.emit("PERCEPTION_UPDATE", {
                        "window": window_info["title"],
                        "change_type": "window" if window_changed else "visual",
                        "ocr_available": bool(ocr_text),
                        "entities_found": len(ui_entities),
                    }, sender="Perception")

                await asyncio.sleep(self.current_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Perception loop error: {e}")
                await asyncio.sleep(5)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  WINDOW TRACKING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_active_window_info(self) -> Dict[str, str]:
        """Gets active window title and process name."""
        title = "Desktop"
        app = "Unknown"
        try:
            if HAS_GW:
                win = gw.getActiveWindow()
                if win:
                    title = win.title or "Desktop"
            # Get process name
            if HAS_PSUTIL:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                try:
                    proc = psutil.Process(pid.value)
                    app = proc.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        return {"title": title, "app": app}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VISUAL HASHING
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _calculate_phash(self, image):
        """64-bit perceptual hash using DCT."""
        resized = cv2.resize(image, (32, 32), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        dct = cv2.dct(np.float32(gray))
        dct_low = dct[:8, :8]
        avg = dct_low.mean()
        return (dct_low > avg).flatten()

    def _hamming_distance(self, h1, h2):
        return np.count_nonzero(h1 != h2)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  OCR EXTRACTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _extract_ocr(self, frame) -> str:
        """Extracts text from screen using Tesseract OCR."""
        if not HAS_OCR or not HAS_CV2:
            return ""
        try:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._ocr_sync, frame)
            return text
        except Exception as e:
            logger.debug(f"OCR extraction failed: {e}")
            return ""

    def _ocr_sync(self, frame) -> str:
        """Synchronous OCR — runs in thread pool."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Resize for speed (half resolution)
        h, w = gray.shape
        if w > 1920:
            scale = 1920 / w
            gray = cv2.resize(gray, None, fx=scale, fy=scale)
        # Apply threshold for better OCR
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(thresh, lang="tur+eng", config="--psm 6")
        # Clean up
        lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 2]
        return '\n'.join(lines[:30])  # Max 30 lines

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  UI ELEMENT DETECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _detect_ui_elements(self, frame) -> List[Dict[str, Any]]:
        """
        [V13.0] True UI Hierarchy Cognition
        Detects elements and builds a semantic hierarchy (parent-child, modals, dialogs, action roles).
        """
        if not HAS_CV2:
            return []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            dilated = cv2.dilate(edges, kernel, iterations=2)
            
            # RETR_TREE gives us hierarchy!
            contours, hierarchy = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            entities = []
            h, w = frame.shape[:2]
            min_area = (w * h) * 0.001
            max_area = (w * h) * 0.5

            if hierarchy is None:
                return []

            # First pass: identify regions and modals
            modals = []
            for i, cnt in enumerate(contours):
                area = cv2.contourArea(cnt)
                if area < min_area or area > max_area: continue
                
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / max(ch, 1)
                
                # Semantic modal/dialog detection
                # A dialog is typically a large box in the center of the screen
                center_dist = math.sqrt(((x+cw/2) - w/2)**2 + ((y+ch/2) - h/2)**2)
                if 0.15 * (w*h) < area < 0.4 * (w*h) and center_dist < h/3:
                    modals.append((i, [x, y, cw, ch]))

            for i, cnt in enumerate(contours):
                area = cv2.contourArea(cnt)
                if area < min_area or area > max_area:
                    continue

                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / max(ch, 1)

                # Determine semantic role
                role = "unknown"
                if 2.0 < aspect < 8.0 and ch < 60:
                    role = "action_button"
                elif 3.0 < aspect and ch < 40:
                    role = "text_input"
                elif 0.8 < aspect < 1.2:
                    role = "icon"
                else:
                    role = "container"

                # Check if it belongs to a modal
                parent_modal = None
                for m_idx, m_box in modals:
                    if i != m_idx and m_box[0] <= x and m_box[1] <= y and \
                       (m_box[0]+m_box[2]) >= (x+cw) and (m_box[1]+m_box[3]) >= (y+ch):
                        parent_modal = "ModalDialog"
                        break
                        
                if any(i == m_idx for m_idx, _ in modals):
                    role = "modal_dialog"

                entities.append({
                    "type": role, 
                    "label": "", 
                    "bbox": [x, y, cw, ch],
                    "confidence": min(0.9, area / max_area),
                    "context": parent_modal or "MainUI",
                    "affordance": "clickable" if "button" in role else "typable" if "input" in role else "viewable"
                })

            entities.sort(key=lambda e: e["bbox"][2]*e["bbox"][3], reverse=True)
            return entities[:30]
        except Exception as e:
            logger.debug(f"UI detection error: {e}")
            return []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  DEEP VISUAL ANALYSIS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _deep_visual_analysis(self) -> str:
        """Uses LLM vision model for semantic scene understanding."""
        if not self._vision:
            return ""
        try:
            loop = asyncio.get_running_loop()
            from core.vision import JarvisVision
            result = await loop.run_in_executor(None, self._vision.analyze_screen)
            if result and JarvisVision.ERROR_SENTINEL not in result:
                return result
        except Exception as e:
            logger.debug(f"Deep vision analysis error: {e}")
        return ""

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SYSTEM METRICS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _collect_system_metrics(self) -> Dict[str, Any]:
        """Collects CPU, memory, and battery info."""
        metrics = {}
        if HAS_PSUTIL:
            try:
                metrics["cpu_percent"] = psutil.cpu_percent(interval=0)
                mem = psutil.virtual_memory()
                metrics["memory_percent"] = mem.percent
                metrics["memory_available_gb"] = round(mem.available / (1024**3), 1)
                battery = psutil.sensors_battery()
                if battery:
                    metrics["battery_percent"] = battery.percent
                    metrics["battery_plugged"] = battery.power_plugged
            except Exception:
                pass
        return metrics
