"""╔═══════════════════ ════════════════════ ════════════════════ ═══════════════════╗
║ J.A.R.V.I.S. — One-Click Update Tool ║
║ (No Git Required) ║
╠═══════════════════ ════════════════════ ════════════════════ ═══════════════════╣
║ This script contains the latest J.A.R.V.I.S. on GitHub. downloads the codes and ║
║ updates your local installation.                                            ║
║ ║
║ YOUR PERSONAL DATA IS PROTECTED: ║
║ • .env (your API keys) ║
║ • contacts.json (your contact list) ║
║ • memory_db/ & jarvis_memory_db/ (memory databases) ║
║ • logs/ (log files) ║
║ • Audio files (.mp3, .wav) ║
║ ║
║ Usage: python update.py ║
╚═══════════════════ ════════════════════ ════════════════════ ═══════════════════╝"""

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
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# GitHub repository bilgileri
GITHUB_USER = "oguzemirtopuz"
GITHUB_REPO = "JARVIS-Cognitive-OS"
GITHUB_BRANCH = "main"
DOWNLOAD_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"

# Project root directory (the folder where this file is located)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ── UNTOUCHABLE FILES AND FOLDERS ──
# Files/folders in this list are NEVER updated or deleted.
# The user's personal data is protected here.
PROTECTED_ITEMS = [
    # Personal data
    ".env",
    "contacts.json",

    # Memory databases
    "memory_db",
    "jarvis_memory_db",
    "memory",

    # Logs and temporary files
    "logs",
    "errors",
    "debug.log",
    ".jarvis_autostart",

    # Voice cache files (user-specific TTS voices)
    # .mp3 and .wav files are also protected based on extension

    # Test and large dump files
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

    # Git and the updater itself
    ".git",
    ".gitignore",
    "update.py",

    # Python cache
    "__pycache__",
]

# Files with these extensions will NOT be changed by the update
PROTECTED_EXTENSIONS = [".mp3", ".wav", ".db", ".sqlite3", ".log", ".pyc"]

# Backup folder
BACKUP_DIR_NAME = "_jarvis_backup"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUXILIARY FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_banner():
    """Prints the update header."""
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║ 🔄 J.A.R.V.I.S. Update Tool v1.0 ║")
    print("║ Switch to the latest version with one click!                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()


def print_step(step_num, total, message):
    """Prints step information."""
    bar = "█" * step_num + "░" * (total - step_num)
    print(f"[{bar}] Step {step_num}/{total}: {message}")


def print_success(message):
    print(f"  ✅ {message}")


def print_warning(message):
    print(f"  ⚠️  {message}")


def print_error(message):
    print(f"  ❌ {message}")


def print_info(message):
    print(f"  ℹ️  {message}")


def is_protected(relative_path: str) -> bool:
    """Checks whether a file/folder is protected or not."""
    # Exact name match (at root level)
    top_level = relative_path.split(os.sep)[0]
    if top_level in PROTECTED_ITEMS:
        return True

    # Is the relative path itself protected?
    if relative_path in PROTECTED_ITEMS:
        return True

    # Extension based protection
    _, ext = os.path.splitext(relative_path)
    if ext.lower() in PROTECTED_EXTENSIONS:
        return True

    # __pycache__ folders are protected at all levels
    parts = relative_path.split(os.sep)
    if "__pycache__" in parts:
        return True

    return False


def file_hash(filepath: str) -> str:
    """Calculates the MD5 hash of the file (for change detection)."""
    try:
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def download_with_progress(url: str, dest_path: str) -> bool:
    """It downloads files from the URL and shows progress."""
    try:
        print_info(f"Download starts: {url}")
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

        print()  # new line
        return True

    except urllib.error.URLError as e:
        print_error(f"Download error: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN UPDATE ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_update():
    """Main update stream."""
    print_banner()

    total_steps = 5
    stats = {"updated": 0, "added": 0, "skipped": 0, "protected": 0}

    # ─── STEP 1: Internet and GitHub Connection Check ───
    print_step(1, total_steps, "Checking GitHub link...")
    try:
        test_req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}",
            headers={"User-Agent": "JARVIS-Updater/1.0"}
        )
        test_resp = urllib.request.urlopen(test_req, timeout=10)
        if test_resp.status == 200:
            print_success("GitHub connection successful.")
        else:
            print_error(f"GitHub response code: {test_resp.status}")
            return False
    except Exception as e:
        print_error(f"Unable to connect to GitHub: {e}")
        print_info("Check your internet connection.")
        return False

    print()

    # ─── STEP 2: Download Latest Version ───
    print_step(2, total_steps, "Downloading the latest version...")
    zip_path = os.path.join(PROJECT_ROOT, "_update_temp.zip")

    if not download_with_progress(DOWNLOAD_URL, zip_path):
        print_error("Download failed.")
        return False

    print_success("Download completed.")
    print()

    # ─── STEP 3: Backup Existing Files ───
    print_step(3, total_steps, "Backing up existing code files...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(PROJECT_ROOT, BACKUP_DIR_NAME, f"backup_{timestamp}")

    try:
        os.makedirs(backup_dir, exist_ok=True)

        # Backup only the files to be updated (those that are not protected)
        backed_up = 0
        for root, dirs, files in os.walk(PROJECT_ROOT):
            # Skip backup and temp folders
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

        print_success(f"Backup completed ({backed_up} file → {BACKUP_DIR_NAME}/backup_{timestamp}/)")
    except Exception as e:
        print_warning(f"Error during backup (update in progress): {e}")

    print()

    # ─── STEP 4: Update Files ───
    print_step(4, total_steps, "Files are being updated...")
    extract_dir = os.path.join(PROJECT_ROOT, "_update_extract")

    try:
        # Extract ZIP
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        # GitHub ZIPs contain a parent folder "REPO-BRANCH/"
        inner_dirs = os.listdir(extract_dir)
        if len(inner_dirs) == 1 and os.path.isdir(os.path.join(extract_dir, inner_dirs[0])):
            source_root = os.path.join(extract_dir, inner_dirs[0])
        else:
            source_root = extract_dir

        # Compare and update files
        for root, dirs, files in os.walk(source_root):
            rel_root = os.path.relpath(root, source_root)

            for f in files:
                if rel_root == ".":
                    rel_path = f
                else:
                    rel_path = os.path.join(rel_root, f)

                # Protected?
                if is_protected(rel_path):
                    stats["protected"] += 1
                    continue

                src_file = os.path.join(root, f)
                dst_file = os.path.join(PROJECT_ROOT, rel_path)

                # Does the target file exist?
                if os.path.exists(dst_file):
                    # Compare hash — skip if same
                    if file_hash(src_file) == file_hash(dst_file):
                        stats["skipped"] += 1
                        continue
                    else:
                        # Different → update
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        stats["updated"] += 1
                        print(f"📝 Updated: {rel_path}")
                else:
                    # Yeni dosya → ekle
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    shutil.copy2(src_file, dst_file)
                    stats["added"] += 1
                    print(f"    🆕 Eklendi:     {rel_path}")

        print()
        print_success("File update completed.")

    except zipfile.BadZipFile:
        print_error("The downloaded file is not a valid ZIP. Try again.")
        return False
    except Exception as e:
        print_error(f"Error during update: {e}")
        print_info(f"Your backup files: {backup_dir}")
        return False
    finally:
        # Clear temporary files
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)

    print()

    # ─── STEP 5: Final Report ───
    print_step(5, total_steps, "Update report is being prepared...")
    print()
    print("  ╔════════════════════════════════════════════════════════╗")
    print("║ 📊 UPDATE REPORT ║")
    print("  ╠════════════════════════════════════════════════════════╣")
    print(f"║ 📝 Updated files: {stats['updated']:>4} ║")
    print(f"  ║  🆕 Yeni eklenen dosyalar: {stats['added']:>4}                       ║")
    print(f"║ ⏩ Already up to date (skipped): {stats['skipped']:>4} ║")
    print(f"║ 🛡️ Protected personal data: {stats['protected']:>4} ║")
    print("  ╠════════════════════════════════════════════════════════╣")

    if stats["updated"] == 0 and stats["added"] == 0:
        print("║ ✨ You are already on the latest version!                     ║")
    else:
        total_changes = stats["updated"] + stats["added"]
        print(f"║ ✅ Total {total_changes} files updated successfully!           ║")

    print("  ╚════════════════════════════════════════════════════════╝")
    print()
    print("  🛡️  Korunan verileriniz:")
    print("• .env (API keys)")
    print("• contacts.json (contacts)")
    print("• memory_db/ (memory database)")
    print("• logs/ (log files)")
    print("• Audio files (.mp3, .wav)")
    print()

    # Recommendation to clean old backups (if there are more than 3 backups)
    backup_base = os.path.join(PROJECT_ROOT, BACKUP_DIR_NAME)
    if os.path.exists(backup_base):
        backups = sorted(os.listdir(backup_base))
        if len(backups) > 3:
            print_info(f"You have a backup folder {len(backups)}. To clear old backups:")
            print(f"Folder: {backup_base}")
            print()

    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    try:
        success = run_update()

        if success:
            print("🚀 You can use the current version by restarting J.A.R.V.I.S.")
        else:
            print("⚠️ The update could not be completed. Check the error messages above.")

        print()
        input("Press Enter to exit...")

    except KeyboardInterrupt:
        print("\n\n ⛔ Update canceled by user.")
    except Exception as e:
        print(f"\n ❌ Critical error: {e}")
        input("\nPress Enter to exit...")
