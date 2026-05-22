"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                 J.A.R.V.I.S. — Tek Tıkla Güncelleme Aracı                 ║
║                          (Git Gerektirmez)                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Bu script GitHub'daki en güncel J.A.R.V.I.S. kodlarını indirir ve        ║
║  yerel kurulumunuzu günceller.                                            ║
║                                                                            ║
║  KİŞİSEL VERİLERİNİZ KORUNUR:                                            ║
║    • .env (API anahtarlarınız)                                            ║
║    • contacts.json (kişi listeniz)                                        ║
║    • memory_db/ & jarvis_memory_db/ (hafıza veritabanları)                ║
║    • logs/ (günlük dosyaları)                                             ║
║    • Ses dosyaları (.mp3, .wav)                                           ║
║                                                                            ║
║  Kullanım: python update.py                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import shutil
import zipfile
import urllib.request
import urllib.error
import time
import datetime
import hashlib

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KONFİGÜRASYON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# GitHub repository bilgileri
GITHUB_USER = "oguzemirtopuz"
GITHUB_REPO = "JARVIS-Cognitive-OS"
GITHUB_BRANCH = "main"
DOWNLOAD_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"

# Proje kök dizini (bu dosyanın bulunduğu klasör)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ── DOKUNULMAZ DOSYA VE KLASÖRLER ──
# Bu listedeki dosya/klasörler ASLA güncellenmez veya silinmez.
# Kullanıcının kişisel verileri burada korunur.
PROTECTED_ITEMS = [
    # Kişisel veriler
    ".env",
    "contacts.json",

    # Hafıza veritabanları
    "memory_db",
    "jarvis_memory_db",
    "memory",

    # Loglar ve geçici dosyalar
    "logs",
    "errors",
    "debug.log",
    ".jarvis_autostart",

    # Ses cache dosyaları (kullanıcıya özel TTS sesleri)
    # .mp3 ve .wav dosyaları ayrıca uzantı bazlı korunur

    # Test ve büyük dump dosyaları
    "test_db",
    "test_db_2",
    "ai_studio_code.py",
    "Jarvis_Project_Full_Code.txt",
    "diff.txt",
    "diff_utf8.txt",
    "tree.txt",
    ".coverage",
    ".pytest_cache",
    "validation_output",
    "validation_reports",
    "validation",
    "PyWhatKit_DB.txt",
    "WHATSAPP_HATA.txt",
    "JARVIS_MEMORY.md.bak",

    # Git ve güncelleyici kendisi
    ".git",
    ".gitignore",
    "update.py",

    # Python cache
    "__pycache__",
]

# Bu uzantılara sahip dosyalar güncelleme ile DEĞİŞTİRİLMEZ
PROTECTED_EXTENSIONS = [".mp3", ".wav", ".db", ".sqlite3", ".log", ".pyc"]

# Yedekleme klasörü
BACKUP_DIR_NAME = "_jarvis_backup"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# YARDIMCI FONKSİYONLAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_banner():
    """Güncelleme başlığını yazdırır."""
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         🔄 J.A.R.V.I.S. Güncelleme Aracı v1.0             ║")
    print("║            Tek tıkla en güncel sürüme geç!                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


def print_step(step_num, total, message):
    """Adım bilgisi yazdırır."""
    bar = "█" * step_num + "░" * (total - step_num)
    print(f"  [{bar}] Adım {step_num}/{total}: {message}")


def print_success(message):
    print(f"  ✅ {message}")


def print_warning(message):
    print(f"  ⚠️  {message}")


def print_error(message):
    print(f"  ❌ {message}")


def print_info(message):
    print(f"  ℹ️  {message}")


def is_protected(relative_path: str) -> bool:
    """Bir dosya/klasörün korumalı olup olmadığını kontrol eder."""
    # Tam isim eşleşmesi (kök seviyede)
    top_level = relative_path.split(os.sep)[0]
    if top_level in PROTECTED_ITEMS:
        return True

    # Relative path'in kendisi korumalı mı
    if relative_path in PROTECTED_ITEMS:
        return True

    # Uzantı bazlı koruma
    _, ext = os.path.splitext(relative_path)
    if ext.lower() in PROTECTED_EXTENSIONS:
        return True

    # __pycache__ klasörleri her seviyede korunur
    parts = relative_path.split(os.sep)
    if "__pycache__" in parts:
        return True

    return False


def file_hash(filepath: str) -> str:
    """Dosyanın MD5 hash'ini hesaplar (değişim tespiti için)."""
    try:
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def download_with_progress(url: str, dest_path: str) -> bool:
    """URL'den dosya indirir ve ilerleme gösterir."""
    try:
        print_info(f"İndirme başlıyor: {url}")
        print()

        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Updater/1.0"})
        response = urllib.request.urlopen(req, timeout=60)

        total_size = response.headers.get("Content-Length")
        total_size = int(total_size) if total_size else None

        downloaded = 0
        block_size = 8192
        start_time = time.time()

        with open(dest_path, "wb") as f:
            while True:
                chunk = response.read(block_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                if total_size:
                    pct = downloaded / total_size * 100
                    elapsed = time.time() - start_time
                    speed = downloaded / (elapsed + 0.001) / 1024  # KB/s
                    bar_len = 30
                    filled = int(bar_len * downloaded / total_size)
                    bar = "█" * filled + "░" * (bar_len - filled)
                    size_mb = downloaded / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    sys.stdout.write(
                        f"\r  ⬇️  [{bar}] {pct:5.1f}% — {size_mb:.1f}/{total_mb:.1f} MB ({speed:.0f} KB/s)"
                    )
                    sys.stdout.flush()

        print()  # Yeni satır
        return True

    except urllib.error.URLError as e:
        print_error(f"İndirme hatası: {e}")
        return False
    except Exception as e:
        print_error(f"Beklenmeyen hata: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANA GÜNCELLEME MOTORU
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_update():
    """Ana güncelleme akışı."""
    print_banner()

    total_steps = 5
    stats = {"updated": 0, "added": 0, "skipped": 0, "protected": 0}

    # ─── ADIM 1: İnternet ve GitHub Bağlantı Kontrolü ───
    print_step(1, total_steps, "GitHub bağlantısı kontrol ediliyor...")
    try:
        test_req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}",
            headers={"User-Agent": "JARVIS-Updater/1.0"}
        )
        test_resp = urllib.request.urlopen(test_req, timeout=10)
        if test_resp.status == 200:
            print_success("GitHub bağlantısı başarılı.")
        else:
            print_error(f"GitHub yanıt kodu: {test_resp.status}")
            return False
    except Exception as e:
        print_error(f"GitHub'a bağlanılamıyor: {e}")
        print_info("İnternet bağlantınızı kontrol edin.")
        return False

    print()

    # ─── ADIM 2: En Güncel Sürümü İndir ───
    print_step(2, total_steps, "En güncel sürüm indiriliyor...")
    zip_path = os.path.join(PROJECT_ROOT, "_update_temp.zip")

    if not download_with_progress(DOWNLOAD_URL, zip_path):
        print_error("İndirme başarısız oldu.")
        return False

    print_success("İndirme tamamlandı.")
    print()

    # ─── ADIM 3: Mevcut Dosyaların Yedeğini Al ───
    print_step(3, total_steps, "Mevcut kod dosyalarının yedeği alınıyor...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(PROJECT_ROOT, BACKUP_DIR_NAME, f"backup_{timestamp}")

    try:
        os.makedirs(backup_dir, exist_ok=True)

        # Sadece güncellenecek dosyaları yedekle (korumalı olmayanları)
        backed_up = 0
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Yedekleme ve temp klasörlerini atla
            rel_root = os.path.relpath(root, PROJECT_ROOT)
            if rel_root.startswith(BACKUP_DIR_NAME) or rel_root.startswith("_update_"):
                continue

            for f in files:
                rel_path = os.path.relpath(os.path.join(root, f), PROJECT_ROOT)
                if not is_protected(rel_path):
                    src = os.path.join(root, f)
                    dst = os.path.join(backup_dir, rel_path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    backed_up += 1

        print_success(f"Yedekleme tamamlandı ({backed_up} dosya → {BACKUP_DIR_NAME}/backup_{timestamp}/)")
    except Exception as e:
        print_warning(f"Yedekleme sırasında hata (güncelleme devam ediyor): {e}")

    print()

    # ─── ADIM 4: Dosyaları Güncelle ───
    print_step(4, total_steps, "Dosyalar güncelleniyor...")
    extract_dir = os.path.join(PROJECT_ROOT, "_update_extract")

    try:
        # ZIP'i çıkar
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        # GitHub ZIP'leri "REPO-BRANCH/" şeklinde bir üst klasör içerir
        inner_dirs = os.listdir(extract_dir)
        if len(inner_dirs) == 1 and os.path.isdir(os.path.join(extract_dir, inner_dirs[0])):
            source_root = os.path.join(extract_dir, inner_dirs[0])
        else:
            source_root = extract_dir

        # Dosyaları karşılaştır ve güncelle
        for root, dirs, files in os.walk(source_root):
            rel_root = os.path.relpath(root, source_root)

            for f in files:
                if rel_root == ".":
                    rel_path = f
                else:
                    rel_path = os.path.join(rel_root, f)

                # Korumalı mı?
                if is_protected(rel_path):
                    stats["protected"] += 1
                    continue

                src_file = os.path.join(root, f)
                dst_file = os.path.join(PROJECT_ROOT, rel_path)

                # Hedef dosya var mı?
                if os.path.exists(dst_file):
                    # Hash karşılaştır — aynıysa atla
                    if file_hash(src_file) == file_hash(dst_file):
                        stats["skipped"] += 1
                        continue
                    else:
                        # Farklı → güncelle
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        stats["updated"] += 1
                        print(f"    📝 Güncellendi: {rel_path}")
                else:
                    # Yeni dosya → ekle
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    stats["added"] += 1
                    print(f"    🆕 Eklendi:     {rel_path}")

        print()
        print_success("Dosya güncellemesi tamamlandı.")

    except zipfile.BadZipFile:
        print_error("İndirilen dosya geçerli bir ZIP değil. Tekrar deneyin.")
        return False
    except Exception as e:
        print_error(f"Güncelleme sırasında hata: {e}")
        print_info(f"Yedek dosyalarınız: {backup_dir}")
        return False
    finally:
        # Geçici dosyaları temizle
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)

    print()

    # ─── ADIM 5: Sonuç Raporu ───
    print_step(5, total_steps, "Güncelleme raporu hazırlanıyor...")
    print()
    print("  ╔════════════════════════════════════════════════════════╗")
    print("  ║              📊 GÜNCELLEME RAPORU                     ║")
    print("  ╠════════════════════════════════════════════════════════╣")
    print(f"  ║  📝 Güncellenen dosyalar:  {stats['updated']:>4}                       ║")
    print(f"  ║  🆕 Yeni eklenen dosyalar: {stats['added']:>4}                       ║")
    print(f"  ║  ⏩ Zaten güncel (atlandı): {stats['skipped']:>4}                      ║")
    print(f"  ║  🛡️  Korunan kişisel veri:  {stats['protected']:>4}                       ║")
    print("  ╠════════════════════════════════════════════════════════╣")

    if stats["updated"] == 0 and stats["added"] == 0:
        print("  ║  ✨ Zaten en güncel sürümdesiniz!                     ║")
    else:
        total_changes = stats["updated"] + stats["added"]
        print(f"  ║  ✅ Toplam {total_changes} dosya başarıyla güncellendi!           ║")

    print("  ╚════════════════════════════════════════════════════════╝")
    print()
    print("  🛡️  Korunan verileriniz:")
    print("      • .env (API anahtarları)")
    print("      • contacts.json (kişiler)")
    print("      • memory_db/ (hafıza veritabanı)")
    print("      • logs/ (günlük dosyaları)")
    print("      • Ses dosyaları (.mp3, .wav)")
    print()

    # Eski yedekleri temizleme önerisi (3'ten fazla yedek varsa)
    backup_base = os.path.join(PROJECT_ROOT, BACKUP_DIR_NAME)
    if os.path.exists(backup_base):
        backups = sorted(os.listdir(backup_base))
        if len(backups) > 3:
            print_info(f"{len(backups)} yedek klasörünüz var. Eski yedekleri temizlemek için:")
            print(f"         Klasör: {backup_base}")
            print()

    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GİRİŞ NOKTASI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    try:
        success = run_update()

        if success:
            print("  🚀 J.A.R.V.I.S.'i yeniden başlatarak güncel sürümü kullanabilirsiniz.")
        else:
            print("  ⚠️  Güncelleme tamamlanamadı. Yukarıdaki hata mesajlarını kontrol edin.")

        print()
        input("  Çıkmak için Enter'a basın...")

    except KeyboardInterrupt:
        print("\n\n  ⛔ Güncelleme kullanıcı tarafından iptal edildi.")
    except Exception as e:
        print(f"\n  ❌ Kritik hata: {e}")
        input("\n  Çıkmak için Enter'a basın...")
