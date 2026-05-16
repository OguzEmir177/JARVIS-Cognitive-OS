"""
J.A.R.V.I.S. — Visual Control Interface  [10/10 Upgrade]
Iron Man HUD Style | Dark Blue Theme
gui/interface.py

Yenilikler:
  + HAFIZA sekmesi: canlı hafıza listesi, istatistik grafiği, yenile butonu
  + display_chart_card(): gerçek matplotlib grafik → CTkImage olarak kart içinde render
  + display_card()      : image_path varsa PIL ile görsel yükler ve gösterir
  + Toast bildirimi     : "Öğrendim ✓" — hafıza kaydedilince 3 sn görünür
  + Vision Status       : HUD sol paneline ekran analizi özeti
  + Grafik kartı renk teması: Jarvis mavi-cyan palette
"""

import customtkinter as ctk
import tkinter as tk
import threading
import queue
import sys
import io
import os
import math
import time
import pyautogui
import win32gui
import win32con
from datetime import datetime
import logging

logger = logging.getLogger("JARVIS.GUI")

try:
    from staticmap import StaticMap, CircleMarker
    HAS_STATICMAP = True
except ImportError:
    HAS_STATICMAP = False
# Matplotlib — GUI thread dışında çizim için Agg backend
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

# Pillow
try:
    from PIL import Image as PILImage, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Renk Paleti ──────────────────────────────────────────────────────────────
BG_DEEP     = "#040810"
BG_PANEL    = "#070D1C"
BG_CARD     = "#091224"
ACCENT_BLUE = "#00C8FF"
ACCENT_DIM  = "#003D5C"
ACCENT_RING = "#0077AA"
ORANGE      = "#FF6B35"
GREEN_OK    = "#00E87A"
RED_ERR     = "#FF3B3B"
TEXT_MAIN   = "#C8E8FF"
TEXT_DIM    = "#35526B"
LOG_JARVIS  = "#00C8FF"
LOG_USER    = "#90C8E8"
LOG_ERROR   = "#FF6B35"
LOG_SYSTEM  = "#446680"
LOG_OK      = "#00E87A"

# Grafik renkleri (matplotlib için hex)
CHART_COLORS = ["#00C8FF", "#FF6B35", "#00E87A", "#9B59B6", "#F1C40F",
                "#E74C3C", "#3498DB", "#2ECC71", "#E67E22", "#1ABC9C"]

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Matplotlib Yardımcıları ──────────────────────────────────────────────────

def _fig_to_ctk_image(fig: Figure, width: int = 460, height: int = 230) -> "ctk.CTkImage | None":
    """Matplotlib figure → CTkImage dönüştürücü. Pillow gerektirir."""
    if not HAS_PIL:
        return None
    try:
        canvas = FigureCanvasAgg(fig)
        canvas.draw()
        buf = canvas.buffer_rgba()
        pil_img = PILImage.frombuffer("RGBA", canvas.get_width_height(), buf, "raw", "RGBA", 0, 1)
        pil_img = pil_img.resize((width, height), PILImage.LANCZOS)
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(width, height))
    except Exception:
        return None
    finally:
        plt.close(fig)


def _apply_jarvis_style(fig: Figure, ax):
    """Tüm grafiklere J.A.R.V.I.S. koyu temasını uygular."""
    fig.patch.set_facecolor(BG_CARD)
    ax.set_facecolor("#060F20")
    ax.tick_params(colors=TEXT_MAIN, labelsize=7)
    ax.xaxis.label.set_color(TEXT_MAIN)
    ax.yaxis.label.set_color(TEXT_MAIN)
    ax.title.set_color(ACCENT_BLUE)
    for spine in ax.spines.values():
        spine.set_edgecolor(ACCENT_DIM)
    ax.grid(color=ACCENT_DIM, linestyle="--", linewidth=0.4, alpha=0.6)


def render_bar_chart(data: dict, title: str) -> "ctk.CTkImage | None":
    labels = data.get("labels", [])
    values = data.get("values", [])
    ylabel = data.get("ylabel", "")
    if not labels or not values:
        return None

    fig, ax = plt.subplots(figsize=(5.2, 2.5))
    bars = ax.bar(labels, values, color=CHART_COLORS[:len(labels)], width=0.55, edgecolor="none")
    ax.set_ylabel(ylabel, fontsize=7)
    ax.set_title(title, fontsize=8, pad=6)
    _apply_jarvis_style(fig, ax)
    # Değer etiketleri
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.02,
                str(val), ha='center', va='bottom', color=TEXT_MAIN, fontsize=7)
    fig.tight_layout(pad=0.6)
    return _fig_to_ctk_image(fig)


def render_line_chart(data: dict, title: str) -> "ctk.CTkImage | None":
    labels = data.get("labels", [])
    values = data.get("values", [])
    ylabel = data.get("ylabel", "")
    if not labels or not values:
        return None

    fig, ax = plt.subplots(figsize=(5.2, 2.5))
    ax.plot(labels, values, color=ACCENT_BLUE, linewidth=1.8, marker="o",
            markersize=4, markerfacecolor=ORANGE)
    ax.fill_between(range(len(labels)), values, alpha=0.12, color=ACCENT_BLUE)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=6)
    ax.set_ylabel(ylabel, fontsize=7)
    ax.set_title(title, fontsize=8, pad=6)
    _apply_jarvis_style(fig, ax)
    fig.tight_layout(pad=0.6)
    return _fig_to_ctk_image(fig)


def render_area_chart(data: dict, title: str) -> "ctk.CTkImage | None":
    """Çizgi + doldurulmuş alan — line ile aynı, daha belirgin dolgu."""
    labels = data.get("labels", [])
    values = data.get("values", [])
    ylabel = data.get("ylabel", "")
    if not labels or not values:
        return None

    fig, ax = plt.subplots(figsize=(5.2, 2.5))
    ax.fill_between(range(len(labels)), values, alpha=0.35, color=ACCENT_BLUE)
    ax.plot(labels, values, color=ACCENT_BLUE, linewidth=1.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=6)
    ax.set_ylabel(ylabel, fontsize=7)
    ax.set_title(title, fontsize=8, pad=6)
    _apply_jarvis_style(fig, ax)
    fig.tight_layout(pad=0.6)
    return _fig_to_ctk_image(fig)


def render_pie_chart(data: dict, title: str) -> "ctk.CTkImage | None":
    labels = data.get("labels", [])
    values = data.get("values", [])
    if not labels or not values:
        return None

    fig, ax = plt.subplots(figsize=(3.8, 2.6))
    wedges, texts, autotexts = ax.pie(
        values, labels=labels,
        colors=CHART_COLORS[:len(labels)],
        autopct="%1.0f%%",
        startangle=140,
        textprops={"color": TEXT_MAIN, "fontsize": 7},
        wedgeprops={"edgecolor": BG_CARD, "linewidth": 1.2}
    )
    for at in autotexts:
        at.set_fontsize(6)
        at.set_color(BG_DEEP)
    ax.set_title(title, fontsize=8, pad=6, color=ACCENT_BLUE)
    fig.patch.set_facecolor(BG_CARD)
    fig.tight_layout(pad=0.4)
    return _fig_to_ctk_image(fig, width=380, height=240)


def render_chart(chart_type: str, data: dict, title: str) -> "ctk.CTkImage | None":
    """Grafik türüne göre doğru renderer'ı çağırır."""
    dispatch = {
        "bar":  render_bar_chart,
        "line": render_line_chart,
        "pie":  render_pie_chart,
        "area": render_area_chart,
    }
    fn = dispatch.get(chart_type, render_bar_chart)
    try:
        return fn(data, title)
    except Exception:
        return None


def render_map_card(lat: float, lon: float, zoom: int = 13,
                    width: int = 460, height: int = 260) -> "ctk.CTkImage | None":
    """
    OpenStreetMap tile'larından statik harita görüntüsü oluşturur.
    staticmap kütüphanesi gerektirir: pip install staticmap
    """
    if not HAS_STATICMAP or not HAS_PIL:
        return None
    try:
        m = StaticMap(width, height)
        m.add_marker(CircleMarker((lon, lat), "#1E90FF", 14))
        m.add_marker(CircleMarker((lon, lat), "#FFFFFF", 6))
        pil_img = m.render(zoom=zoom)
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(width, height))
    except Exception as e:
        logger.warning(f"[MAP] Harita oluşturulamadı: {e}")
        return None

# ── Stdout Yönlendirici ───────────────────────────────────────────────────────
class GUIStream(io.IOBase):
    def __init__(self, callback):
        self.callback = callback
        self._buf = ""

    def write(self, text):
        self._buf += text
        if "\n" in self._buf:
            lines = self._buf.split("\n")
            for line in lines[:-1]:
                if line.strip():
                    self.callback(line.strip())
            self._buf = lines[-1]
        return len(text)

    def flush(self):
        if self._buf.strip():
            self.callback(self._buf.strip())
            self._buf = ""

    def readable(self): return False
    def writable(self): return True
    def seekable(self): return False


# ── Ana GUI Sınıfı ────────────────────────────────────────────────────────────
class JarvisInterface:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("J.A.R.V.I.S. — Sistem Kontrol Merkezi")
        self.root.geometry("1100x760")
        self.root.minsize(900, 640)
        self.root.configure(fg_color=BG_DEEP)

        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - 1100) // 2}+{(sh - 760) // 2}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Durum değişkenleri
        self.text_mode   = False
        self.input_queue = queue.Queue()
        self._status     = "BAŞLATILIYOR"
        self._running    = True
        self._anim_angle = 0.0
        self._anim_pulse = 0.0
        self._anim_dir   = 1
        self._anim_glow  = 0.0
        self.engine      = None

        # [10/10] Vision son özet
        self._last_vision_summary = "Henüz analiz yapılmadı."

        # [10/10] Toast kuyruğu
        self._toast_queue: queue.Queue = queue.Queue()
        self._toast_visible = False

        self._build_ui()
        self._redirect_stdout()
        self._start_jarvis()
        self._animate()
        self._poll_toast()

    # ─────────────────────────────────────────────────────────────────────────
    # UI İNŞASI
    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Üst Bar
        topbar = tk.Frame(self.root, bg="#030810", height=52)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="  ⬡  J·A·R·V·I·S",
                 font=("Consolas", 17, "bold"),
                 fg=ACCENT_BLUE, bg="#030810").pack(side="left", padx=16, pady=10)

        tk.Label(topbar, text="JUST A RATHER VERY INTELLIGENT SYSTEM",
                 font=("Consolas", 8), fg=TEXT_DIM, bg="#030810").pack(side="left", pady=16)

        self.version_lbl = tk.Label(topbar, text="● AKTİF   v2.0  ",
                                    font=("Consolas", 10, "bold"),
                                    fg=GREEN_OK, bg="#030810")
        self.version_lbl.pack(side="right", padx=10)

        tk.Frame(self.root, bg=ACCENT_DIM, height=1).pack(fill="x")

        # Orta İçerik
        content = tk.Frame(self.root, bg=BG_DEEP)
        content.pack(fill="both", expand=True, padx=8, pady=(6, 0))

        # Sol HUD
        left = tk.Frame(content, bg=BG_PANEL, width=320,
                        highlightbackground=ACCENT_DIM, highlightthickness=1)
        left.pack(side="left", fill="y", padx=(0, 5), pady=2)
        left.pack_propagate(False)
        self._build_hud_panel(left)

        # Sağ Sekmeler
        right = tk.Frame(content, bg=BG_PANEL,
                         highlightbackground=ACCENT_DIM, highlightthickness=1)
        right.pack(side="left", fill="both", expand=True, pady=2)

        self.tabview = ctk.CTkTabview(
            right, fg_color=BG_PANEL,
            segmented_button_fg_color=BG_PANEL,
            segmented_button_selected_color=ACCENT_BLUE,
            segmented_button_selected_hover_color=ACCENT_RING,
            segmented_button_unselected_color=BG_CARD,
            segmented_button_unselected_hover_color=ACCENT_DIM,
            border_width=0
        )
        self.tabview.pack(fill="both", expand=True, padx=2, pady=2)

        tab_log     = self.tabview.add("LOGS")
        tab_mission = self.tabview.add("MISSION CONTROL")
        tab_memory  = self.tabview.add("HAFIZA")

        self._build_log_panel(tab_log)
        self._build_mission_panel(tab_mission)
        self._build_memory_panel(tab_memory)

        # Alt Giriş
        tk.Frame(self.root, bg=ACCENT_DIM, height=1).pack(fill="x")
        bottom = tk.Frame(self.root, bg=BG_PANEL, height=62)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        self._build_bottom_bar(bottom)

    # ─────────────────────────────────────────────────────────────────────────
    # HUD PANELİ
    # ─────────────────────────────────────────────────────────────────────────
    def _build_hud_panel(self, parent):
        self.canvas = tk.Canvas(parent, width=290, height=250,
                                bg=BG_PANEL, highlightthickness=0)
        self.canvas.pack(pady=(14, 0))

        self.status_lbl = tk.Label(parent, text="● BAŞLATILIYOR",
                                   font=("Consolas", 12, "bold"),
                                   fg=ACCENT_BLUE, bg=BG_PANEL)
        self.status_lbl.pack(pady=(4, 2))

        tk.Frame(parent, bg=ACCENT_DIM, height=1).pack(fill="x", padx=18, pady=6)

        tk.Label(parent, text="SON KOMUT", font=("Consolas", 8, "bold"),
                 fg=TEXT_DIM, bg=BG_PANEL).pack(padx=14, anchor="w")
        self.last_cmd = tk.Label(parent, text="—", font=("Consolas", 10),
                                 fg=TEXT_MAIN, bg=BG_PANEL, wraplength=280,
                                 justify="left", anchor="w")
        self.last_cmd.pack(padx=14, anchor="w", pady=(2, 6))

        tk.Label(parent, text="SON YANIT", font=("Consolas", 8, "bold"),
                 fg=TEXT_DIM, bg=BG_PANEL).pack(padx=14, anchor="w")
        self.last_resp = tk.Label(parent, text="—", font=("Consolas", 10),
                                  fg=ACCENT_BLUE, bg=BG_PANEL, wraplength=280,
                                  justify="left", anchor="w")
        self.last_resp.pack(padx=14, anchor="w", pady=(2, 6))

        # [10/10] Vision Durum Kutusu
        tk.Frame(parent, bg=ACCENT_DIM, height=1).pack(fill="x", padx=18, pady=4)
        tk.Label(parent, text="👁  EKRAN ANALİZİ", font=("Consolas", 8),
                 fg=TEXT_DIM, bg=BG_PANEL).pack(padx=14, anchor="w")
        self.vision_lbl = tk.Label(parent, text="Bekliyor...",
                                   font=("Consolas", 9), fg="#5588AA", bg=BG_PANEL,
                                   wraplength=278, justify="left", anchor="w")
        self.vision_lbl.pack(padx=14, anchor="w", pady=(2, 4))

        # Mod Toggle
        tk.Frame(parent, bg=ACCENT_DIM, height=1).pack(fill="x", padx=18, pady=4)
        tk.Label(parent, text="GİRİŞ MODU", font=("Consolas", 8),
                 fg=TEXT_DIM, bg=BG_PANEL).pack(padx=14, anchor="w")

        toggle_row = tk.Frame(parent, bg=BG_PANEL)
        toggle_row.pack(padx=14, pady=6, anchor="w")

        tk.Label(toggle_row, text="🎙 Sesli", font=("Consolas", 11),
                 fg=TEXT_MAIN, bg=BG_PANEL).pack(side="left", padx=(0, 8))
        self.mode_switch = ctk.CTkSwitch(
            toggle_row, text="", width=56, height=28,
            fg_color=ACCENT_DIM, progress_color=ORANGE,
            command=self._toggle_mode
        )
        self.mode_switch.pack(side="left")
        tk.Label(toggle_row, text="⌨ Yazılı", font=("Consolas", 11),
                 fg=TEXT_DIM, bg=BG_PANEL).pack(side="left", padx=(8, 0))

        tk.Frame(parent, bg=ACCENT_DIM, height=1).pack(fill="x", padx=18, pady=(8, 4))
        tk.Label(parent, text="Oğuz Emir  |  J.A.R.V.I.S. ©",
                 font=("Consolas", 8), fg=TEXT_DIM, bg=BG_PANEL).pack(pady=4)

    # ─────────────────────────────────────────────────────────────────────────
    # MISSION CONTROL — Zengin Kartlar
    # ─────────────────────────────────────────────────────────────────────────
    def _build_mission_panel(self, parent):
        # Canlı Vitals (CPU/RAM) Barı
        self.vitals_frame = tk.Frame(parent, bg="#050A15", highlightbackground=ACCENT_DIM, highlightthickness=1)
        self.vitals_frame.pack(fill="x", padx=5, pady=(5, 0))
        
        tk.Label(self.vitals_frame, text="⚡ SİSTEM DURUMU:", font=("Consolas", 9, "bold"), fg=TEXT_DIM, bg="#050A15").pack(side="left", padx=10, pady=6)
        self.cpu_lbl = tk.Label(self.vitals_frame, text="CPU: %0", font=("Consolas", 9, "bold"), fg=ACCENT_BLUE, bg="#050A15")
        self.cpu_lbl.pack(side="left", padx=10)
        self.ram_lbl = tk.Label(self.vitals_frame, text="RAM: %0", font=("Consolas", 9, "bold"), fg=ACCENT_BLUE, bg="#050A15")
        self.ram_lbl.pack(side="left", padx=10)

        self.card_container = ctk.CTkScrollableFrame(
            parent, fg_color=BG_PANEL,
            label_text="⬢  DİNAMİK VERİ KARTLARI",
            label_font=("Consolas", 11, "bold"),
            label_text_color=ACCENT_BLUE,
            label_fg_color="transparent",
            scrollbar_button_color=ACCENT_DIM,
            scrollbar_button_hover_color=ACCENT_BLUE
        )
        self.card_container.pack(fill="both", expand=True, padx=5, pady=5)

        # Başlangıç kartı
        self.display_card(
            "Sistem Hazır",
            "Mission Control aktif. Grafik kartları, ekran analizi ve proaktif eylemler burada görünecek.",
            None
        )
        self._poll_vitals()

    def _poll_vitals(self):
        try:
            import psutil
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.cpu_lbl.configure(text=f"CPU: %{cpu}")
            self.ram_lbl.configure(text=f"RAM: %{ram}")
        except Exception:
            pass
        self.root.after(2000, self._poll_vitals)

    def display_card(self, title: str, content: str, image_path: str = None):
        """Metin + isteğe bağlı görsel içeren kart. Thread-safe."""
        self.root.after(0, lambda: self._create_card_ui(title, content, image_path))

    def _create_card_ui(self, title: str, content: str, image_path: str = None):
        self.tabview.set("MISSION CONTROL")

        card = ctk.CTkFrame(self.card_container, fg_color=BG_CARD,
                            corner_radius=10, border_width=1, border_color=ACCENT_DIM)
        card.pack(fill="x", padx=10, pady=8, side="top")

        # Başlık satırı
        header = tk.Frame(card, bg=BG_CARD)
        header.pack(fill="x", padx=15, pady=(12, 0))

        tk.Label(header, text=f"⌬ {title.upper()}",
                 font=("Consolas", 11, "bold"),
                 fg=ACCENT_BLUE, bg=BG_CARD).pack(side="left")

        ts = datetime.now().strftime("%H:%M")
        tk.Label(header, text=ts, font=("Consolas", 8),
                 fg=TEXT_DIM, bg=BG_CARD).pack(side="right")

        tk.Frame(card, bg=ACCENT_DIM, height=1).pack(fill="x", padx=15, pady=(5, 0))

        # İçerik metni
        tk.Label(card, text=content, font=("Consolas", 10),
                 fg=TEXT_MAIN, bg=BG_CARD, wraplength=480,
                 justify="left", anchor="w").pack(padx=15, pady=(8, 8), anchor="w")

        # [10/10] Görsel yükleme
        if image_path and HAS_PIL and os.path.exists(image_path):
            try:
                pil_img = PILImage.open(image_path)
                max_w = 460
                ratio = max_w / pil_img.width
                new_h = int(pil_img.height * ratio)
                pil_img = pil_img.resize((max_w, new_h), PILImage.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img,
                                       size=(max_w, new_h))
                img_lbl = ctk.CTkLabel(card, image=ctk_img, text="")
                img_lbl.image = ctk_img  # referans tut
                img_lbl.pack(padx=15, pady=(0, 10))
            except Exception:
                pass  # Görsel yüklenemezse sadece metin kalır

        # Glow animasyonu
        def glow():
            if card.winfo_exists():
                card.configure(border_color=ACCENT_BLUE)
                self.root.after(600, lambda: card.configure(border_color=ACCENT_DIM)
                                if card.winfo_exists() else None)
        glow()

    def display_chart_card(self, title: str, data: dict, chart_type: str = "bar"):
        """[10/10] Gerçek matplotlib grafik kartı oluştur. Thread-safe."""
        self.root.after(0, lambda: self._create_chart_card_ui(title, data, chart_type))

    

    def display_map_card(self, title: str, lat: float, lon: float, zoom: int = 13):
        """[MAP] Harita kartı oluştur. Thread-safe."""
        self.root.after(0, lambda: self._create_map_card_ui(title, lat, lon, zoom))

    def _create_map_card_ui(self, title: str, lat: float, lon: float, zoom: int):
        self.tabview.set("MISSION CONTROL")

        card = ctk.CTkFrame(self.card_container, fg_color=BG_CARD,
                            corner_radius=10, border_width=1, border_color=ACCENT_DIM)
        card.pack(fill="x", padx=10, pady=8, side="top")

        # Başlık
        header = tk.Frame(card, bg=BG_CARD)
        header.pack(fill="x", padx=15, pady=(12, 0))

        tk.Label(header, text=f"🗺 {title.upper()}",
                font=("Consolas", 11, "bold"),
                fg=ACCENT_BLUE, bg=BG_CARD).pack(side="left")

        ts = datetime.now().strftime("%H:%M")
        tk.Label(header, text=ts, font=("Consolas", 8),
                fg=TEXT_DIM, bg=BG_CARD).pack(side="right")

        tk.Frame(card, bg=ACCENT_DIM, height=1).pack(fill="x", padx=15, pady=(5, 0))

        # Koordinat bilgisi
        tk.Label(card, text=f"📍 {lat:.5f}, {lon:.5f}  —  zoom {zoom}",
                font=("Consolas", 9), fg=TEXT_DIM, bg=BG_CARD).pack(
                padx=15, pady=(6, 4), anchor="w")

        # Harita görüntüsü
        ctk_img = render_map_card(lat, lon, zoom)
        if ctk_img:
            img_lbl = ctk.CTkLabel(card, image=ctk_img, text="")
            img_lbl.image = ctk_img
            img_lbl.pack(padx=15, pady=(0, 12))
        else:
            # staticmap yoksa veya internet yoksa bilgi ver
            tk.Label(card, text="⚠ Harita yüklenemedi. (pip install staticmap)",
                    font=("Consolas", 9), fg="#FF6B35", bg=BG_CARD).pack(
                    padx=15, pady=(0, 12), anchor="w")

        # Glow
        def glow():
            if card.winfo_exists():
                card.configure(border_color=ACCENT_BLUE)
                self.root.after(600, lambda: card.configure(border_color=ACCENT_DIM)
                                if card.winfo_exists() else None)
        glow()











    def _create_chart_card_ui(self, title: str, data: dict, chart_type: str):
        self.tabview.set("MISSION CONTROL")

        card = ctk.CTkFrame(self.card_container, fg_color=BG_CARD,
                            corner_radius=10, border_width=1, border_color=ACCENT_DIM)
        card.pack(fill="x", padx=10, pady=8, side="top")

        # Başlık
        header = tk.Frame(card, bg=BG_CARD)
        header.pack(fill="x", padx=15, pady=(12, 0))

        type_icons = {"bar": "📊", "line": "📈", "pie": "🥧", "area": "🌊"}
        icon = type_icons.get(chart_type, "📊")

        tk.Label(header, text=f"{icon} {title.upper()}",
                 font=("Consolas", 11, "bold"),
                 fg=ACCENT_BLUE, bg=BG_CARD).pack(side="left")

        ts = datetime.now().strftime("%H:%M")
        tk.Label(header, text=ts, font=("Consolas", 8),
                 fg=TEXT_DIM, bg=BG_CARD).pack(side="right")

        tk.Frame(card, bg=ACCENT_DIM, height=1).pack(fill="x", padx=15, pady=(5, 0))

        # Grafik oluştur (Agg backend — thread-safe)
        ctk_img = render_chart(chart_type, data, title)

        if ctk_img and HAS_PIL:
            img_lbl = ctk.CTkLabel(card, image=ctk_img, text="")
            img_lbl.image = ctk_img
            img_lbl.pack(padx=15, pady=(8, 12))
        else:
            # Fallback: Pillow yoksa düz metin listesi
            labels = data.get("labels", [])
            values = data.get("values", [])
            fallback = "\n".join(f"  {l}: {v}" for l, v in zip(labels, values))
            tk.Label(card, text=fallback or str(data),
                     font=("Consolas", 10), fg=TEXT_MAIN, bg=BG_CARD,
                     justify="left", anchor="w").pack(padx=15, pady=(8, 12), anchor="w")

        # Glow
        def glow():
            if card.winfo_exists():
                card.configure(border_color=GREEN_OK)
                self.root.after(700, lambda: card.configure(border_color=ACCENT_DIM)
                                if card.winfo_exists() else None)
        glow()

    # ─────────────────────────────────────────────────────────────────────────
    # HAFIZA SEKMESİ — [10/10]
    # ─────────────────────────────────────────────────────────────────────────
    def _build_memory_panel(self, parent):
        """Canlı hafıza listesi + istatistik çubuğu + yenile butonu."""
        # Üst araç çubuğu
        toolbar = tk.Frame(parent, bg=BG_PANEL)
        toolbar.pack(fill="x", padx=12, pady=(10, 4))

        tk.Label(toolbar, text="🧠  HAFIZA YÖNETİMİ",
                 font=("Consolas", 10, "bold"),
                 fg=ACCENT_BLUE, bg=BG_PANEL).pack(side="left")

        self.mem_count_lbl = tk.Label(toolbar, text="0 kayıt",
                                      font=("Consolas", 9), fg=TEXT_DIM, bg=BG_PANEL)
        self.mem_count_lbl.pack(side="left", padx=14)

        ctk.CTkButton(
            toolbar, text="↻ Yenile",
            font=("Consolas", 10), height=28, width=80,
            fg_color=ACCENT_DIM, hover_color=ACCENT_BLUE,
            text_color=TEXT_MAIN,
            command=self._refresh_memory_panel
        ).pack(side="right")

        # İstatistik kutusu
        self.mem_stats_frame = tk.Frame(parent, bg=BG_CARD,
                                        highlightbackground=ACCENT_DIM, highlightthickness=1)
        self.mem_stats_frame.pack(fill="x", padx=12, pady=(0, 6))

        self.mem_stats_lbl = tk.Label(
            self.mem_stats_frame,
            text="İstatistikler yükleniyor...",
            font=("Consolas", 9), fg=TEXT_DIM, bg=BG_CARD,
            anchor="w", justify="left", padx=12, pady=6
        )
        self.mem_stats_lbl.pack(fill="x")

        # İstatistik grafiği (pasta)
        self.mem_chart_frame = tk.Frame(parent, bg=BG_CARD, highlightbackground=ACCENT_DIM, highlightthickness=1)
        self.mem_chart_frame.pack(pady=(4, 8), padx=12)
        self.mem_chart_lbl = ctk.CTkLabel(self.mem_chart_frame, text="", image=None)
        self.mem_chart_lbl.pack(padx=4, pady=4)

        # Hafıza listesi
        self.mem_list_frame = ctk.CTkScrollableFrame(
            parent, fg_color=BG_PANEL,
            label_text="", scrollbar_button_color=ACCENT_DIM
        )
        self.mem_list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _refresh_memory_panel(self):
        """Hafıza listesini ve istatistikleri yeniler."""
        if not (self.engine and hasattr(self.engine, 'memory') and self.engine.memory):
            self.mem_stats_lbl.configure(text="Motor henüz bağlı değil.")
            return

        threading.Thread(target=self._load_memory_data, daemon=True).start()

    def _load_memory_data(self):
        """Arka planda hafıza verilerini çeker, GUI thread'ine gönderir."""
        try:
            memories = self.engine.memory.get_display_memories(60)
            stats    = self.engine.memory.get_stats()
            self.root.after(0, lambda: self._render_memory_panel(memories, stats))
        except Exception as e:
            err_msg = str(e)
            self.root.after(0, lambda: self.mem_stats_lbl.configure(
                text=f"Hata: {err_msg}"
            ))

    def _render_memory_panel(self, memories: list, stats: dict):
        # Sayaç
        total = stats.get("total", 0)
        self.mem_count_lbl.configure(text=f"{total} kayıt")

        # İstatistik metni
        by_type = stats.get("by_type", {})
        avg_imp = stats.get("avg_importance", 0.0)
        type_labels = {"episodic": "Epizodik", "semantic": "Semantik",
                       "task": "Görev", "pattern_rule": "Kural"}
        stats_parts = [f"{type_labels.get(k, k)}: {v}" for k, v in by_type.items()]
        stats_text = "  |  ".join(stats_parts) + f"  |  Ort. Önem: {avg_imp:.2f}"
        self.mem_stats_lbl.configure(text=stats_text if stats_parts else "Henüz kayıt yok.")

        # Pasta grafiği (eğer veri varsa)
        if by_type and HAS_PIL:
            chart_data = {
                "labels": [type_labels.get(k, k) for k in by_type],
                "values": list(by_type.values())
            }
            ctk_img = render_pie_chart(chart_data, "Hafıza Dağılımı")
            if ctk_img:
                self.mem_chart_lbl.configure(image=ctk_img)
                self.mem_chart_lbl.image = ctk_img

        # Önceki satırları temizle
        for widget in self.mem_list_frame.winfo_children():
            widget.destroy()

        if not memories:
            tk.Label(self.mem_list_frame, text="Kayıtlı hafıza yok.",
                     font=("Consolas", 10), fg=TEXT_DIM, bg=BG_PANEL).pack(pady=20)
            return

        # Her hafıza için satır
        type_colors = {
            "episodic":    "#00C8FF",
            "semantic":    "#00E87A",
            "task":        "#FF6B35",
            "pattern_rule":"#9B59B6",
        }
        type_icons = {
            "episodic": "💬", "semantic": "📚", "task": "✅", "pattern_rule": "⚙"
        }

        for mem in memories:
            row = tk.Frame(self.mem_list_frame, bg=BG_CARD,
                           highlightbackground=ACCENT_DIM, highlightthickness=1)
            row.pack(fill="x", padx=4, pady=3)

            # Sol renk şeridi
            mtype = mem.get("memory_type", "semantic")
            stripe_color = type_colors.get(mtype, ACCENT_BLUE)
            tk.Frame(row, bg=stripe_color, width=3).pack(side="left", fill="y")

            # İçerik
            inner = tk.Frame(row, bg=BG_CARD)
            inner.pack(side="left", fill="both", expand=True, padx=(8, 8), pady=6)

            # Üst satır: tür ikonu + yaş + önem
            meta_row = tk.Frame(inner, bg=BG_CARD)
            meta_row.pack(fill="x")

            icon = type_icons.get(mtype, "•")
            tk.Label(meta_row, text=f"{icon} {mtype.upper()}",
                     font=("Consolas", 7, "bold"),
                     fg=stripe_color, bg=BG_CARD).pack(side="left")

            imp = mem.get("importance", 0.5)
            imp_bar = "█" * int(imp * 8) + "░" * (8 - int(imp * 8))
            tk.Label(meta_row, text=imp_bar,
                     font=("Consolas", 7),
                     fg=stripe_color, bg=BG_CARD).pack(side="left", padx=8)

            tk.Label(meta_row, text=mem.get("age_label", ""),
                     font=("Consolas", 7),
                     fg=TEXT_DIM, bg=BG_CARD).pack(side="right")

            # Metin
            text = mem.get("text", "")
            display_text = text[:120] + ("..." if len(text) > 120 else "")
            tk.Label(inner, text=display_text,
                     font=("Consolas", 9), fg=TEXT_MAIN, bg=BG_CARD,
                     wraplength=520, justify="left", anchor="w").pack(anchor="w", pady=(2, 0))

    # ─────────────────────────────────────────────────────────────────────────
    # TOAST BİLDİRİMİ — [10/10]  "Öğrendim ✓"
    # ─────────────────────────────────────────────────────────────────────────
    def _poll_toast(self):
        """Ana döngüye bağlı toast kuyruğu dinleyici."""
        if not self._toast_queue.empty() and not self._toast_visible:
            try:
                msg = self._toast_queue.get_nowait()
                self._show_toast(msg)
            except queue.Empty:
                pass
        self.root.after(200, self._poll_toast)

    def show_memory_toast(self, text: str, memory_type: str, importance: float):
        """
        [10/10] io_bridge üzerinden çağrılan hafıza bildirimi.
        Güvenli: GUI thread dışından çağrılabilir.
        """
        short = text[:45] + ("..." if len(text) > 45 else "")
        type_icons = {"episodic": "💬", "semantic": "📚", "task": "✅", "pattern_rule": "⚙"}
        icon = type_icons.get(memory_type, "🧠")
        msg = f"{icon}  Öğrendim ✓  — {short}"
        self._toast_queue.put(msg)

    def _show_toast(self, message: str):
        """Ekranın sağ alt köşesine 3 saniyelik toast bildirim penceresi."""
        self._toast_visible = True

        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=BG_CARD)

        try:
            toast.attributes("-alpha", 0.0)
        except Exception as e:
            logger.debug(f"GUI Error (toast alpha init): {e}")

        # İçerik
        frm = tk.Frame(toast, bg="#0D1E35",
                       highlightbackground=GREEN_OK, highlightthickness=1)
        frm.pack(padx=2, pady=2)

        tk.Label(frm, text=message,
                 font=("Consolas", 10), fg=GREEN_OK, bg="#0D1E35",
                 padx=16, pady=10).pack()

        # Konumlandır: sağ alt köşe
        toast.update_idletasks()
        tw = toast.winfo_width()
        th = toast.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        toast.geometry(f"+{sw - tw - 30}+{sh - th - 60}")

        # Fade in
        def fade_in(alpha=0.0):
            if alpha < 0.92:
                try:
                    toast.attributes("-alpha", alpha)
                except Exception as e:
                    logger.debug(f"GUI Error (toast fade_in): {e}")
                self.root.after(30, lambda: fade_in(alpha + 0.08))

        # Fade out + kapat
        def fade_out(alpha=0.92):
            if alpha > 0.0:
                try:
                    toast.attributes("-alpha", alpha)
                except Exception as e:
                    logger.debug(f"GUI Error (toast fade_out): {e}")
                self.root.after(40, lambda: fade_out(alpha - 0.08))
            else:
                toast.destroy()
                self._toast_visible = False

        fade_in()
        self.root.after(3000, fade_out)

    # ─────────────────────────────────────────────────────────────────────────
    # VISION STATUS GÜNCELLEMESI — [10/10]
    # ─────────────────────────────────────────────────────────────────────────
    def update_vision_status(self, summary: str, screenshot_path: str = None):
        """Watcher tarafından çağrılır — HUD'daki vision etiketini günceller."""
        short = summary[:80] + ("..." if len(summary) > 80 else "")
        self._last_vision_summary = summary
        self.root.after(0, lambda: self.vision_lbl.configure(
            text=short, fg="#77AABB"
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # LOG PANELİ
    # ─────────────────────────────────────────────────────────────────────────
    def _build_log_panel(self, parent):
        header = tk.Frame(parent, bg=BG_PANEL)
        header.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header, text="[ SİSTEM LOGLARI ]", font=("Consolas", 9),
                 fg=TEXT_DIM, bg=BG_PANEL).pack(side="left")
        tk.Button(header, text="Temizle", font=("Consolas", 8),
                  fg=TEXT_DIM, bg=BG_CARD, bd=0, relief="flat", cursor="hand2",
                  command=self._clear_logs).pack(side="right")

        self.log_box = tk.Text(parent, font=("Consolas", 11),
                               bg=BG_CARD, fg=TEXT_MAIN, wrap="word",
                               state="disabled", bd=0, relief="flat",
                               insertbackground=ACCENT_BLUE, selectbackground=ACCENT_DIM,
                               padx=10, pady=6)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        sb = tk.Scrollbar(self.log_box, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb.set)

        self.log_box.tag_configure("jarvis", foreground=LOG_JARVIS)
        self.log_box.tag_configure("user",   foreground=LOG_USER)
        self.log_box.tag_configure("error",  foreground=LOG_ERROR)
        self.log_box.tag_configure("error_bg", foreground="#FF8888", background="#3A1010") # Vurgulu Hata
        self.log_box.tag_configure("brain_bg", foreground="#77AABB", background="#0A1830") # Vurgulu Beyin Logu
        self.log_box.tag_configure("system", foreground=LOG_SYSTEM)
        self.log_box.tag_configure("ok",     foreground=LOG_OK)
        self.log_box.tag_configure("time",   foreground="#223344")

    # ─────────────────────────────────────────────────────────────────────────
    # ALT BAR
    # ─────────────────────────────────────────────────────────────────────────
    def _build_bottom_bar(self, parent):
        inner = tk.Frame(parent, bg=BG_PANEL)
        inner.pack(fill="both", expand=True, padx=14, pady=10)

        self.voice_lbl = tk.Label(inner,
                                  text="🎙  Sesli mod aktif — Konuşarak komut verebilirsiniz",
                                  font=("Consolas", 11), fg=TEXT_DIM, bg=BG_PANEL)
        self.voice_lbl.pack(side="left", expand=True)

        self.text_entry = ctk.CTkEntry(
            inner,
            placeholder_text="⌨  Komutunuzu yazın ve Enter'a basın...",
            font=("Consolas", 12), fg_color=BG_CARD,
            border_color=ACCENT_DIM, text_color=TEXT_MAIN, height=40
        )
        self.text_entry.bind("<Return>", self._send_text)

        self.send_btn = ctk.CTkButton(
            inner, text="GÖNDER →",
            font=("Consolas", 12, "bold"),
            fg_color=ACCENT_DIM, hover_color=ACCENT_BLUE,
            text_color=TEXT_MAIN, height=40, width=120,
            command=self._send_text
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ANİMASYON
    # ─────────────────────────────────────────────────────────────────────────
    def _animate(self):
        if not self._running:
            return

        canvas = self.canvas
        canvas.delete("all")

        cx, cy = 145, 122
        r_out = 96
        r_mid = 80
        r_in  = 62

        canvas.create_oval(cx - r_out, cy - r_out, cx + r_out, cy + r_out,
                          outline="#0A1830", width=1, fill=BG_PANEL)
        canvas.create_oval(cx - r_out - 6, cy - r_out - 6,
                           cx + r_out + 6, cy + r_out + 6,
                           outline=ACCENT_DIM, width=1)

        start = self._anim_angle % 360
        extent = 220 + 40 * math.sin(math.radians(self._anim_pulse))

        for offset, width, color in [(0, 7, "#00304A"), (0, 4, ACCENT_RING), (0, 2, ACCENT_BLUE)]:
            canvas.create_arc(
                cx - r_out + offset, cy - r_out + offset,
                cx + r_out - offset, cy + r_out - offset,
                start=start, extent=extent,
                style="arc", outline=color, width=width
            )

        canvas.create_arc(cx - r_mid, cy - r_mid, cx + r_mid, cy + r_mid,
                          start=(start + 150) % 360, extent=70,
                          style="arc", outline=ACCENT_DIM, width=2)
        canvas.create_oval(cx - r_in, cy - r_in, cx + r_in, cy + r_in,
                          outline="#0A2040", width=1)

        for i in range(24):
            angle_r = math.radians(i * 15)
            length = 8 if i % 6 == 0 else (5 if i % 3 == 0 else 3)
            col = ACCENT_BLUE if i % 6 == 0 else ACCENT_DIM
            x1 = cx + (r_out - 1) * math.cos(angle_r)
            y1 = cy - (r_out - 1) * math.sin(angle_r)
            x2 = cx + (r_out + length) * math.cos(angle_r)
            y2 = cy - (r_out + length) * math.sin(angle_r)
            canvas.create_line(x1, y1, x2, y2, fill=col, width=1)

        canvas.create_text(cx, cy - 14, text="J·A·R·V·I·S",
                          fill=ACCENT_BLUE, font=("Consolas", 13, "bold"))

        status_short, status_color = self._get_status_info()
        canvas.create_text(cx, cy + 8, text=status_short,
                          fill=status_color, font=("Consolas", 9))

        glow = 0.5 + 0.5 * math.sin(math.radians(self._anim_glow))
        led_color = self._lerp_color(ACCENT_DIM, ACCENT_BLUE, glow)
        for ax, ay in [(cx - r_out - 12, cy), (cx + r_out + 12, cy),
                       (cx, cy - r_out - 12), (cx, cy + r_out + 12)]:
            canvas.create_oval(ax - 3, ay - 3, ax + 3, ay + 3,
                              fill=led_color, outline="")

        speed = 3.0 if "DİNLİYOR" in self._status else 1.2
        self._anim_angle += speed
        self._anim_pulse += 3 * self._anim_dir
        if self._anim_pulse > 90 or self._anim_pulse < 0:
            self._anim_dir *= -1
        self._anim_glow += 2.5

        self.root.after(35, self._animate)

    def _lerp_color(self, c1, c2, t):
        try:
            r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
            r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
            return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"
        except Exception:
            return c1

    def _get_status_info(self):
        s = self._status.upper()
        if "DİNLİYOR" in s:   return "DİNLİYOR",     GREEN_OK
        if any(x in s for x in ["DÜŞÜNÜYOR", "İŞLENİYOR", "ÇALIŞIYOR"]):
            return "İŞLENİYOR", ORANGE
        if any(x in s for x in ["KONUŞUYOR", "DİKTE"]):   return "ÇALIŞIYOR",   ACCENT_BLUE
        if "BAŞLATILIYOR" in s: return "BAŞLATILIYOR", TEXT_DIM
        if any(x in s for x in ["YAZILI", "KOĞUL"]):      return "KOMUTU BEKLE", ORANGE
        return "HAZIR", ACCENT_DIM

    # ─────────────────────────────────────────────────────────────────────────
    # MOD GEÇİŞİ
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_mode(self):
        self.text_mode = bool(self.mode_switch.get())
        if self.engine:
            self.engine.text_mode = self.text_mode

        if self.text_mode:
            self.voice_lbl.pack_forget()
            self.text_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.send_btn.pack(side="right")
            self._update_status("⌨ YAZILI MOD")
            self._append_log("[GUI] Yazılı mod aktif.", "system")
        else:
            self.text_entry.pack_forget()
            self.send_btn.pack_forget()
            self.voice_lbl.pack(side="left", expand=True)
            self._update_status("🎙 SESLİ MOD")
            self._append_log("[GUI] Sesli mod aktif.", "system")
            if self.engine:
                self.engine.reset_audio()

    # ─────────────────────────────────────────────────────────────────────────
    # METİN GİRİŞİ
    # ─────────────────────────────────────────────────────────────────────────
    def _send_text(self, event=None):
        text = self.text_entry.get().strip()
        if not text:
            return
        self.text_entry.delete(0, "end")
        self._append_log(f"Sen (Yazılı): {text}", "user")
        self.root.after(0, lambda: self.last_cmd.configure(
            text=text[:55] + ("..." if len(text) > 55 else "")
        ))
        self.input_queue.put(text)

    # ─────────────────────────────────────────────────────────────────────────
    # LOG
    # ─────────────────────────────────────────────────────────────────────────
    def _redirect_stdout(self):
        sys.stdout = GUIStream(self._append_log_auto)

        class StderrStream(io.IOBase):
            def __init__(self, callback):
                self.callback = callback
                self._buf = ""
            def write(self, text):
                self._buf += text
                if "\n" in self._buf:
                    lines = self._buf.split("\n")
                    for line in lines[:-1]:
                        line_stripped = line.strip()
                        if line_stripped:
                            if any(x in line_stripped for x in ["Loading weights", "BertModel LOAD REPORT", "embeddings.position_ids", "UNEXPECTED", "HF_TOKEN", "unauthenticated requests", "huggingface.co", "Key                     | Status", "------------------------+", "Notes:", "can be ignored when loading"]):
                                continue
                            self.callback(f"[KRİTİK HATA] {line_stripped}")
                    self._buf = lines[-1]
                return len(text)
            def flush(self):
                if self._buf.strip():
                    if not any(x in self._buf for x in ["Loading weights", "BertModel", "UNEXPECTED", "HF_TOKEN", "Key                     | Status", "------------------------+", "Notes:"]):
                        self.callback(f"[KRİTİK HATA] {self._buf.strip()}")
                    self._buf = ""
        sys.stderr = StderrStream(self._append_log_auto)

    def _append_log_auto(self, text):
        t = text.strip()
        if not t:
            return
        tl = t.lower()

        if "sen (sesli):" in tl or "sen (yazılı):" in tl:
            tag = "user"
            content = t.split(":", 1)[-1].strip()
            self.root.after(0, lambda c=content: self.last_cmd.configure(
                text=c[:55] + ("..." if len(c) > 55 else "")
            ))
        elif "[j.a.r.v.i.s.]:" in tl and "hata" not in tl and "başarisiz" not in tl:
            tag = "jarvis"
            if "]: " in t:
                resp = t.split("]: ", 1)[-1]
                self.root.after(0, lambda r=resp: self.last_resp.configure(
                    text=r[:72] + ("..." if len(r) > 72 else "")
                ))
        elif "başarili" in tl:
            tag = "ok"
        elif "başarisiz" in tl or "hata" in tl or "error" in tl or "kritik" in tl:
            tag = "error_bg" if "[kritik hata]" in tl else "error"
        elif "[beyi̇n logu]" in tl or "[beyin logu]" in tl:
            tag = "brain_bg"
        elif "dinliyor" in tl:
            tag = "system"
            self.root.after(0, lambda: self._update_status("DİNLİYOR"))
        else:
            tag = "system"

        self.root.after(0, lambda: self._append_log(t, tag))

    def _append_log(self, text, tag="system"):
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{ts}] ", "time")
            self.log_box.insert("end", f"{text}\n", tag)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except Exception as e:
            logger.debug(f"GUI Error (log_box insert): {e}")

    def _clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ─────────────────────────────────────────────────────────────────────────
    # ENGINE BAŞLATMA
    # ─────────────────────────────────────────────────────────────────────────
    def _start_jarvis(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "jarvis_icon.ico"
        )
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception as e:
                logger.debug(f"GUI Error (icon loading): {e}")

        threading.Thread(target=self._check_autostart, daemon=True).start()

        def launch():
            async def _async_launch():
                try:
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    if project_root not in sys.path:
                        sys.path.insert(0, project_root)

                    from core.engine import ExecutionEngine
                    from core.config import EngineConfig

                    config = EngineConfig()
                    self.engine = ExecutionEngine(config)

                    self.engine.text_mode = self.text_mode
                    self.engine.text_input_queue = self.input_queue
                    self.engine.set_gui_callback(self._update_status)

                    try:
                        from audio.tts import TextToSpeech
                        tts = TextToSpeech()
                        self.engine.set_tts(tts.speak)
                    except Exception:
                        pass

                    try:
                        from audio.stt import SpeechToText
                        stt = SpeechToText()
                        self.engine.set_stt(stt.listen)
                        self.engine.set_stt_instance(stt)
                    except Exception:
                        pass

                    # [10/10] Tüm callback'leri bağla
                    self.engine.io_bridge.set_card_callback(self.display_card)
                    self.engine.io_bridge.set_chart_card_callback(self.display_chart_card)
                    self.engine.io_bridge.set_vision_status_callback(self.update_vision_status)
                    self.engine.io_bridge.set_memory_notify_callback(self.show_memory_toast)
                    self.engine.io_bridge.set_memory_refresh_callback(self._refresh_memory_panel)
                    self.engine.io_bridge.set_map_card_callback(self.display_map_card)

                    # [10/10] Hafıza kayıt callback'ini bağla
                    if hasattr(self.engine, 'memory') and self.engine.memory:
                        self.engine.memory.set_on_save_callback(
                            self.engine.io_bridge.notify_memory_saved
                        )

                    await self.engine.initialize()

                    # initialize() sonrası memory varsa callback'i tekrar bağla
                    if hasattr(self.engine, 'memory') and self.engine.memory:
                        self.engine.memory.set_on_save_callback(
                            self.engine.io_bridge.notify_memory_saved
                        )

                    self._append_log("[GUI] J.A.R.V.I.S. v2.0 motoru başlatıldı.", "ok")
                    self._update_status("DİNLİYOR")

                    # Hafıza sekmesini başlatılınca otomatik yükle
                    self.root.after(2000, self._refresh_memory_panel)

                    await self.engine.start()

                except Exception as e:
                    self._append_log(f"[KRİTİK HATA] Motor hatası: {e}", "error")

            import asyncio
            asyncio.run(_async_launch())

        threading.Thread(target=launch, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # AUTOSTART (mevcut logic korundu)
    # ─────────────────────────────────────────────────────────────────────────
    def _check_autostart(self):
        import time as _t
        config_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".jarvis_autostart"
        )
        if os.path.exists(config_file):
            return
        _t.sleep(6)
        self.root.after(0, self._show_autostart_dialog)

    def _show_autostart_dialog(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("J.A.R.V.I.S. — Başlangıç Ayarı")
        dialog.geometry("460x210")
        dialog.configure(fg_color=BG_PANEL)
        dialog.grab_set()
        dialog.resizable(False, False)
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 460) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 210) // 2
        dialog.geometry(f"+{x}+{y}")
        tk.Label(dialog, text="⬡  Otomatik Başlatma",
                 font=("Consolas", 14, "bold"), fg=ACCENT_BLUE, bg=BG_PANEL).pack(pady=(18, 6))
        tk.Label(dialog,
                 text="Efendim, her Windows açılışında size eşlik etmemi ister misiniz?",
                 font=("Consolas", 11), fg=TEXT_MAIN, bg=BG_PANEL, wraplength=400).pack(pady=8)
        btn_row = tk.Frame(dialog, bg=BG_PANEL)
        btn_row.pack(pady=14)
        def on_yes():
            dialog.destroy()
            self._setup_autostart()
        def on_no():
            config_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ".jarvis_autostart"
            )
            with open(config_file, "w") as f:
                f.write("declined")
            dialog.destroy()
        ctk.CTkButton(btn_row, text="✓  Evet, her zaman aktif ol",
                      font=("Consolas", 11, "bold"), fg_color=ACCENT_DIM,
                      hover_color=ACCENT_BLUE, text_color=TEXT_MAIN,
                      width=200, height=36, command=on_yes).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="✗  Hayır, gerek yok",
                      font=("Consolas", 11), fg_color="#1A0A0A",
                      hover_color="#3A1010", text_color="#AA6655",
                      width=160, height=36, command=on_no).pack(side="left", padx=8)

    def _setup_autostart(self):
        try:
            project_dir  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            launcher_pyw = os.path.join(project_dir, "launch_jarvis.pyw")
            icon_path    = os.path.join(project_dir, "assets", "jarvis_icon.ico")
            startup_paths = [
                os.path.join(os.environ.get('APPDATA', ''),
                             r"Microsoft\Windows\Start Menu\Programs\Startup"),
            ]
            import subprocess, sys as _sys
            pythonw = _sys.executable.replace("python.exe", "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = _sys.executable
            for startup in startup_paths:
                if not os.path.exists(startup):
                    continue
                lnk_path = os.path.join(startup, "JARVIS.lnk")
                ps = f'''
$ws = New-Object -ComObject WScript.Shell
$s  = $ws.CreateShortcut("{lnk_path}")
$s.TargetPath      = "{pythonw}"
$s.Arguments       = '"{launcher_pyw}"'
$s.WorkingDirectory = "{project_dir}"
$s.Description     = "J.A.R.V.I.S. AI Assistant"
'''
                if os.path.exists(icon_path):
                    ps += f'$s.IconLocation = "{icon_path}"\n'
                ps += "$s.Save()"
                subprocess.run(["powershell", "-Command", ps], capture_output=True, timeout=10)
            config_file = os.path.join(project_dir, ".jarvis_autostart")
            with open(config_file, "w") as f:
                f.write("enabled")
            self._append_log("[AUTOSTART] Kuruldu! Windows açılışında aktif olacak.", "ok")
        except Exception as e:
            self._append_log(f"[AUTOSTART HATA] {e}", "error")

    # ─────────────────────────────────────────────────────────────────────────
    # DURUM GÜNCELLEMESİ
    # ─────────────────────────────────────────────────────────────────────────
    def _update_status(self, status: str):
        self._status = status.upper()
        self.root.after(0, lambda: self.status_lbl.configure(text=f"● {self._status}"))
        if "FOCUS" in status:
            self.bring_to_front()
        if status.upper() == "KAPATILIYOR":
            self.root.after(800, self._on_close)

    def bring_to_front(self):
        try:
            target_title = "J.A.R.V.I.S. — Sistem Kontrol Merkezi"
            hwnd = win32gui.FindWindow(None, target_title)
            if hwnd:
                pyautogui.press('alt')
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(hwnd)
            self.root.attributes("-topmost", True)
            self.root.after(150, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception as e:
            print(f"[FOCUS_SHIELD] Pencere odağı engellendi: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # KAPATMA
    # ─────────────────────────────────────────────────────────────────────────
    def _on_close(self):
        self._running = False
        try:
            sys.stdout = sys.__stdout__
        except Exception:
            pass
        self.root.destroy()
        os._exit(0)

    def run(self):
        self.root.mainloop()


# ── Başlatıcı ─────────────────────────────────────────────────────────────────
def launch_gui():
    app = JarvisInterface()
    app.run()


if __name__ == "__main__":
    launch_gui()