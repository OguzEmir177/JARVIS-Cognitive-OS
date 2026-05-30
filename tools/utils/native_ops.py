"""[V8.4 ARMORED] J.A.R.V.I.S. Native Operations
━━━━━━━━━━━━━━━━━━━━━━━ ━━━━━━━━━━━━━━━━━━━━━━━
Local system operations (pyautogui, subprocess, psutil).

[V8.2] send_whatsapp_message Critical Fixes:
    ┌──────────────────────────────── ─────────────────────────────────┐
    │ ROOT CAUSE: os.system('start "" "whatsapp://...%XX..."') │
    │ │
    │ os.system → cmd.exe → %C4%B1 → ENV_VAR "%C4" not found → │
    │ deleted → URL broken → WhatsApp gets meaningless/empty URL → │
    │ immediate error │
    │ │
    │ SOLUTION: webbrowser.open(url) │
    │ Python → Windows Registry → ShellExecuteW API │
    │ cmd.exe does NOT run at all → XX% arrays are preserved │
    └──────────────────────────────── ─────────────────────────────────┘

[V8.4] open_app Critical Fixes:
    - Removed stderr debug print (was producing spurious [CRITICAL ERROR] in GUI)
    - pyautogui/pygetwindow lazy import (prevents stderr noise)
    - Added process validation with psutil after subprocess.Popen
    - APP_MAP: epic games, whatsapp updated"""

import os
import sys
import time
import subprocess
import asyncio
import webbrowser
import urllib.parse
import logging

import psutil

# pyautogui and pygetwindow: Can print warning to stderr during import.
# GUI StderrStream shows this as [CRITICAL ERROR] → lazy import.
try:
    import pyautogui
except ImportError:
    pyautogui = None  # type: ignore[assignment]

try:
    import pygetwindow as gw  # noqa: F401
except ImportError:
    gw = None  # type: ignore[assignment]

logger = logging.getLogger("JARVIS.NativeOps")


class NativeOps:
    """
    J.A.R.V.I.S. v8.2 Yerel Operasyonlar (pyautogui, subprocess, psutil).
    """

    # ─────────────────────────────────────────────────────────────────────
    # open_app [V8.5 — Multi-Layered Strategy + Process Validation]
    # ─────────────────────────────────────────────────────────────────────

    # Known application name → executable mapping.
    # If the value is str, it is used directly.
    # If the value is list[str], it is checked with os.path.exists in turn,
    # the first path found is used; If none, the last element in the list is tried.
    _APP_MAP: dict[str, str | list[str]] = {
        "discord":      "discord",
        "spotify":      "spotify",
        "chrome":       "chrome",
        "firefox":      "firefox",
        "notepad":      "notepad",
        "explorer":     "explorer",
        "whatsapp":     "STORE:whatsapp",
        "telegram":     "telegram",
        "vscode":       "code",
        "vs code":      "code",
        "epic games":   [
            r"D:\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
            r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
            r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
            r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        ],
        "epic":         [
            r"D:\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
            r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
            r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
            r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
        ],
    }

    # While verifying with psutil after Popen, in the process list
    # names to search for. It is converted to lowercase and compared.
    _PROCESS_NAMES: dict[str, str] = {
        "discord":      "discord",
        "spotify":      "spotify",
        "chrome":       "chrome",
        "firefox":      "firefox",
        "notepad":      "notepad",
        "explorer":     "explorer",
        "whatsapp":     "whatsapp",
        "telegram":     "telegram",
        "vscode":       "code",
        "vs code":      "code",
        "epic games":   "epicgameslauncher",
        "epic":         "epicgameslauncher",
    }

    _KILL_MAP: dict[str, str] = {
        "epic games": "epicgameslauncher",
        "epic": "epicgameslauncher", 
        "steam": "steam",
        "spotify": "spotify",
        "discord": "discord",
        "chrome": "chrome",
        "firefox": "firefox",
        "whatsapp": "whatsapp.root",
        "telegram": "telegram",
        "vscode": "code",
        "vs code": "code",
        "rocket league": "rocketleague",
        "rl": "rocketleague",
        "fall guys": "fallguys",
        "fallguys": "fallguys",
    }

    @staticmethod
    def _verify_process(clean: str, target: str) -> bool:
        """Whether the process actually started after the Popen call
        Confirms with psutil.

        Args:
            clean: The normalized name (lowercase) entered by the user.
            target: executable name parsed from _APP_MAP.

        Returns:
            True → found in the process list.
            False → not found."""
        # Aranacak aday isimleri belirle
        search_name = NativeOps._PROCESS_NAMES.get(clean, clean).lower()
        if target:
            import os
            target_name = os.path.basename(target).replace(".exe", "").lower()
            if target_name:
                search_name = target_name

        for proc in psutil.process_iter(["name"]):
            try:
                p_name = proc.info["name"].lower()
                if search_name in p_name or clean in p_name:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    @staticmethod
    def _resolve_app_map(clean: str) -> str:
        """Parses the target executable path from _APP_MAP.

        - str value → returns directly.
        - list[str] value → checks os.path.exists in order,
          Returns the first path found. If there is none, it returns the last element in the list.
        - If it is not in the MAP → clean (raw name) is returned."""
        entry = NativeOps._APP_MAP.get(clean)
            
        if entry is None:
            return clean
        if isinstance(entry, str):
            return entry
        # list[str] — ilk mevcut yolu bul
        for path in entry:
            if os.path.exists(path):
                logger.debug(f"[open_app] Dinamik yol bulundu: {path}")
                return path
        # If none, return the last element as fallback
        return entry[-1]

    @staticmethod
    def _find_in_registry(app_name: str) -> str:
        """[V8.5] Windows Registry search for applications not found in APP_MAP."""
        import winreg
        paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]
        for base in paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base + "\\" + app_name + ".exe")
                path, _ = winreg.QueryValueEx(key, "")
                if path and os.path.exists(path):
                    return path
            except:
                continue
        return ""

    @staticmethod
    def open_app(app_name: str) -> str:
        """[V10.5] Universal App Launcher.
        Performs fuzzy searches via UniversalAppIndex;
        Start Menu, Desktop, Registry, Steam, Epic, UWP
        and project folders."""
        try:
            from tools.utils.app_index import UniversalAppIndex
            index = UniversalAppIndex.instance()
            matches = index.search(app_name, top_k=1)
            if not matches:
                return f"FAILED: '{app_name}' not found."
            
            best = matches[0][1]
            from tools.utils.app_index import _launch_entry
            ok = _launch_entry(best)
            
            if ok:
                # Real OS Verification
                time.sleep(1.5)
                # The name does not match because shortcuts (.lnk) usually start pythonw.exe or cmd.exe.
                # That's why we skip strict verification in .lnk files.
                if best.launch_type in ["exe", "uwp"]:
                    is_running = NativeOps._verify_process(best.display_name.lower(), best.launch_target)
                    if not is_running:
                        return f"FAILED: {best.display_name} was started but no running process was found (Unreal success blocked)."
                return f"SUCCESSFUL: {best.display_name} opened."
            return f"FAILED: Failed to initialize {best.display_name}."
        except Exception as e:
            logger.error(f"[open_app] AppIndex error: {e}", exc_info=True)
            # Fallback: old direct shell method
            try:
                subprocess.Popen(f'start "" "{app_name}"', shell=True)
                return f"SUCCESSFUL: Tried with shell '{app_name}'."
            except Exception as e2:
                return f"FAILED: Failed to initialize '{app_name}' — {e2}"

    # ─────────────────────────────────────────────────────────────────────
    # kill_app (unchanged)
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def kill_app(app_name: str) -> str:
        """Process termination logic (with Safe-Kill shield)."""
        clean = app_name.lower().strip()
        
        # Use that process name if present in KILL_MAP
        process_target = NativeOps._KILL_MAP.get(clean, clean)
        
        killed = False

        # Safe-Kill Beyaz Listesi
        whitelist = ["jarvis", "python", "code", "terminal", "cmd", "powershell"]

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                p_name = proc.info["name"].lower()
                if any(w in p_name for w in whitelist):
                    continue
                if process_target in p_name:
                    proc.kill()
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return "SUCCESSFUL" if killed else "UNSUCCESSFUL"

    # ─────────────────────────────────────────────────────────────────────
    # send_whatsapp_message [V8.2 ARMORED — full rewrite]
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    async def send_whatsapp_message(phone_number: str, message: str) -> bool:
        """[V8.2 ARMORED] WhatsApp message sending — whatsapp:// URL protocol.

        Stream:
            1. Number normalized (TR local → international 90XXXXXXXXXX)
            2. Message text URL encode (ALL encoded including safe='' → & ? # /)
            3. webbrowser.open(url) → ShellExecuteW, cmd.exe BYPASS
            4. asyncio.sleep(5) → Install WhatsApp Desktop
            5. pyautogui.press('enter')→ Send message
            6. Return true

        Why webbrowser.open?
            os.system('start "" "url"') → cmd.exe → XX% → searches for ENV_VAR → DELETE if not found
            webbrowser.open(url) → ShellExecuteW → % characters are RETAINED

        Args:
            phone_number: Raw number ("+905551234567", "05551234567", etc.)
            message: Text to send (everything including Turkish characters)

        Returns:
            True → Stream completed, Enter pressed
            False → Exception at any step (written to log)"""
        loop = asyncio.get_running_loop()

        try:
            # ── ADIM 1: Numara Temizlik & Normalize ──────────────────────────
            clean_number = "".join(filter(str.isdigit, phone_number))

            # TR yerel format: 05XXXXXXXXX → 905XXXXXXXXX
            if len(clean_number) == 11 and clean_number.startswith("0"):
                clean_number = "9" + clean_number
            # Local line only: 5XXXXXXXXXX → 905XXXXXXXXXX
            elif len(clean_number) == 10 and clean_number.startswith("5"):
                clean_number = "90" + clean_number

            if len(clean_number) < 10:
                logger.error(
                    f"WhatsApp: Invalid number format → '{phone_number}' → '{clean_number}'"
                )
                return False

            # ── ADIM 2: Mesaj URL Encode ──────────────────────────────────────
            # safe='' → ALL special including space, Turkish letter, &, ?, #, /
            # characters are converted to %XX.
            #
            # Neden safe='' zorunlu?
            # urllib.parse.quote leaves the default safe='/'.
            # If there is '/' in the WhatsApp message, the URL parser will convert it to path
            # # It may be mistaken for a # separator. With safe='' this risk is reset.
            encoded_msg = urllib.parse.quote(message, safe="")

            # ── STEP 3: Create & Trigger URL (cmd.exe BYPASS) ───────────────
            url = f"whatsapp://send?phone={clean_number}&text={encoded_msg}"

            logger.info(
                f"[WhatsApp] URL tetikleniyor → phone={clean_number} "
                f"| message length={len(message)} characters"
            )
            logger.debug(f"[WhatsApp] Ham URL: {url[:120]}...")

            # webbrowser.open:
            # On Windows → becomes a ShellExecuteW call via winreg.
            # cmd.exe is not activated at all → XX% strings are fully transmitted to WhatsApp.
            #
            # run_in_executor: webbrowser.open is a synchronous call; event loop
            # We send it to the thread pool so it doesn't get blocked.
            await loop.run_in_executor(None, webbrowser.open, url)

            # ── STEP 4: Wait — Install WhatsApp Desktop ─────────────────
            logger.info("[WhatsApp] Waiting 10 seconds for application to load...")
            await asyncio.sleep(8.0)

            # ── STEP 5: Focus Window and Enter → Send ────────────────────
            # If the application is newly opened, it may take time for the text to drop from the URL into the box.
            # We try to bring it to the fore.
            if gw:
                try:
                    windows = gw.getWindowsWithTitle("WhatsApp")
                    if windows:
                        win = windows[0]
                        if getattr(win, "isMinimized", False):
                            win.restore()
                        win.activate()
                        await asyncio.sleep(1.0)
                except Exception as e:
                    logger.debug(f"[WhatsApp] Window focus skipped: {e}")
            else:
                await asyncio.sleep(2.0)

            # call pyautogui.press synchronous/blocking → run_in_executor.
            # It may be delayed for the text to fill or for the interface to react.
            # To guarantee, we press Enter 3 times at intervals.
            for _ in range(3):
                await loop.run_in_executor(None, pyautogui.press, "enter")
                await asyncio.sleep(1.0)

            logger.info(f"[WhatsApp] Message sent → {clean_number}")
            return True

        except Exception as e:
            # exc_info=True → traceback is recorded in the log, exception is not swallowed.
            logger.error(
                f"[WhatsApp] Critical Error: {e!r}",
                exc_info=True,
            )
            return False
