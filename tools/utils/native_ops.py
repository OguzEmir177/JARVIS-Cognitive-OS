"""
[V8.4 ARMORED] J.A.R.V.I.S. Native Operations
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Yerel sistem operasyonları (pyautogui, subprocess, psutil).

[V8.2] send_whatsapp_message Kritik Düzeltmeleri:
    ┌─────────────────────────────────────────────────────────────────┐
    │  KÖK NEDEN: os.system('start "" "whatsapp://...%XX..."')        │
    │                                                                 │
    │  os.system → cmd.exe → %C4%B1 → "%C4" ENV_VAR bulunamadı →    │
    │  silinir → URL bozulur → WhatsApp anlamsız/boş URL alır →      │
    │  anında hata                                                    │
    │                                                                 │
    │  ÇÖZÜM: webbrowser.open(url)                                    │
    │  Python → Windows Registry → ShellExecuteW API                  │
    │  cmd.exe hiç devreye GİRMEZ → %XX dizileri korunur             │
    └─────────────────────────────────────────────────────────────────┘

[V8.4] open_app Kritik Düzeltmeleri:
    - stderr debug print kaldırıldı (GUI'de sahte [KRİTİK HATA] üretiyordu)
    - pyautogui/pygetwindow lazy import (stderr gürültüsünü önler)
    - subprocess.Popen sonrası psutil ile süreç doğrulama eklendi
    - APP_MAP: epic games, whatsapp güncellendi
"""

import os
import sys
import time
import subprocess
import asyncio
import webbrowser
import urllib.parse
import logging

import psutil

# pyautogui ve pygetwindow: import sırasında stderr'e uyarı basabilir.
# GUI StderrStream bunu [KRİTİK HATA] olarak gösterir → lazy import.
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
    #  open_app  [V8.5 — Çok Katmanlı Strateji + Süreç Doğrulama]
    # ─────────────────────────────────────────────────────────────────────

    # Bilinen uygulama adı → çalıştırılabilir eşlemesi.
    # Değer str ise doğrudan kullanılır.
    # Değer list[str] ise sırayla os.path.exists ile kontrol edilir,
    # ilk bulunan yol kullanılır; hiçbiri yoksa listedeki son eleman denenir.
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

    # Popen sonrası psutil ile doğrulama yapılırken process listesinde
    # aranacak isimler. Küçük harfe çevrilip karşılaştırılır.
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
        """
        Popen çağrısından sonra sürecin gerçekten başlayıp başlamadığını
        psutil ile doğrular.

        Args:
            clean:  Kullanıcının girdiği normalize ad (lowercase).
            target: _APP_MAP'ten çözümlenmiş çalıştırılabilir ad.

        Returns:
            True  → process listesinde bulundu.
            False → bulunamadı.
        """
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
        """
        _APP_MAP'ten hedef çalıştırılabilir yolu çözümler.

        - str değer → doğrudan döner.
        - list[str] değer → sırayla os.path.exists kontrol eder,
          ilk bulunan yolu döner. Hiçbiri yoksa listedeki son elemanı döner.
        - MAP'te yoksa → clean (ham isim) döner.
        """
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
        # Hiçbiri yoksa son elemanı fallback olarak dön
        return entry[-1]

    @staticmethod
    def _find_in_registry(app_name: str) -> str:
        """
        [V8.5] APP_MAP'te bulunamayan uygulamalar için Windows Registry araması.
        """
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
        """
        [V10.5] Evrensel Uygulama Başlatıcı.
        UniversalAppIndex üzerinden fuzzy arama yapar;
        Start Menu, Desktop, Registry, Steam, Epic, UWP
        ve proje klasörlerini kapsar.
        """
        try:
            from tools.utils.app_index import UniversalAppIndex
            index = UniversalAppIndex.instance()
            matches = index.search(app_name, top_k=1)
            if not matches:
                return f"BAŞARISIZ: '{app_name}' bulunamadı."
            
            best = matches[0][1]
            from tools.utils.app_index import _launch_entry
            ok = _launch_entry(best)
            
            if ok:
                # Gerçek OS Doğrulaması
                time.sleep(1.5)
                # Kısayollar (.lnk) genelde pythonw.exe veya cmd.exe başlattığı için isim eşleşmez.
                # Bu yüzden .lnk dosyalarında katı süreç doğrulamasını (strict verification) atlıyoruz.
                if best.launch_type in ["exe", "uwp"]:
                    is_running = NativeOps._verify_process(best.display_name.lower(), best.launch_target)
                    if not is_running:
                        return f"BAŞARISIZ: {best.display_name} başlatıldı ancak çalışan bir süreç bulunamadı (Gerçek dışı başarı engellendi)."
                return f"BAŞARILI: {best.display_name} açıldı."
            return f"BAŞARISIZ: {best.display_name} başlatılamadı."
        except Exception as e:
            logger.error(f"[open_app] AppIndex hatası: {e}", exc_info=True)
            # Fallback: eski direkt shell yöntemi
            try:
                subprocess.Popen(f'start "" "{app_name}"', shell=True)
                return f"BAŞARILI: '{app_name}' shell ile denendi."
            except Exception as e2:
                return f"BAŞARISIZ: '{app_name}' başlatılamadı — {e2}"

    # ─────────────────────────────────────────────────────────────────────
    #  kill_app  (değişmedi)
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def kill_app(app_name: str) -> str:
        """Süreç sonlandırma mantığı (Safe-Kill kalkanı ile)."""
        clean = app_name.lower().strip()
        
        # KILL_MAP'te varsa o process adını kullan
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

        return "BAŞARILI" if killed else "BAŞARISIZ"

    # ─────────────────────────────────────────────────────────────────────
    #  send_whatsapp_message  [V8.2 ARMORED — tam yeniden yazım]
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    async def send_whatsapp_message(phone_number: str, message: str) -> bool:
        """
        [V8.2 ARMORED] WhatsApp mesaj gönderimi — whatsapp:// URL protokolü.

        Akış:
            1. Numara normalize (TR yerel → uluslararası 90XXXXXXXXXX)
            2. Mesaj metni URL encode  (safe='' → & ? # / dahil HEPSİ encode edilir)
            3. webbrowser.open(url)   → ShellExecuteW, cmd.exe BYPASS
            4. asyncio.sleep(5)       → WhatsApp Desktop yüklensin
            5. pyautogui.press('enter')→ Mesajı gönder
            6. True dön

        Neden webbrowser.open?
            os.system('start "" "url"') → cmd.exe → %XX → ENV_VAR arar → bulamazsa SİLER
            webbrowser.open(url)        → ShellExecuteW → % karakterleri KORUNUR

        Args:
            phone_number: Ham numara ("+905551234567", "05551234567", vb.)
            message:      Gönderilecek metin (Türkçe karakterler dahil her şey)

        Returns:
            True  → Akış tamamlandı, Enter basıldı
            False → Herhangi bir adımda exception (log'a yazıldı)
        """
        loop = asyncio.get_running_loop()

        try:
            # ── ADIM 1: Numara Temizlik & Normalize ──────────────────────────
            clean_number = "".join(filter(str.isdigit, phone_number))

            # TR yerel format: 05XXXXXXXXX → 905XXXXXXXXX
            if len(clean_number) == 11 and clean_number.startswith("0"):
                clean_number = "9" + clean_number
            # Yalnızca yerel hat: 5XXXXXXXXX → 905XXXXXXXXX
            elif len(clean_number) == 10 and clean_number.startswith("5"):
                clean_number = "90" + clean_number

            if len(clean_number) < 10:
                logger.error(
                    f"WhatsApp: Geçersiz numara formatı → '{phone_number}' → '{clean_number}'"
                )
                return False

            # ── ADIM 2: Mesaj URL Encode ──────────────────────────────────────
            # safe='' → boşluk, Türkçe harf, &, ?, #, / dahil TÜM özel
            # karakterler %XX biçimine dönüştürülür.
            #
            # Neden safe='' zorunlu?
            #   urllib.parse.quote varsayılanı safe='/' bırakır.
            #   WhatsApp mesajında '/' varsa URL parse edici bunu path
            #   ayracı sanabilir. safe='' ile bu risk sıfırlanır.
            encoded_msg = urllib.parse.quote(message, safe="")

            # ── ADIM 3: URL Oluştur & Tetikle (cmd.exe BYPASS) ───────────────
            url = f"whatsapp://send?phone={clean_number}&text={encoded_msg}"

            logger.info(
                f"[WhatsApp] URL tetikleniyor → phone={clean_number} "
                f"| mesaj uzunluğu={len(message)} karakter"
            )
            logger.debug(f"[WhatsApp] Ham URL: {url[:120]}...")

            # webbrowser.open:
            #   Windows'ta → winreg üzerinden ShellExecuteW çağrısına dönüşür.
            #   cmd.exe hiç devreye girmez → %XX dizileri WhatsApp'a tam iletilir.
            #
            # run_in_executor: webbrowser.open senkron bir çağrıdır; event loop
            # bloke olmasın diye thread pool'a gönderiyoruz.
            await loop.run_in_executor(None, webbrowser.open, url)

            # ── ADIM 4: Bekleme — WhatsApp Desktop yüklensin ─────────────────
            logger.info("[WhatsApp] Uygulama yüklenmesi için 6.5s bekleniyor...")
            await asyncio.sleep(6.5)

            # ── ADIM 5: Enter → Gönder ────────────────────────────────────────
            # pyautogui.press senkron/blocking → run_in_executor ile çağır.
            # Bazen WhatsApp metni doldurur ama odak (focus) gönderme tuşunda olmaz veya gecikir. 
            # Garantiye almak için iki kez Enter (arada 0.5s bekleme ile) gönderiyoruz.
            await loop.run_in_executor(None, pyautogui.press, "enter")
            await asyncio.sleep(0.5)
            await loop.run_in_executor(None, pyautogui.press, "enter")

            logger.info(f"[WhatsApp] Mesaj gönderildi → {clean_number}")
            return True

        except Exception as e:
            # exc_info=True → traceback log'a düşer, exception yutulmaz.
            logger.error(
                f"[WhatsApp] Kritik Hata: {e!r}",
                exc_info=True,
            )
            return False
