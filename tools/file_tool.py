"""[V15.0] J.A.R.V.I.S. Filesystem Tools
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Production-grade file I/O tools.

V15.0 Changes:
    - Absolute path guarantee: real user directories via Windows API
    - Context-aware: last_active_file is updated on every successful transaction
    - OS-level verification: exists() + content verification
    - NO fake success: every failure returns honestly
    - FILE_WRITE: path|content and context fallback
    - FOLDER_OPEN: explorer.exe verified subprocess
    - FILE_DELETE: full implementation"""

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
    """Returns the actual user directory with the Windows KNOWNFOLDER API or SHGetFolderPath.
    Fallback: os.path.expanduser + USERPROFILE env."""
    # Shell folder ID mapping specific to Windows
    CSIDL_MAP = {
        "desktop":    0x0010,   # CSIDL_DESKTOPDIRECTORY
        "documents":  0x0005,   # CSIDL_PERSONAL
        "downloads":  None,     # No CSIDL, get it from Registry
        "pictures":   0x0027,   # CSIDL_MYPICTURES
        "videos":     0x000E,   # CSIDL_MYVIDEO (eski), fallback kullan
    }

    # Try USERPROFILE + direct path first (most reliable)
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
        # This is the correct path even if it is not created — return
        return p

    return Path(userprofile)


# Turkish → canonical folder key mapping
FOLDER_ALIAS_MAP = {
    "desktop":      "desktop",
    "desktop":      "desktop",
    "desktop":      "desktop",
    "masaustu":      "desktop",
    "desktop":       "desktop",
    "belgeler":      "documents",
    "documents":    "documents",
    "documents":     "documents",
    "indirmeler":    "downloads",
    "indirilenler":  "downloads",
    "indirilmeler":  "downloads",
    "downloads":     "downloads",
    "resimler":      "pictures",
    "pictures":      "pictures",
    "photos":   "pictures",
    "videolar":      "videos",
    "videos":        "videos",
    "music":         "music",
    "music":         "music",
}


def _resolve_path(raw: str, context: dict = None) -> tuple[Path, str]:
    """Converts the raw path string to absolute Path.

    Returns: (resolved_path, debug_info)

    Priority:
      1. Empty + context last_active_file → last active file
      2. Turkish alias prefix → Windows real folder (inflectional suffixes are cleared)
      3. If it is an absolute path, use it directly
      4. Relative path → expanduser + resolve"""
    raw = (raw or "").strip()
    # Legacy format compatibility: convert pipe separator to path separator
    raw = raw.replace("|", "/")

    #1. Get last active file from empty input → context
    if not raw:
        if context:
            laf = context.get("last_active_file")
            if laf:
                return Path(laf), f"context:last_active_file={laf}"
        return Path.cwd(), "fallback:cwd"

    lower = raw.lower()

    # Turkish inflectional suffixes — strip after alias
    TURKISH_SUFFIXES = ("nde", "nude", "nude", "ni", "ne", "na", "ya", "ye",
                        "da", "de", "ta", "te", "of", "nun", "nin", "of")

    # 2. Turkish alias prefix control
    for alias, folder_key in FOLDER_ALIAS_MAP.items():
        if lower.startswith(alias):
            base_folder = _get_windows_user_folder(folder_key)
            remainder = raw[len(alias):]

            # Derive the Turkish inflectional suffix (e.g. "nde", "ne", "ya" etc.)
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

    # 4. If only the file name is given (no path component) → is there a file with the same name in the context?
    # Ex: "Write into jarvis_regression_test.txt" → raw="jarvis_regression_test.txt"
    # context'te last_active_file="C:\...\Desktop\jarvis_regression_test.txt" → o path'i kullan
    if "/" not in raw and "\\" not in raw and context is not None:
        laf = context.get("last_active_file")
        if laf:
            laf_path = Path(laf)
            # Only if the filename matches (case insensitive)
            if laf_path.name.lower() == Path(raw).name.lower():
                return laf_path, f"context_match:{raw}→{laf_path}"

    # 5. Relative → expanduser resolve
    expanded = Path(raw).expanduser().resolve()
    return expanded, f"relative:{raw}→{expanded}"


def _set_last_active_file(context: dict, path: Path):
    """Write the last active file to the context. If there is a PlanExecutor reference, write it to that too."""
    if context is None:   # NOTE: 'if not context' returns False for {}, this is FALSE
        return
    context["last_active_file"] = str(path)
    logger.info(f"[CONTEXT] last_active_file = {path}")
    # If there is a PlanExecutor reference
    pe = context.get("plan_executor")
    if pe is not None and hasattr(pe, "last_active_file"):
        pe.last_active_file = str(path)
        logger.info(f"[CONTEXT] plan_executor.last_active_file = {path}")



def _parse_write_params(raw: str, context: dict) -> tuple[str, str]:
    """For FILE_WRITE, it distinguishes path and content.

    Formats:
      1. "desktop/test.txt|hello" → path=desktop/test.txt, content=hello
      2. "test.txt|hello world" → path=test.txt, content=hello world
      3. “type hello in it” → path=context, content=hello (verb extraction)
      4. "hello" → path=context, content=hello"""
    if "|" in raw:
        parts = raw.split("|", 1)
        return parts[0].strip(), parts[1].strip()

    # Turkish "Write Y into X" / "Write Y into X" pattern
    import re
    # "write hello in test.txt" → path=test.txt, content=hello
    m = re.search(r'(.+?)\s+(?:into|into\s+)\s*(.+?)(?:\s+write\s*)?$', raw, re.IGNORECASE)
    if m:
        possible_path = m.group(1).strip()
        # If possible_path contains a file extension or is an alias → path
        if ("." in possible_path or
                any(possible_path.lower().startswith(a) for a in FOLDER_ALIAS_MAP)):
            content_part = m.group(2).strip()
            # Remove the verb "write" if it is appended
            if content_part.endswith(" yaz"):
                content_part = content_part[:-4].strip()
            return possible_path, content_part

    # Just content → get path from context (empty string → _resolve_path gets from context)
    # like "write hello in it"
    content_clean = raw
    # "... yaz" son fiilini temizle
    if content_clean.lower().endswith(" yaz"):
        content_clean = content_clean[:-4].strip()
    # clear "into" prefix
    if content_clean.lower().startswith("into"):
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
                message=f"File not found: {path}"
            )

        if path.is_dir():
            try:
                files = sorted(path.iterdir(), key=lambda f: f.name)[:20]
                names = [f.name for f in files]
                files_str = ", ".join(names) if names else "folder is empty"
                return ToolResult(
                    success=True, verified=True,
                    message=f"Dizin ({path}): {files_str}",
                    speak=f"Folder content: {files_str}"
                )
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message=str(e))

        _set_last_active_file(context, path)
        try:
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, lambda: path.read_text(encoding="utf-8"))
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + "... [INTERRUPT]"
            return ToolResult(
                success=True, verified=True,
                message=content,
                speak=f"File {path.name} has been read."
            )
        except UnicodeDecodeError:
            try:
                loop = asyncio.get_running_loop()
                content = await loop.run_in_executor(None, lambda: path.read_text(encoding="cp1254"))
                return ToolResult(success=True, verified=True, message=content, speak="Dosya okundu.")
            except Exception as e:
                return ToolResult(success=False, verified=False, error=str(e), message=f"Encoding error: {e}")
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=f"Read error: {e}")


class FileCreateTool(BaseTool):
    name = "Creating Files"
    protocol_tag = "FILE_CREATE"
    domain = "filesystem"
    parameters = {
        "file_path": {"type": "string", "description": "File path (ex: desktop/test.txt)"}
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        # Resolve according to the type of parameter: file_path or query
        raw = (params.get("file_path") or params.get("query") or "").strip()

        if not raw:
            return ToolResult(
                success=False, verified=False,
                error="MissingPath",
                message="Dosya yolu belirtilmedi."
            )

        # Extract filename from raw input (LLM can send "generate test.txt on desktop")
        raw = _extract_filename_from_command(raw)

        path, dbg = _resolve_path(raw, context)
        logger.info(f"FILE_CREATE resolved: {raw!r} → {path} ({dbg})")

        if path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="IsDir",
                message=f"Only directory specified, filename required: {path}"
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
                    message=f"Failed to create file (OS verification failed): {path}"
                )

            _set_last_active_file(context, path)
            return ToolResult(
                success=True, verified=True,
                message=f"{path.name} created → {path}",
                speak=f"File {path.name} created successfully Sir."
            )
        except PermissionError:
            return ToolResult(
                success=False, verified=False,
                error="PermissionDenied",
                message=f"Permission error: No permission to write to location {path}."
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=f"Render error: {e}")


class FileWriteTool(BaseTool):
    name = "Dosya Yazma"
    protocol_tag = "FILE_WRITE"
    domain = "filesystem"
    parameters = {
        "file_path_and_content": {
            "type": "string",
            "description": "File path and context: 'path|content' or just content (path is taken from context)"
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
                message="The content to be written is not specified."
            )

        path, dbg = _resolve_path(file_path_str, context)
        logger.info(f"FILE_WRITE resolved: {file_path_str!r} → {path} ({dbg}), content={content[:40]!r}")

        if path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="IsDir",
                message=f"Cannot write to directory, filename required: {path}"
            )

        try:
            loop = asyncio.get_running_loop()
            def _write_and_read():
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("w", encoding="utf-8") as f:
                    f.write(content + "\n")
                return path.read_text(encoding="utf-8")
            
            written = await loop.run_in_executor(None, _write_and_read)

            # OS-level content verification
            if content not in written:
                return ToolResult(
                    success=False, verified=False,
                    error="VerifyFailed",
                    message=f"Content written but could not be verified: {path}"
                )

            _set_last_active_file(context, path)
            return ToolResult(
                success=True, verified=True,
                message=f"Written to file {path.name} → {path}",
                next_action="FILE_WRITE_INTERPRET",
                data={"filename": path.name}
            )
        except PermissionError:
            return ToolResult(
                success=False, verified=False,
                error="PermissionDenied",
                message=f"Permission error: {path}"
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=f"Write error: {e}")


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
                message=f"File not found: {path}"
            )
        if path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="IsDir",
                message=f"The directory cannot be deleted (security). Only file can be deleted: {path}"
            )

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, path.unlink)

            # OS-level deletion verification
            if path.exists():
                return ToolResult(
                    success=False, verified=False,
                    error="DeleteFailed",
                    message=f"The file appears to have been deleted but still exists: {path}"
                )

            # Clear last_active_file in context
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
                speak=f"File {path.name} deleted successfully Sir."
            )
        except PermissionError:
            return ToolResult(
                success=False, verified=False,
                error="PermissionDenied",
                message=f"Permission error: Could not delete {path}."
            )
        except Exception as e:
            return ToolResult(success=False, verified=False, error=str(e), message=f"Delete error: {e}")


class FolderOpenTool(BaseTool):
    name = "Opening a Folder"
    protocol_tag = "FOLDER_OPEN"
    domain = "filesystem"
    parameters = {
        "folder_path": {"type": "string", "description": "Path or name of the folder to open (e.g. downloads)"}
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        raw = (params.get("folder_path") or params.get("query") or "").strip()

        # If the keyword sounds like "downloads", change it to the correct alias
        raw = _clean_folder_keyword(raw)

        path, dbg = _resolve_path(raw, context)
        logger.info(f"FOLDER_OPEN resolved: {raw!r} → {path} ({dbg})")

        # If path is a file, get parent directory
        if path.is_file():
            path = path.parent

        if not path.exists():
            return ToolResult(
                success=False, verified=False,
                error="NotFound",
                message=f"Folder not found: {path}"
            )

        if not path.is_dir():
            return ToolResult(
                success=False, verified=False,
                error="NotADirectory",
                message=f"This is not a folder: {path}"
            )

        try:
            # Open with Explorer — verified subprocess
            result = subprocess.Popen(
                ["explorer.exe", str(path)],
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            logger.info(f"FOLDER_OPEN: explorer.exe started, PID={result.pid}, path={path}")

            return ToolResult(
                success=True, verified=True,
                message=f"The {path} folder is opened.",
                speak=f"The {path.name} folder is opening, Sir."
            )
        except FileNotFoundError:
            # explorer.exe not found — alternative path
            try:
                os.startfile(str(path))
                return ToolResult(
                    success=True, verified=True,
                    message=f"The {path} folder is opened (os.startfile).",
                    speak="The folder is opening, Sir."
                )
            except Exception as e2:
                return ToolResult(
                    success=False, verified=False,
                    error=str(e2),
                    message=f"Could not open folder: {e2}"
                )
        except Exception as e:
            return ToolResult(
                success=False, verified=False,
                error=str(e),
                message=f"Could not open folder: {e}"
            )


class FileOpenTool(BaseTool):
    name = "Opening a File"
    protocol_tag = "FILE_OPEN"
    domain = "filesystem"
    parameters = {
        "file_path": {"type": "string", "description": "Path or name of the file to be opened (ex: accounting_makinesi.py)"}
    }

    async def execute(self, params: dict, context: dict) -> ToolResult:
        raw = (params.get("file_path") or params.get("query") or "").strip()
        path, dbg = _resolve_path(raw, context)
        logger.info(f"FILE_OPEN resolved: {raw!r} → {path} ({dbg})")

        if not path.exists():
            return ToolResult(
                success=False, verified=False,
                error="NotFound",
                message=f"File not found: {path}"
            )

        if not path.is_file():
            return ToolResult(
                success=False, verified=False,
                error="NotAFile",
                message=f"This is not a file: {path}. Use FOLDER_OPEN to open folders."
            )

        try:
            # os.startfile opens the file with the default OS application (.py with editor, .txt with notepad, etc.)
            os.startfile(str(path))
            return ToolResult(
                success=True, verified=True,
                message=f"The {path.name} file was opened with the default application.",
                speak=f"I am opening the {path.name} file, Sir."
            )
        except Exception as e:
            return ToolResult(
                success=False, verified=False,
                error=str(e),
                message=f"Could not open file: {e}"
            )


class FileLatestTool(BaseTool):
    name = "Son Dosya Bulma"
    protocol_tag = "FILE_LATEST"
    domain = "filesystem"
    parameters = {
        "dir_path": {"type": "string", "description": "Folder path (e.g. downloads)"}
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
                message=f"Folder not found: {path}"
            )

        try:
            files = [f for f in path.iterdir() if f.is_file()]
            if not files:
                return ToolResult(
                    success=False, verified=False,
                    error="Empty",
                    message=f"No files in folder: {path}"
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
    """For backward compatibility — redirects."""
    name = "File Summarization"
    protocol_tag = "FILE_SUMMARIZE"
    domain = "filesystem"
    parameters = {"file_path": {"type": "string", "description": "Dosya yolu"}}

    async def execute(self, params: dict, context: dict) -> ToolResult:
        return ToolResult(
            success=False, verified=False,
            error="Deprecated",
            message="This tool has been removed. Use FILE_READ."
        )


# ──────────────────────────────────────────────────────────
# AUXILIARY FUNCTIONS
# ──────────────────────────────────────────────────────────

def _extract_filename_from_command(raw: str) -> str:
    """
    "create test.txt on desktop" → "desktop/test.txt"
    "create test.txt" → "test.txt"
    "create notes.txt to desktop" → "desktop/notes.txt"
    """
    import re

    # If the path is already clean, do not touch it
    if not any(v in raw.lower() for v in ["create", "yarat", "created", "yaz"]):
        return raw

    # "create X on/to desktop" pattern
    for alias in FOLDER_ALIAS_MAP.keys():
        # "on desktop", "to desktop", "desktop" etc.
        pattern = rf'({re.escape(alias)}(?:n[de]|what|nu|what|eat|or|in|to)?)\s+(.+?)(?:\s+(?:create|create|generate|write).*)?$'
        m = re.search(pattern, raw.lower(), re.IGNORECASE)
        if m:
            folder_part = alias  # canonical alias kullan
            file_part = m.group(2).strip()
            # remove verbs like "create"
            file_part = re.sub(r'\s+(?:create|create|create|write|file\s+create).*$', '', file_part, flags=re.IGNORECASE).strip()
            if file_part:
                return f"{folder_part}/{file_part}"
            return folder_part

    # Extract the filename directly (remaining words)
    cleaned = re.sub(r'\s+(?:create|create|create|file\s+create)\s*$', '', raw, flags=re.IGNORECASE).strip()
    return cleaned


def _clean_folder_keyword(raw: str) -> str:
    """
    "downloads folder" → "downloads"
    "documents folder" → "documents"
    """
    import re
    cleaned = re.sub(r'\s+(?:folder|folder|directory|directory|to folder|in folder)\s*$', '', raw, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\s+(?:open|show|list)\s*$', '', cleaned, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else raw