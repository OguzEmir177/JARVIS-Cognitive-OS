"""[V10.5] J.A.R.V.I.S. Universal App Index

━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━

Universal application that finds EVERY application on the computer and opens it with fuzzy matching

application index.



Features:

    - Start Menu (system + user) scan

    - Desktop .lnk scanning

    - Windows Registry (App Paths) scan

    - Scan for .exe in PATH

    - UWP/Microsoft Store apps

    - Steam library scanning

    - Epic Games library scan

    - User-defined project folders

    - Fuzzy matching (difflib) + Turkish character normalization

    - Typo tolerance ("whatsap" → "WhatsApp")

    - Case insensitivity

    - Cache (fast after first scan)"""



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

# Turkish Character Normalization

# ─────────────────────────────────────────────────────────────────────────────



_TR_MAP = str.maketrans(
    "ğüşıöçĞÜŞİÖÇ",
    "gusiocGUSIOC"
)





def _normalize(text: str) -> str:

    """Lowercase + Turkish character normalize + remove spaces/hyphens."""

    text = text.lower().translate(_TR_MAP)

    text = re.sub(r"[\s\-_\.]+", "", text)

    return text





# ─────────────────────────────────────────────────────────────────────────────

#  Veri Modeli

# ─────────────────────────────────────────────────────────────────────────────



@dataclass

class AppEntry:

    """Represents a single application."""

    display_name: str          # Displayed name (e.g. "WhatsApp")

    launch_target: str         # Open path/command/URI

    launch_type: str           # "exe", "lnk", "uri", "uwp", "shell"

    source: str                # Where found (for log)

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

    """Returns the common starting length ratio of the query and the token.

    The fuzzy score is used as a multiplier to suppress false positives."""

    prefix_len = 0

    for a, b in zip(q, token):

        if a == b:

            prefix_len += 1

        else:

            break

    # If at least half of the queries have common prefixes, the full multiplier (1.0)

    # Otherwise it decreases by

    ratio = prefix_len / max(len(q), 1)

    return min(1.0, ratio * 2)  # 0.5 prefix rate → exactly 1.0 multiplier





# ─────────────────────────────────────────────────────────────────────────────

# User Defined Project/Shortcut Folders

# (add your own project shortcut folders here)

# ─────────────────────────────────────────────────────────────────────────────



_home = os.path.expanduser("~")

_USER_PROJECT_DIRS: list[str] = [

    os.path.join(_home, "OneDrive", "desktop", "Projeler"),

    os.path.join(_home, "OneDrive", "desktop"),

    os.path.join(_home, "Desktop"),

    os.path.join(_home, "Documents", "GitHub"),

    os.path.join(_home, "source", "repos"),

]



# Additional manual keyword matches — spelling variants

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

# Static fallback entries for known applications

# (package names may be different for Microsoft Store / UWP applications)

# ────────────────────────────────────────────────────────────────────────────────

_WELL_KNOWN_APPS: list[dict] = [

    # Microsoft Store / UWP protokol URI'leri

    {"name": "WhatsApp",  "target": "whatsapp:",

     "type": "uri", "kw": ["whatsap", "whatsup", "wp", "wattsapp"]},

    {"name": "Spotify",   "target": "spotify:",

     "type": "uri", "kw": ["spotifly", "spotfy"]},

    {"name": "Telegram",  "target": "tg:",

     "type": "uri", "kw": ["telegrem", "telgram"]},

    # Epic Games Launcher — can take many different paths, URI fallback

    {"name": "Epic Games", "target": "com.epicgames.launcher://",

     "type": "uri", "kw": ["epic", "epicgames", "epik", "epic games"]},

    # GitHub Desktop — may not have loaded, web fallback

    {"name": "GitHub",    "target": "https://github.com",

     "type": "uri", "kw": ["git hub", "githup", "gtihub", "github desktop"]},

    {"name": "YouTube", "target": "https://www.youtube.com", "type": "uri", "kw": ["youtube", "yt", "youtub"]},

    {"name": "Hesap Makinesi", "target": "calc.exe", "type": "exe", "kw": ["calc", "calculator", "hesapmakinesi", "hesap makinesi"]},

    {"name": "Chrome", "target": "chrome.exe", "type": "exe", "kw": ["google chrome", "krom", "scanner", "chrome"]},

]





# ─────────────────────────────────────────────────────────────────────────────

# Browsers

# ─────────────────────────────────────────────────────────────────────────────



def _scan_start_menu() -> list[AppEntry]:

    """Scans all .lnk files in the Start Menu."""

    entries: list[AppEntry] = []

    username = os.environ.get("USERNAME", "")

    paths = [

        r"C:\ProgramData\Microsoft\Windows\Start Menu",

        rf"C:\Users\{username}\AppData\Roaming\Microsoft\Windows\Start Menu",

    ]

    for base in paths:

        for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):

            name = Path(lnk).stem

            # Skip unwanted ones like Uninstaller/Uninstall

            low = name.lower()

            if any(x in low for x in ["uninstall", "remove", "remove", "help", "help",

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

    """Scans .lnk and .exe files on the desktop."""

    entries: list[AppEntry] = []

    username = os.environ.get("USERNAME", "")

    desktops = [

        rf"C:\Users\{username}\Desktop",

        rf"C:\Users\{username}\OneDrive\Desktop",

        r"C:\Users\Public\Desktop",

    ]

    for base in desktops:

        if not os.path.isdir(base):

            continue

        for ext in ("*.lnk", "*.exe"):

            for f in glob.glob(os.path.join(base, ext)):

                name = Path(f).stem

                low = name.lower()

                if any(x in low for x in ["uninstall", "remove", "remove"]):

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

    """Scans .lnk / .exe / .py files in user-defined project folders."""

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

        # Search for .lnk in subfolders as well (one level)

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

    """Scans applications from Windows Registry App Paths."""

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

    """Scans UWP/Microsoft Store apps with PowerShell."""

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

            # Get the last piece for the display name

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

        logger.debug(f"[AppIndex] UWP crawl error: {e}")

    logger.debug(f"[AppIndex] UWP: {len(entries)} uygulama")

    return entries





def _scan_steam() -> list[AppEntry]:

    """Scans games in the Steam library."""

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

            logger.debug(f"[AppIndex] Steam crawl error ({root}): {e}")

    logger.debug(f"[AppIndex] Steam: {len(entries)} oyun")

    return entries





def _scan_well_known() -> list[AppEntry]:

    """Adds static fallback entries for known applications."""

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

    """Scans games in the Epic Games library."""

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

            logger.debug(f"[AppIndex] Epic crawl error ({root}): {e}")

    logger.debug(f"[AppIndex] Epic: {len(entries)} oyun")

    return entries





def _find_main_exe(folder_path: str, folder_name: str) -> Optional[str]:

    """Finds the main .exe in a game folder (except crash/helper/uninstall)."""

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

            # Similarity score to main exe

            score = 0

            if folder_norm in name_norm or name_norm in folder_norm:

                score += 10

            # Proximity to root directory

            depth = len(Path(dirpath).relative_to(folder_path).parts)

            score -= depth

            candidates.append((score, exe_path))



    if not candidates:

        return None

    candidates.sort(key=lambda x: -x[0])

    return candidates[0][1]





# ─────────────────────────────────────────────────────────────────────────────

# App Launcher

# ─────────────────────────────────────────────────────────────────────────────



def _launch_entry(entry: AppEntry) -> bool:

    """Starts an AppEntry. True = successful."""

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

        logger.warning(f"[AppIndex] Launch error ({entry.display_name}): {e}")

        return False





# ─────────────────────────────────────────────────────────────────────────────

#  Ana Motor: UniversalAppIndex

# ─────────────────────────────────────────────────────────────────────────────



class UniversalAppIndex:

    """Engine that indexes all applications on the computer and finds them with fuzzy matching.



    Usage:

        result = UniversalAppIndex.instance().find_and_launch("github")

        # → “SUCCESS: GitHub Desktop opened.”"""



    _singleton: Optional["UniversalAppIndex"] = None

    _CACHE_TTL: float = 300.0   # 5 minutes cache



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

        """It scans all resources and creates the index."""

        if not force and not self._needs_rebuild():

            return



        logger.info("[AppIndex] Creating index...")

        t0 = time.time()

        entries: list[AppEntry] = []



        # Scan sequentially (Start Menu is the most reliable source)

        entries += _scan_start_menu()

        entries += _scan_desktop()

        entries += _scan_project_dirs()

        entries += _scan_registry()

        entries += _scan_steam()

        entries += _scan_epic()

        entries += _scan_well_known()  # statik fallback

        # UWP is a bit slow, leave it for last

        entries += _scan_uwp()



        # Remove duplicate display_names (on a normalized basis)

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

        """Fuzzy search. Returns a list of (score, entry) — score 0.0-1.0, high=good."""

        self.build_index()

        q_norm = _normalize(query)

        if not q_norm:

            return []



        results: list[tuple[float, AppEntry]] = []

        for entry in self._index:

            best_score = 0.0

            for token in entry.all_search_tokens:

                # Exact match

                if token == q_norm:

                    best_score = 1.0

                    break

                # Include: if the query is inside the token

                if q_norm in token:

                    contain_score = len(q_norm) / max(len(token), 1)

                    # Penalty for short tokens

                    if len(q_norm) >= 4:

                        contain_score = min(contain_score, 0.92)

                    best_score = max(best_score, contain_score)

                    continue

                # If token is in the query (partial name)

                if token in q_norm:

                    contain_score = len(token) / max(len(q_norm), 1)

                    best_score = max(best_score, min(contain_score, 0.85))

                    continue

                # difflib fuzzy — with prefix quality multiplier

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

        """Finds and starts the best match.



        Returns:

            "SUCCESSFUL: <name> opened." or "FAILED: <reason>"
    """

        self.build_index()

        matches = self.search(query, top_k=3)



        if not matches:

            logger.warning(f"[AppIndex] Not Found: '{query}'")

            # Last resort: direct shell

            try:

                subprocess.Popen(

                    f'start "" "{query}"',

                    shell=True, creationflags=0x08000000

                )

                return f"SUCCESSFUL: Tried with shell command '{query}'."

            except Exception as e:

                return f"FAILED: '{query}' not found — {e}"



        score, best = matches[0]

        logger.info(

            f"[AppIndex] Best match: '{best.display_name}'"

            f"(score={score:.2f}, source={best.source}, type={best.launch_type})"

        )



        if score < 0.70:

            # Uncertain — try anyway but log

            logger.warning(

                f"[AppIndex] Low trust score ({score:.2f}) →"

                f"'{best.display_name}' deneniyor."

            )



        ok = _launch_entry(best)

        if ok:

            return f"SUCCESSFUL: {best.display_name} opened."

        return f"FAILED: Failed to initialize {best.display_name}."



    def rebuild_async_safe(self) -> None:

        """If the TTL has expired, it rebuilds the index (for a thread-safe call)."""

        if self._needs_rebuild():

            self.build_index(force=True)





# ─────────────────────────────────────────────────────────────────────────────

# Convenience Function

# ─────────────────────────────────────────────────────────────────────────────



def find_and_launch(app_name: str) -> str:

    """Shortcut function for direct use."""

    return UniversalAppIndex.instance().find_and_launch(app_name)

