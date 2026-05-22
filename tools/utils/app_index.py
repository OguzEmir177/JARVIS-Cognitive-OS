"""
[V10.5] J.A.R.V.I.S. Universal App Index
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bilgisayardaki HER uygulamayı bulan ve fuzzy matching ile açan evrensel
uygulama indeksi.

Özellikler:
    - Start Menu (sistem + kullanıcı) taraması
    - Desktop .lnk taraması
    - Windows Registry (App Paths) taraması
    - PATH içindeki .exe taraması
    - UWP/Microsoft Store uygulamaları
    - Steam kütüphane taraması
    - Epic Games kütüphane taraması
    - Kullanıcı tanımlı proje klasörleri
    - Fuzzy matching (difflib) + Türkçe karakter normalizasyonu
    - Yazım hatası toleransı ("whatsap" → "WhatsApp")
    - Büyük/küçük harf duyarsızlığı
    - Önbellek (ilk taramadan sonra hızlı)
"""

from __future__ import annotations

import difflib
import glob
import json
import logging
import os
import re
import subprocess
import time
import winreg
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("JARVIS.AppIndex")

# ─────────────────────────────────────────────────────────────────────────────
#  Türkçe Karakter Normalizasyonu
# ─────────────────────────────────────────────────────────────────────────────

_TR_MAP = str.maketrans(
    "ğüşıöçĞÜŞİÖÇ",
    "gusiocgusioc"
)


def _normalize(text: str) -> str:
    """Lowercase + Türkçe karakter normalize + boşluk/tire kaldır."""
    text = text.lower().translate(_TR_MAP)
    text = re.sub(r"[\s\-_\.]+", "", text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
#  Veri Modeli
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AppEntry:
    """Tek bir uygulamayı temsil eder."""
    display_name: str          # Gösterilen ad (örn. "WhatsApp")
    launch_target: str         # Açılacak yol/komut/URI
    launch_type: str           # "exe", "lnk", "uri", "uwp", "shell"
    source: str                # Nereden bulundu (log için)
    keywords: list[str] = field(default_factory=list)  # Ek arama terimleri

    @property
    def normalized_name(self) -> str:
        return _normalize(self.display_name)

    @property
    def all_search_tokens(self) -> list[str]:
        tokens = [self.normalized_name]
        for kw in self.keywords:
            tokens.append(_normalize(kw))
        return tokens


def _prefix_quality(q: str, token: str) -> float:
    """Sorgu ile token'in ortak başlangıç uzunluğu oranını döndürür.
    False positive'leri baskılamak için fuzzy skoru çarpan olarak kullanılır."""
    prefix_len = 0
    for a, b in zip(q, token):
        if a == b:
            prefix_len += 1
        else:
            break
    # En az sorgunun yarısı kadarı ortak prefix varsa tam çarpan (1.0)
    # Aksi halde oranıyla azaltır
    ratio = prefix_len / max(len(q), 1)
    return min(1.0, ratio * 2)  # 0.5 prefix oranı → tam 1.0 çarpan


# ─────────────────────────────────────────────────────────────────────────────
#  Kullanıcı Tanımlı Proje/Shortcut Klasörleri
#  (buraya kendi proje kısayol klasörlerinizi ekleyin)
# ─────────────────────────────────────────────────────────────────────────────

_home = os.path.expanduser("~")
_USER_PROJECT_DIRS: list[str] = [
    os.path.join(_home, "OneDrive", "Masaüstü", "Projeler"),
    os.path.join(_home, "OneDrive", "Masaüstü"),
    os.path.join(_home, "Desktop"),
    os.path.join(_home, "Documents", "GitHub"),
    os.path.join(_home, "source", "repos"),
]

# Ek manuel keyword eşlemeleri — yazım varyantları
_KEYWORD_OVERRIDES: dict[str, list[str]] = {
    "whatsapp":     ["whatsap", "whatsup", "wp", "wattsapp"],
    "github":       ["git hub", "githup", "gtihub"],
    "discord":      ["discort", "discard", "discrod"],
    "spotify":      ["spotifly", "spotfy"],
    "telegram":     ["telegrem", "telgram"],
    "steam":        ["estim", "steem"],
    "epic games":   ["epic", "epicgames", "epik"],
    "epicgameslauncher": ["epic", "epicgames", "epik"],
    "visual studio code": ["vscode", "vs code", "vs kodu"],
    "notepad++":    ["notepad plus", "not defteri plus"],
    "chrome":       ["google chrome", "krom"],
    "firefox":      ["mozilla", "fierfox"],
    "edge":         ["microsoft edge", "kenari"],
    "obs studio":   ["obs", "screen recorder"],
    "vlc":          ["vlc media player", "video player"],
}

# ────────────────────────────────────────────────────────────────────────────────
# Bilinen uygulamalar için statik fallback girdileri
# (Microsoft Store / UWP uygulamaları için package isimleri farklı olabilir)
# ────────────────────────────────────────────────────────────────────────────────
_WELL_KNOWN_APPS: list[dict] = [
    # Microsoft Store / UWP protokol URI'leri
    {"name": "WhatsApp",  "target": "whatsapp:",
     "type": "uri", "kw": ["whatsap", "whatsup", "wp", "wattsapp"]},
    {"name": "Spotify",   "target": "spotify:",
     "type": "uri", "kw": ["spotifly", "spotfy"]},
    {"name": "Telegram",  "target": "tg:",
     "type": "uri", "kw": ["telegrem", "telgram"]},
    # Epic Games Launcher — çok farklı yollarda olabilir, URI fallback
    {"name": "Epic Games", "target": "com.epicgames.launcher://",
     "type": "uri", "kw": ["epic", "epicgames", "epik", "epic games"]},
    # GitHub Desktop — yüklenmemiş olabilir, web fallback
    {"name": "GitHub",    "target": "https://github.com",
     "type": "uri", "kw": ["git hub", "githup", "gtihub", "github desktop"]},
    {"name": "YouTube", "target": "https://www.youtube.com", "type": "uri", "kw": ["youtube", "yt", "youtub"]},
    {"name": "Hesap Makinesi", "target": "calc.exe", "type": "exe", "kw": ["calc", "calculator", "hesapmakinesi", "hesap makinesi"]},
    {"name": "Chrome", "target": "chrome.exe", "type": "exe", "kw": ["google chrome", "krom", "tarayıcı", "chrome"]},
]


# ─────────────────────────────────────────────────────────────────────────────
#  Tarayıcılar
# ─────────────────────────────────────────────────────────────────────────────

def _scan_start_menu() -> list[AppEntry]:
    """Start Menu'deki tüm .lnk dosyalarını tarar."""
    entries: list[AppEntry] = []
    username = os.environ.get("USERNAME", "")
    paths = [
        r"C:\ProgramData\Microsoft\Windows\Start Menu",
        rf"C:\Users\{username}\AppData\Roaming\Microsoft\Windows\Start Menu",
    ]
    for base in paths:
        for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
            name = Path(lnk).stem
            # Kaldırıcı/Uninstall gibi istenmeyen olanları atla
            low = name.lower()
            if any(x in low for x in ["uninstall", "kaldır", "remove", "help", "yardım",
                                        "readme", "setup", "install"]):
                continue
            entry = AppEntry(
                display_name=name,
                launch_target=lnk,
                launch_type="lnk",
                source="start_menu",
                keywords=_KEYWORD_OVERRIDES.get(name.lower(), []),
            )
            entries.append(entry)
    logger.debug(f"[AppIndex] Start Menu: {len(entries)} uygulama")
    return entries


def _scan_desktop() -> list[AppEntry]:
    """Masaüstündeki .lnk ve .exe dosyalarını tarar."""
    entries: list[AppEntry] = []
    username = os.environ.get("USERNAME", "")
    desktops = [
        rf"C:\Users\{username}\Desktop",
        rf"C:\Users\{username}\OneDrive\Masaüstü",
        r"C:\Users\Public\Desktop",
    ]
    for base in desktops:
        if not os.path.isdir(base):
            continue
        for ext in ("*.lnk", "*.exe"):
            for f in glob.glob(os.path.join(base, ext)):
                name = Path(f).stem
                low = name.lower()
                if any(x in low for x in ["uninstall", "kaldır", "remove"]):
                    continue
                entries.append(AppEntry(
                    display_name=name,
                    launch_target=f,
                    launch_type="lnk" if f.endswith(".lnk") else "exe",
                    source="desktop",
                    keywords=_KEYWORD_OVERRIDES.get(low, []),
                ))
    logger.debug(f"[AppIndex] Desktop: {len(entries)} uygulama")
    return entries


def _scan_project_dirs() -> list[AppEntry]:
    """Kullanıcı tanımlı proje klasörlerindeki .lnk / .exe / .py dosyalarını tarar."""
    entries: list[AppEntry] = []
    for base in _USER_PROJECT_DIRS:
        if not os.path.isdir(base):
            continue
        for ext in ("*.lnk", "*.exe"):
            for f in glob.glob(os.path.join(base, ext)):
                name = Path(f).stem
                entries.append(AppEntry(
                    display_name=name,
                    launch_target=f,
                    launch_type="lnk" if f.endswith(".lnk") else "exe",
                    source="project_dir",
                    keywords=_KEYWORD_OVERRIDES.get(name.lower(), []),
                ))
        # Alt klasörlerde de .lnk ara (bir seviye)
        try:
            for sub in os.scandir(base):
                if sub.is_dir():
                    for ext in ("*.lnk", "*.exe"):
                        for f in glob.glob(os.path.join(sub.path, ext)):
                            name = Path(f).stem
                            entries.append(AppEntry(
                                display_name=name,
                                launch_target=f,
                                launch_type="lnk" if f.endswith(".lnk") else "exe",
                                source="project_subdir",
                                keywords=_KEYWORD_OVERRIDES.get(name.lower(), []),
                            ))
        except PermissionError:
            pass
    logger.debug(f"[AppIndex] Project dirs: {len(entries)} uygulama")
    return entries


def _scan_registry() -> list[AppEntry]:
    """Windows Registry App Paths'ten uygulamaları tarar."""
    entries: list[AppEntry] = []
    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    for hive, path in reg_paths:
        try:
            key = winreg.OpenKey(hive, path)
            for i in range(winreg.QueryInfoKey(key)[0]):
                subkey_name = winreg.EnumKey(key, i)
                name = subkey_name.replace(".exe", "")
                try:
                    subkey = winreg.OpenKey(key, subkey_name)
                    exe_path, _ = winreg.QueryValueEx(subkey, "")
                    if exe_path and os.path.exists(exe_path):
                        low = name.lower()
                        if any(x in low for x in ["uninstall", "setup", "install"]):
                            continue
                        entries.append(AppEntry(
                            display_name=name,
                            launch_target=exe_path,
                            launch_type="exe",
                            source="registry",
                            keywords=_KEYWORD_OVERRIDES.get(low, []),
                        ))
                except Exception:
                    pass
        except Exception:
            pass
    logger.debug(f"[AppIndex] Registry: {len(entries)} uygulama")
    return entries


def _scan_uwp() -> list[AppEntry]:
    """UWP/Microsoft Store uygulamalarını PowerShell ile tarar."""
    entries: list[AppEntry] = []
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-AppxPackage | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=10, creationflags=0x08000000
        )
        for line in result.stdout.splitlines():
            name = line.strip()
            if not name or "." not in name:
                continue
            # Görünür ad için son parçayı al
            display = name.split(".")[-1]
            if any(x in display.lower() for x in ["runtime", "framework", "vclibs", "directx"]):
                continue
            entries.append(AppEntry(
                display_name=display,
                launch_target=f"shell:AppsFolder\\{name}_!App",
                launch_type="uwp",
                source="uwp",
                keywords=_KEYWORD_OVERRIDES.get(display.lower(), []),
            ))
    except Exception as e:
        logger.debug(f"[AppIndex] UWP tarama hatası: {e}")
    logger.debug(f"[AppIndex] UWP: {len(entries)} uygulama")
    return entries


def _scan_steam() -> list[AppEntry]:
    """Steam kütüphanesindeki oyunları tarar."""
    entries: list[AppEntry] = []
    drives = [f"{chr(d)}:\\\\" for d in range(65, 91) if os.path.exists(f"{chr(d)}:\\\\")]
    steam_roots = []
    for d in drives:
        steam_roots.extend([
            os.path.join(d, "Steam", "steamapps", "common"),
            os.path.join(d, "Program Files (x86)", "Steam", "steamapps", "common"),
            os.path.join(d, "Program Files", "Steam", "steamapps", "common"),
        ])
    for root in steam_roots:
        if not os.path.isdir(root):
            continue
        try:
            for folder in os.listdir(root):
                folder_path = os.path.join(root, folder)
                if not os.path.isdir(folder_path):
                    continue
                # Ana exe'yi bul
                best_exe = _find_main_exe(folder_path, folder)
                if best_exe:
                    entries.append(AppEntry(
                        display_name=folder,
                        launch_target=best_exe,
                        launch_type="exe",
                        source="steam_library",
                        keywords=_KEYWORD_OVERRIDES.get(folder.lower(), []),
                    ))
        except Exception as e:
            logger.debug(f"[AppIndex] Steam tarama hatası ({root}): {e}")
    logger.debug(f"[AppIndex] Steam: {len(entries)} oyun")
    return entries


def _scan_well_known() -> list[AppEntry]:
    """Bilinen uygulamalar için statik fallback girdilerini ekler."""
    entries: list[AppEntry] = []
    for app in _WELL_KNOWN_APPS:
        entries.append(AppEntry(
            display_name=app["name"],
            launch_target=app["target"],
            launch_type=app["type"],
            source="well_known",
            keywords=app.get("kw", []),
        ))
    return entries


def _scan_epic() -> list[AppEntry]:
    """Epic Games kütüphanesindeki oyunları tarar."""
    entries: list[AppEntry] = []
    drives = [f"{chr(d)}:\\\\" for d in range(65, 91) if os.path.exists(f"{chr(d)}:\\\\")]
    epic_roots = []
    for d in drives:
        epic_roots.extend([
            os.path.join(d, "Epic Games"),
            os.path.join(d, "Program Files", "Epic Games"),
            os.path.join(d, "Program Files (x86)", "Epic Games"),
        ])
    for root in epic_roots:
        if not os.path.isdir(root):
            continue
        try:
            for folder in os.listdir(root):
                if folder.lower() == "launcher":
                    continue
                folder_path = os.path.join(root, folder)
                if not os.path.isdir(folder_path):
                    continue
                best_exe = _find_main_exe(folder_path, folder)
                if best_exe:
                    entries.append(AppEntry(
                        display_name=folder,
                        launch_target=best_exe,
                        launch_type="exe",
                        source="epic_library",
                        keywords=_KEYWORD_OVERRIDES.get(folder.lower(), []),
                    ))
        except Exception as e:
            logger.debug(f"[AppIndex] Epic tarama hatası ({root}): {e}")
    logger.debug(f"[AppIndex] Epic: {len(entries)} oyun")
    return entries


def _find_main_exe(folder_path: str, folder_name: str) -> Optional[str]:
    """Bir oyun klasöründe ana .exe'yi bulur (crash/helper/uninstall hariç)."""
    folder_norm = _normalize(folder_name)
    candidates: list[tuple[int, str]] = []  # (skor, yol)

    for dirpath, _, files in os.walk(folder_path):
        for f in files:
            flow = f.lower()
            if not flow.endswith(".exe"):
                continue
            if any(x in flow for x in ["crash", "helper", "uninstall",
                                         "launcher_temp", "redist", "dxsetup",
                                         "vcredist", "setup"]):
                continue
            exe_path = os.path.join(dirpath, f)
            name_norm = _normalize(Path(f).stem)
            # Ana exe'ye benzerlik puanı
            score = 0
            if folder_norm in name_norm or name_norm in folder_norm:
                score += 10
            # Kök dizine yakınlık
            depth = len(Path(dirpath).relative_to(folder_path).parts)
            score -= depth
            candidates.append((score, exe_path))

    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


# ─────────────────────────────────────────────────────────────────────────────
#  Uygulama Başlatıcı
# ─────────────────────────────────────────────────────────────────────────────

def _launch_entry(entry: AppEntry) -> bool:
    """Bir AppEntry'yi başlatır. True = başarılı."""
    target = entry.launch_target
    ltype = entry.launch_type

    try:
        if ltype == "uwp":
            subprocess.Popen(
                f'explorer.exe "{target}"',
                shell=True, creationflags=0x08000000
            )
            return True

        elif ltype in ("lnk", "exe"):
            try:
                os.startfile(target)
                return True
            except Exception:
                subprocess.Popen(
                    f'start "" "{target}"',
                    shell=True, creationflags=0x08000000
                )
                return True

        elif ltype == "uri":
            import webbrowser
            webbrowser.open(target)
            return True

        elif ltype == "shell":
            subprocess.Popen(target, shell=True, creationflags=0x08000000)
            return True

        else:
            os.startfile(target)
            return True

    except Exception as e:
        logger.warning(f"[AppIndex] Launch hatası ({entry.display_name}): {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Ana Motor: UniversalAppIndex
# ─────────────────────────────────────────────────────────────────────────────

class UniversalAppIndex:
    """
    Bilgisayardaki tüm uygulamaları indeksleyen ve fuzzy matching ile bulan motor.

    Kullanım:
        result = UniversalAppIndex.instance().find_and_launch("github")
        # → "BAŞARILI: GitHub Desktop açıldı."
    """

    _singleton: Optional["UniversalAppIndex"] = None
    _CACHE_TTL: float = 300.0   # 5 dakika önbellek

    def __init__(self):
        self._index: list[AppEntry] = []
        self._built_at: float = 0.0

    @classmethod
    def instance(cls) -> "UniversalAppIndex":
        if cls._singleton is None:
            cls._singleton = cls()
        return cls._singleton

    def _needs_rebuild(self) -> bool:
        return not self._index or (time.time() - self._built_at) > self._CACHE_TTL

    def build_index(self, force: bool = False) -> None:
        """Tüm kaynakları tarayıp indeksi oluşturur."""
        if not force and not self._needs_rebuild():
            return

        logger.info("[AppIndex] İndeks oluşturuluyor...")
        t0 = time.time()
        entries: list[AppEntry] = []

        # Sırayla tara (Start Menu en güvenilir kaynak)
        entries += _scan_start_menu()
        entries += _scan_desktop()
        entries += _scan_project_dirs()
        entries += _scan_registry()
        entries += _scan_steam()
        entries += _scan_epic()
        entries += _scan_well_known()  # statik fallback
        # UWP biraz yavaş, en sona bırak
        entries += _scan_uwp()

        # Tekrar eden display_name'leri kaldır (normalized bazında)
        seen: set[str] = set()
        unique: list[AppEntry] = []
        for e in entries:
            key = e.normalized_name + "|" + e.launch_type
            if key not in seen:
                seen.add(key)
                unique.append(e)

        self._index = unique
        self._built_at = time.time()
        logger.info(
            f"[AppIndex] Indeks hazir: {len(self._index)} uygulama "
            f"({time.time() - t0:.2f}s)"
        )

    def search(self, query: str, top_k: int = 5) -> list[tuple[float, AppEntry]]:
        """
        Fuzzy search. (skor, entry) listesi döner — skor 0.0-1.0, yüksek=iyi.
        """
        self.build_index()
        q_norm = _normalize(query)
        if not q_norm:
            return []

        results: list[tuple[float, AppEntry]] = []
        for entry in self._index:
            best_score = 0.0
            for token in entry.all_search_tokens:
                # Tam eşleşme
                if token == q_norm:
                    best_score = 1.0
                    break
                # İçerme: sorgu token'in içindeyse
                if q_norm in token:
                    contain_score = len(q_norm) / max(len(token), 1)
                    # Kısa token'lar için ceza
                    if len(q_norm) >= 4:
                        contain_score = min(contain_score, 0.92)
                    best_score = max(best_score, contain_score)
                    continue
                # Token sorgunun içindeyse (kısmi ad)
                if token in q_norm:
                    contain_score = len(token) / max(len(q_norm), 1)
                    best_score = max(best_score, min(contain_score, 0.85))
                    continue
                # difflib fuzzy — prefix kalite çarpanı ile
                ratio = difflib.SequenceMatcher(None, q_norm, token).ratio()
                if ratio >= 0.60:
                    pq = _prefix_quality(q_norm, token)
                    adjusted = ratio * (0.5 + 0.5 * pq)  # prefix olmadan maks 0.5*ratio
                    best_score = max(best_score, adjusted)

            if best_score >= 0.58:
                results.append((best_score, entry))

        results.sort(key=lambda x: -x[0])
        return results[:top_k]

    def find_and_launch(self, query: str) -> str:
        """
        En iyi eşleşmeyi bulup başlatır.

        Returns:
            "BAŞARILI: <ad> açıldı." veya "BAŞARISIZ: <sebep>"
        """
        self.build_index()
        matches = self.search(query, top_k=3)

        if not matches:
            logger.warning(f"[AppIndex] Bulunamadı: '{query}'")
            # Son çare: direkt shell
            try:
                subprocess.Popen(
                    f'start "" "{query}"',
                    shell=True, creationflags=0x08000000
                )
                return f"BAŞARILI: '{query}' shell komutu ile denendi."
            except Exception as e:
                return f"BAŞARISIZ: '{query}' bulunamadı — {e}"

        score, best = matches[0]
        logger.info(
            f"[AppIndex] En iyi eşleşme: '{best.display_name}' "
            f"(skor={score:.2f}, kaynak={best.source}, tür={best.launch_type})"
        )

        if score < 0.70:
            # Belirsiz — yine de dene ama logla
            logger.warning(
                f"[AppIndex] Düşük güven skoru ({score:.2f}) → "
                f"'{best.display_name}' deneniyor."
            )

        ok = _launch_entry(best)
        if ok:
            return f"BAŞARILI: {best.display_name} açıldı."
        return f"BAŞARISIZ: {best.display_name} başlatılamadı."

    def rebuild_async_safe(self) -> None:
        """TTL süresi dolmuşsa index'i yeniden oluşturur (thread-safe çağrı için)."""
        if self._needs_rebuild():
            self.build_index(force=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Kolaylık Fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────

def find_and_launch(app_name: str) -> str:
    """Doğrudan kullanım için kısayol fonksiyon."""
    return UniversalAppIndex.instance().find_and_launch(app_name)
