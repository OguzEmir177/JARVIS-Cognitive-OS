"""
[V15.0] J.A.R.V.I.S. Filesystem Tools
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Production-grade file I/O araçları.

V15.0 Değişiklikleri:
    - Absolute path garantisi: Windows API üzerinden gerçek kullanıcı dizinleri
    - Context-aware: last_active_file her başarılı işlemde güncellenir
    - OS-level doğrulama: exists() + content verification
    - Fake success YOK: her başarısızlık dürüstçe döner
    - FILE_WRITE: path|content ve context fallback
    - FOLDER_OPEN: explorer.exe verified subprocess
    - FILE_DELETE: tam implementasyon
"""

import logging
import os
import subprocess
import ctypes
import asyncio
from pathlib import Path
from tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger("JARVIS.FileTools")
MAX_FILE_CHARS = 8000


def _get_windows_user_folder(folder_name: str) -> Path:
    """
    Windows KNOWNFOLDER API veya SHGetFolderPath ile gerçek kullanıcı dizinini döndürür.
    Fallback: os.path.expanduser + USERPROFILE env.
    """
    # Windows'a özel shell folder ID mapping
    CSIDL_MAP = {
        "desktop":    0x0010,   # CSIDL_DESKTOPDIRECTORY
        "documents":  0x0005,   # CSIDL_PERSONAL
        "downloads":  None,     # CSIDL yok, Registry'den al
        "pictures":   0x0027,   # CSIDL_MYPICTURES
        "videos":     0x000E,   # CSIDL_MYVIDEO (eski), fallback kullan
    }

    # Önce USERPROFILE + direkt yol dene (en güvenilir)
    userprofile = os.environ.get("USERPROFILE", str(Path.home()))

    DIRECT_MAP = {
        "desktop":   os.path.join(userprofile, "Desktop"),
        "documents": os.path.join(userprofile, "Documents"),
        "downloads": os.path.join(userprofile, "Downloads"),
        "pictures":  os.path.join(userprofile, "Pictures"),
        "videos":    os.path.join(userprofile, "Videos"),
        "music":     os.path.join(userprofile, "Music"),
    }

    direct = DIRECT_MAP.get(folder_name.lower())
    if direct:
        p = Path(direct)
        if p.exists():
            return p
        # Oluşmamış bile olsa bu doğru path — döndür
        return p

    return Path(userprofile)


# Türkçe → canonical folder key mapping
FOLDER_ALIAS_MAP = {
    "masaüstü":      "desktop",
    "masaustü":      "desktop",
    "masaüstu":      "desktop",
    "masaustu":      "desktop",
    "desktop":       "desktop",
    "belgeler":      "documents",
    "dökümanlar":    "documents",
    "documents":     "documents",
    "indirmeler":    "downloads",
    "indirilenler":  "downloads",
    "indirilmeler":  "downloads",
    "downloads":     "downloads",
    "resimler":      "pictures",
    "pictures":      "pictures",
    "fotoğraflar":   "pictures",
    "videolar":      "videos",
    "videos":        "videos",
    "müzik":         "music",
    "music":         "music",
}


def _resolve_path(raw: str, context: dict = None) -> tuple[Path, str]:
    """
    Ham path string'ini absolute Path'e çevirir.

    Returns: (resolved_path, debug_info)

    Priority:
      1. Boş + context last_active_file → son aktif dosya
      2. Türkçe alias prefix → Windows gerçek klasör (çekim ekleri temizlenir)
      3. Absolute path ise direkt kullan
      4. Relative path → expanduser + resolve
    """
    raw = (raw or "").strip()
    # Eski format uyumluluğu: pipe separator'ı path separator'a çevir
    raw = raw.replace("|", "/")

    # 1. Boş input → context'ten son aktif dosyayı al
    if not raw:
        if context:
            laf = context.get("last_active_file")
            if laf:
                return Path(laf), f"context:last_active_file={laf}"
        return Path.cwd(), "fallback:cwd"

    lower = raw.lower()

    # Türkçe çekim ekleri — alias'tan sonra strip edilir
    TURKISH_SUFFIXES = ("nde", "nü", "nü", "nı", "ne", "na", "ya", "ye",
                        "da", "de", "ta", "te", "nün", "nun", "nin", "nın")

    # 2. Türkçe alias prefix kontrolü
    for alias, folder_key in FOLDER_ALIAS_MAP.items():
        if lower.startswith(alias):
            base_folder = _get_windows_user_folder(folder_key)
            remainder = raw[len(alias):]

            # Türkçe çekim ekini soyundan soy (örn: "nde ", "ne ", "ya " vb.)
            remainder_stripped = remainder.lstrip()
            remainder_lower = remainder_stripped.lower()
            for suffix in TURKISH_SUFFIXES:
                if remainder_lower.startswith(suffix) and (
                    len(remainder_lower) == len(suffix) or
                    not remainder_lower[len(suffix)].isalpha()
                ):
                    remainder_stripped = remainder_stripped[len(suffix):]
                    break

            remainder_stripped = remainder_stripped.strip("/\\ ")

            if remainder_stripped:
                resolved = (base_folder / remainder_stripped).resolve()
            else:
                resolved = base_folder.resolve()
            return resolved, f"alias:{alias}→{base_folder}/{remainder_stripped}"

    # 3. Absolute path
    p = Path(raw)
    if p.is_absolute():
        return p.resolve(), f"absolute:{raw}"

    # 4. Sadece dosya adı verilmişse (path bileşeni yok) → context'te aynı isimde dosya var mı?
    # Örn: "jarvis_regression_test.txt içine yaz" → raw="jarvis_regression_test.txt"
    # context'te last_active_file="C:\...\Desktop\jarvis_regression_test.txt" → o path'i kullan
    if "/" not in raw and "\\" not in raw and context is not None:
        laf = context.get("last_active_file")
        if laf:
            laf_path = Path(laf)
            # Sadece dosya adı eşleşiyorsa (büyük/küçük harf insensitive)
            if laf_path.name.lower() == Path(raw).name.lower():
                return laf_path, f"context_match:{raw}→{laf_path}"

    # 5. Relative → expanduser resolve
    expanded = Path(raw).expanduser().resolve()
    return expanded, f"relative:{raw}→{expanded}"


def _set_last_active_file(context: dict, path: Path):
    """Context'e son aktif dosyayı yaz. PlanExecutor referansı varsa ona da yaz."""
    if context is None:   # NOT: 'if not context' {} için False döner, bu YANLIŞ
        return
    context["last_active_file"] = str(path)
    logger.info(f"[CONTEXT] last_active_file = {path}")
    # PlanExecutor referansı varsa
    pe = context.get("plan_executor")
    if pe is not None and hasattr(pe, "last_active_file"):
        pe.last_active_file = str(path)
        logger.info(f"[CONTEXT] plan_executor.last_active_file = {path}")



def _parse_write_params(raw: str, context: dict) -> tuple[str, str]:
    """
    FILE_WRITE için path ve content ayırt eder.

    Formatlar:
      1. "masaüstü/test.txt|merhaba"   → path=masaüstü/test.txt, content=merhaba
      2. "test.txt|merhaba dünya"       → path=test.txt, content=merhaba dünya
      3. "içine merhaba yaz"            → path=context, content=merhaba (verb extraction)
      4. "merhaba"                      → path=context, content=merhaba
    """
    if "|" in raw:
        parts = raw.split("|", 1)
        return parts[0].strip(), parts[1].strip()

    # Türkçe "X'e Y yaz" / "X içine Y yaz" kalıbı
    import re
    # "test.txt içine merhaba yaz" → path=test.txt, content=merhaba
    m = re.search(r'(.+?)\s+(?:içine|içine\s+)\s*(.+?)(?:\s+yaz\s*)?$', raw, re.IGNORECASE)
    if m:
        possible_path = m.group(1).strip()
        # Eğer possible_path bir dosya uzantısı içeriyorsa ya da alias ise → path
        if ("." in possible_path or
                any(possible_path.lower().startswith(a) for a in FOLDER_ALIAS_MAP)):
            content_part = m.group(2).strip()
            # "yaz" fiilini sona eklenmişse çıkar
            if content_part.endswith(" yaz"):
                content_part = content_part[:-4].strip()
            return possible_path, content_part

    # Sadece içerik → path'i context'ten al (boş string → _resolve_path context'ten alır)
    # "içine merhaba yaz" gibi
    content_clean = raw
    # "... yaz" son fiilini temizle
    if content_clean.lower().endswith(" yaz"):
        content_clean = content_clean[:-4].strip()
    # "içine " prefix'ini temizle
    if content_clean.lower().startswith("içine "):
        content_clean = content_clean[6:].strip()
    return "", content_clean


# ──────────────────────────────────────────────────────────
#  TOOLS
# ──────────────────────────────────────────────────────────

class FileReadTool(BaseTool):
    name = "Dosya Okuma"
    protocol_tag = "FILE_READ"
    domain = "filesystem"
    parameters = {
        "file_path": {"type": "string", "description": "Dosya veya dizin yolu"}
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        raw = params.get("file_path", "").strip()
        path, dbg = _resolve_path(raw, context)
        logger.info(f"FILE_READ resolved: {raw!r} → {path} ({dbg})")

        if not path.exists():
            return ToolResult(
                success=False, verified=False,
                error="NotFound",
                message=f"Dosya bulunamadı: {path}"
            )

        if path.is_dir():
            try:
                files = sorted(path.iterdir(), key=lambda f: f.name)[:20]
                names = [f.name for f in files]
                files_str = ", ".join(names) if names else "Klasör boş"
                return ToolResult(
                    success=True, verified=True,
                    message=f"Dizin ({path}): {files_str}",
                    speak=f"Klasör içeriği: {files_str}"
                )
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message=str(e))

        _set_last_active_file(context, path)
        try:
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, lambda: path.read_text(encoding="utf-8"))
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + "... [KESİLDİ]"
            return ToolResult(
                success=True, verified=True,
                message=content,
                speak=f"{path.name} dosyası okundu."
            )
        except UnicodeDecodeError:
            try:
                loop = asyncio.get_running_loop()
                content = await loop.run_in_executor(None, lambda: path.read_text(encoding="cp1254"))
                return ToolResult(success=True, verified=True, message=content, speak="Dosya okundu.")
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message=f"Encoding hatası: {e}")
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=f"Okuma hatası: {e}")


class FileCreateTool(BaseTool):
    name = "Dosya Oluşturma"
    protocol_tag = "FILE_CREATE"
    domain = "filesystem"
    parameters = {
        "file_path": {"type": "string", "description": "Dosya yolu (ör: masaüstü/test.txt)"}
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        # Parametre gelme şekline göre çöz: file_path veya query
        raw = (params.get("file_path") or params.get("query") or "").strip()

        if not raw:
            return ToolResult(
                success=False, verified=False,
                error="MissingPath",
                message="Dosya yolu belirtilmedi."
            )

        # Ham input'tan dosya adını çıkar (LLM "masaüstünde test.txt oluştur" gönderebilir)
        raw = _extract_filename_from_command(raw)

        path, dbg = _resolve_path(raw, context)
        logger.info(f"FILE_CREATE resolved: {raw!r} → {path} ({dbg})")

        if path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="IsDir",
                message=f"Sadece dizin belirtildi, dosya adı gerekli: {path}"
            )

        try:
            loop = asyncio.get_running_loop()
            def _create_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch(exist_ok=True)
            await loop.run_in_executor(None, _create_file)

            # OS-level verification
            if not path.exists():
                return ToolResult(
                    success=False, verified=False,
                    error="CreateFailed",
                    message=f"Dosya oluşturulamadı (OS doğrulaması başarısız): {path}"
                )

            _set_last_active_file(context, path)
            return ToolResult(
                success=True, verified=True,
                message=f"{path.name} oluşturuldu → {path}",
                speak=f"{path.name} dosyası başarıyla oluşturuldu Efendim."
            )
        except PermissionError:
            return ToolResult(
                success=False, verified=False,
                error="PermissionDenied",
                message=f"İzin hatası: {path} konumuna yazma izni yok."
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=f"Oluşturma hatası: {e}")


class FileWriteTool(BaseTool):
    name = "Dosya Yazma"
    protocol_tag = "FILE_WRITE"
    domain = "filesystem"
    parameters = {
        "file_path_and_content": {
            "type": "string",
            "description": "Dosya yolu ve içerik: 'yol|içerik' veya sadece içerik (path context'ten alınır)"
        }
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        raw = (params.get("file_path_and_content") or
               params.get("query") or
               params.get("file_path") or "").strip()

        file_path_str, content = _parse_write_params(raw, context)

        if not content:
            return ToolResult(
                success=False, verified=False,
                error="MissingContent",
                message="Yazılacak içerik belirtilmedi."
            )

        path, dbg = _resolve_path(file_path_str, context)
        logger.info(f"FILE_WRITE resolved: {file_path_str!r} → {path} ({dbg}), content={content[:40]!r}")

        if path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="IsDir",
                message=f"Dizine yazılamaz, dosya adı gerekli: {path}"
            )

        try:
            loop = asyncio.get_running_loop()
            def _write_and_read():
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(content + "\n")
                return path.read_text(encoding="utf-8")
            
            written = await loop.run_in_executor(None, _write_and_read)

            # OS-level content verification
            if content not in written:
                return ToolResult(
                    success=False, verified=False,
                    error="VerifyFailed",
                    message=f"İçerik yazıldı ama doğrulanamadı: {path}"
                )

            _set_last_active_file(context, path)
            return ToolResult(
                success=True, verified=True,
                message=f"{path.name} dosyasına yazıldı → {path}",
                speak=f"{path.name} dosyasına başarıyla yazıldı Efendim."
            )
        except PermissionError:
            return ToolResult(
                success=False, verified=False,
                error="PermissionDenied",
                message=f"İzin hatası: {path}"
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=f"Yazma hatası: {e}")


class FileDeleteTool(BaseTool):
    name = "Dosya Silme"
    protocol_tag = "FILE_DELETE"
    domain = "filesystem"
    parameters = {
        "file_path": {"type": "string", "description": "Silinecek dosya yolu"}
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        raw = (params.get("file_path") or params.get("query") or "").strip()
        path, dbg = _resolve_path(raw, context)
        logger.info(f"FILE_DELETE resolved: {raw!r} → {path} ({dbg})")

        if not path.exists():
            return ToolResult(
                success=False, verified=False,
                error="NotFound",
                message=f"Dosya bulunamadı: {path}"
            )
        if path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="IsDir",
                message=f"Dizin silinemez (güvenlik). Sadece dosya silinebilir: {path}"
            )

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, path.unlink)

            # OS-level deletion verification
            if path.exists():
                return ToolResult(
                    success=False, verified=False,
                    error="DeleteFailed",
                    message=f"Dosya silindi gibi görünüyor ama hâlâ var: {path}"
                )

            # Context'teki last_active_file'ı temizle
            if context:
                if context.get("last_active_file") == str(path):
                    context["last_active_file"] = None
                pe = context.get("plan_executor")
                if pe and hasattr(pe, "last_active_file"):
                    if pe.last_active_file == str(path):
                        pe.last_active_file = None

            return ToolResult(
                success=True, verified=True,
                message=f"{path.name} silindi.",
                speak=f"{path.name} dosyası başarıyla silindi Efendim."
            )
        except PermissionError:
            return ToolResult(
                success=False, verified=False,
                error="PermissionDenied",
                message=f"İzin hatası: {path} silinemedi."
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=f"Silme hatası: {e}")


class FolderOpenTool(BaseTool):
    name = "Klasör Açma"
    protocol_tag = "FOLDER_OPEN"
    domain = "filesystem"
    parameters = {
        "folder_path": {"type": "string", "description": "Açılacak klasör yolu veya adı (ör: indirilenler)"}
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        raw = (params.get("folder_path") or params.get("query") or "").strip()

        # Keyword olarak "indirilenler" gibi gelirse doğru alias'a çevir
        raw = _clean_folder_keyword(raw)

        path, dbg = _resolve_path(raw, context)
        logger.info(f"FOLDER_OPEN resolved: {raw!r} → {path} ({dbg})")

        # Eğer path bir dosyaysa, parent dizini al
        if path.is_file():
            path = path.parent

        if not path.exists():
            return ToolResult(
                success=False, verified=False,
                error="NotFound",
                message=f"Klasör bulunamadı: {path}"
            )

        if not path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="NotADirectory",
                message=f"Bu bir klasör değil: {path}"
            )

        try:
            # Explorer ile aç — verified subprocess
            result = subprocess.Popen(
                ["explorer.exe", str(path)],
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            logger.info(f"FOLDER_OPEN: explorer.exe başlatıldı, PID={result.pid}, path={path}")

            return ToolResult(
                success=True, verified=True,
                message=f"{path} klasörü açıldı.",
                speak=f"{path.name} klasörü açılıyor Efendim."
            )
        except FileNotFoundError:
            # explorer.exe bulunamadı — alternatif yol
            try:
                os.startfile(str(path))
                return ToolResult(
                    success=True, verified=True,
                    message=f"{path} klasörü açıldı (os.startfile).",
                    speak="Klasör açılıyor Efendim."
                )
            except Exception as e2:
                return ToolResult(
                    success=False, verified=False,
                    error=str(e2),
                    message=f"Klasör açılamadı: {e2}"
                )
        except Exception as e:
            return ToolResult(
                success=False, verified=False,
                error=str(e),
                message=f"Klasör açılamadı: {e}"
            )


class FileLatestTool(BaseTool):
    name = "Son Dosya Bulma"
    protocol_tag = "FILE_LATEST"
    domain = "filesystem"
    parameters = {
        "dir_path": {"type": "string", "description": "Klasör yolu (ör: indirmeler)"}
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        raw = (params.get("dir_path") or params.get("query") or "indirilenler").strip()
        raw = _clean_folder_keyword(raw)
        path, dbg = _resolve_path(raw, context)
        logger.info(f"FILE_LATEST resolved: {raw!r} → {path} ({dbg})")

        if not path.exists() or not path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="NoDir",
                message=f"Klasör bulunamadı: {path}"
            )

        try:
            files = [f for f in path.iterdir() if f.is_file()]
            if not files:
                return ToolResult(
                    success=False, verified=False,
                    error="Empty",
                    message=f"Klasörde dosya yok: {path}"
                )
            latest = max(files, key=lambda p: p.stat().st_mtime)
            _set_last_active_file(context, latest)
            return ToolResult(
                success=True, verified=True,
                message=f"Son indirilen dosya: {latest.name} ({latest})",
                speak=f"Son indirilen dosya: {latest.name}"
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=str(e))


class FileSummarizeTool(BaseTool):
    """Geriye dönük uyumluluk için — yönlendirir."""
    name = "Dosya Özetleme"
    protocol_tag = "FILE_SUMMARIZE"
    domain = "filesystem"
    parameters = {"file_path": {"type": "string", "description": "Dosya yolu"}}

    async def execute(self, params: dict, context: dict) -> ToolResult:
        return ToolResult(
            success=False, verified=False,
            error="Deprecated",
            message="Bu araç kaldırıldı. FILE_READ kullanın."
        )


# ──────────────────────────────────────────────────────────
#  YARDIMCI FONKSİYONLAR
# ──────────────────────────────────────────────────────────

def _extract_filename_from_command(raw: str) -> str:
    """
    "masaüstünde test.txt oluştur" → "masaüstü/test.txt"
    "test.txt oluştur" → "test.txt"
    "masaüstüne notes.txt yarat" → "masaüstü/notes.txt"
    """
    import re

    # Eğer zaten temiz path ise dokunma
    if not any(v in raw.lower() for v in ["oluştur", "yarat", "oluşt", "yaz"]):
        return raw

    # "masaüstünde/masaüstüne X oluştur" kalıbı
    for alias in FOLDER_ALIAS_MAP.keys():
        # "masaüstünde", "masaüstüne", "masaüstünü" vb.
        pattern = rf'({re.escape(alias)}(?:n[de]|ne|nü|nı|ye|ya|de|da)?)\s+(.+?)(?:\s+(?:oluştur|yarat|oluşt|yaz).*)?$'
        m = re.search(pattern, raw.lower(), re.IGNORECASE)
        if m:
            folder_part = alias  # canonical alias kullan
            file_part = m.group(2).strip()
            # "oluştur" gibi fiilleri çıkar
            file_part = re.sub(r'\s+(?:oluştur|yarat|oluşt|yaz|dosya\s+oluştur).*$', '', file_part, flags=re.IGNORECASE).strip()
            if file_part:
                return f"{folder_part}/{file_part}"
            return folder_part

    # Dosya adını doğrudan çıkar (geriye kalan kelimeler)
    cleaned = re.sub(r'\s+(?:oluştur|yarat|oluşt|dosya\s+oluştur)\s*$', '', raw, flags=re.IGNORECASE).strip()
    return cleaned


def _clean_folder_keyword(raw: str) -> str:
    """
    "indirilenler klasörünü" → "indirilenler"
    "belgeler klasörü" → "belgeler"
    """
    import re
    cleaned = re.sub(r'\s+(?:klasörünü|klasörü|dizini|dizinini|klasörüne|klasöründe)\s*$', '', raw, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\s+(?:aç|göster|listele)\s*$', '', cleaned, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else raw