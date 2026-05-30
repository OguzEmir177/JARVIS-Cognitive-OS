"""
╔══════════════════════════════════════════════════════════════════════════╗
║        J.A.R.V.I.S. AUTONOMOUS CODE AUDITOR — jarvis_audit.py          ║
║   Statik analiz ile bug tespiti, sınıflandırma ve fix talimatları       ║
╚══════════════════════════════════════════════════════════════════════════╝

Kullanım:
    python jarvis_audit.py

Çıktı:
    - Konsola ve audit_report.txt dosyasına yazılır.
    - Her bulgu: CRITICAL / WARNING / INFO olarak sınıflandırılır.
    - Her bulgu için nokta atışı düzeltme talimatı verilir.
"""

import ast
import re
import sys
import os
import io
from datetime import datetime
from pathlib import Path

# Windows terminal UTF-8 fix
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ─────────────────────────────────────────────────────────────────────────────
#  KONFİGÜRASYON — Hangi dosyaları tara?
# ─────────────────────────────────────────────────────────────────────────────
TARGET_FILES = [
    "core/brain.py",
    "core/engine.py",
    "core/io_bridge.py",
    "core/watcher.py",
    "core/plan_executor.py",
    "core/executor.py",
    "core/scheduler.py",
    "core/memory.py",
    "core/cognitive_core.py",
    "gui/interface.py",
]

# ─────────────────────────────────────────────────────────────────────────────
#  RENK KODLARI (Terminal)
# ─────────────────────────────────────────────────────────────────────────────
class C:
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

# ─────────────────────────────────────────────────────────────────────────────
#  BULGU SINIFI
# ─────────────────────────────────────────────────────────────────────────────
class Finding:
    LEVELS = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}

    def __init__(self, level: str, file: str, line: int | str, title: str, detail: str, fix: str):
        self.level  = level   # CRITICAL / WARNING / INFO
        self.file   = file
        self.line   = line    # int veya "N/A"
        self.title  = title
        self.detail = detail
        self.fix    = fix

    @property
    def order(self):
        return self.LEVELS.get(self.level, 99)


findings: list[Finding] = []

def report(level, file, line, title, detail, fix):
    findings.append(Finding(level, file, line, title, detail, fix))


# ─────────────────────────────────────────────────────────────────────────────
#  YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────────────────
def read_file(path: str) -> tuple[str | None, list[str]]:
    """Dosyayı okur. (raw_text, lines) döndürür. Hata varsa (None, [])."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text, text.splitlines()
    except FileNotFoundError:
        return None, []
    except Exception as e:
        print(f"  [!] {path} okunamadı: {e}")
        return None, []


def parse_ast(text: str, path: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except SyntaxError as e:
        report("CRITICAL", path, e.lineno, "Syntax Error",
               f"Dosya parse edilemiyor: {e.msg}",
               "Söz dizimi hatasını düzeltin. Detay: " + str(e))
        return None


def find_lines(lines: list[str], pattern: str, flags=re.IGNORECASE) -> list[tuple[int, str]]:
    """Pattern'i satır satır arar. [(line_no, line_text), ...] döndürür (1-indexed)."""
    results = []
    rx = re.compile(pattern, flags)
    for i, line in enumerate(lines, 1):
        if rx.search(line):
            results.append((i, line.rstrip()))
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  CHECK FONKSİYONLARI
# ─────────────────────────────────────────────────────────────────────────────

def check_syntax(path: str, text: str):
    """Her dosya için söz dizimi kontrolü."""
    try:
        ast.parse(text)
    except SyntaxError as e:
        report("CRITICAL", path, e.lineno, "Syntax Error",
               f"Python bu dosyayı yükleyemez: {e.msg}",
               f"Satır {e.lineno} civarındaki söz dizimini düzeltin.")


def check_asyncio_lock_lazy(path: str, lines: list[str], tree):
    """
    CRITICAL: asyncio.Lock() lazy init — yarış koşulu.
    Pattern: __init__ içinde self._lock = None  VE  bir metod içinde  if self._lock is None: self._lock = asyncio.Lock()
    """
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # __init__ içinde _lock = None var mı?
        init_has_none_lock = False
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in ast.walk(item):
                    if (isinstance(stmt, ast.Assign) and
                            any(isinstance(t, ast.Attribute) and "_lock" in t.attr
                                for t in stmt.targets)):
                        if isinstance(stmt.value, ast.Constant) and stmt.value.value is None:
                            init_has_none_lock = True
        if not init_has_none_lock:
            continue
        # Herhangi bir metot içinde lazy init var mı?
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_src = "\n".join(lines[item.lineno - 1: item.end_lineno])
                if "self._lock is None" in method_src and "asyncio.Lock()" in method_src:
                    report(
                        "CRITICAL", path, item.lineno,
                        f"asyncio.Lock Lazy-Init Race Condition — {node.name}",
                        f"Sınıf `{node.name}`: `__init__` içinde `self._lock = None` atanıyor, "
                        f"ardından `{item.name}()` içinde `if self._lock is None: self._lock = asyncio.Lock()` ile oluşturuluyor. "
                        f"İki coroutine aynı anda ilk kez bu metodu çağırırsa her ikisi de `None` görür ve iki ayrı Lock nesnesi oluşturur — mutual exclusion tamamen bozulur.",
                        f"DÜZELTME: `__init__` içinde `self._lock = None` satırını "
                        f"`self._lock = asyncio.Lock()` ile değiştirin. "
                        f"Ardından `{item.name}()` içindeki `if self._lock is None: ... asyncio.Lock()` bloğunu tamamen silin."
                    )


def check_blocking_in_async(path: str, lines: list[str], tree):
    """
    CRITICAL: async def içinde blocking çağrılar (locale.setlocale, time.sleep).
    """
    if tree is None:
        return
    BLOCKING = ["locale.setlocale", "time.sleep", "requests.get", "urllib.request.urlopen"]
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        body_src_lines = lines[node.lineno - 1: node.end_lineno]
        for rel_i, line in enumerate(body_src_lines, node.lineno):
            stripped = line.strip()
            for call in BLOCKING:
                if call in stripped and not stripped.startswith("#"):
                    report(
                        "CRITICAL", path, rel_i,
                        f"Blocking Call Inside `async def {node.name}()`",
                        f"`{call}` çağrısı bir `async def` fonksiyon içinde doğrudan kullanılıyor. "
                        f"Bu, async event loop'u dondurur ve tüm sistemi bloke eder.",
                        f"DÜZELTME: `{call}` çağrısını `async def {node.name}()` dışına taşıyın "
                        f"(örn. sınıfın `__init__` metoduna) VEYA "
                        f"`await asyncio.get_running_loop().run_in_executor(None, lambda: {call}(...))` şeklinde sarın."
                    )


def check_turkish_in_speak(path: str, lines: list[str]):
    """
    WARNING: io_bridge.speak() veya update_gui() çağrısına Türkçe karakter içeren string geçilmesi.
    TTS motoru İngilizce, Türkçe string bozuk seslenir.
    """
    TURKISH_CHARS = set("çğışöüÇĞİŞÖÜ")
    speak_pattern = re.compile(r'(io_bridge\.speak|await.*speak)\s*\(', re.IGNORECASE)
    for lineno, line in enumerate(lines, 1):
        if speak_pattern.search(line):
            # Stringin içindeki Türkçe karakter var mı?
            strings_in_line = re.findall(r'"([^"]*)"', line) + re.findall(r"'([^']*)'", line)
            for s in strings_in_line:
                if any(c in TURKISH_CHARS for c in s):
                    report(
                        "WARNING", path, lineno,
                        "Turkish String Passed to TTS Engine",
                        f"TTS motoru İngilizce konuşmak üzere ayarlı. `{s}` Türkçe karakter içeriyor — "
                        f"seslendirildiğinde bozuk çıkar.",
                        f"DÜZELTME: Satır {lineno}'deki `{s}` stringini İngilizce karşılığıyla değiştirin."
                    )


def check_update_gui_turkish(path: str, lines: list[str]):
    """
    WARNING: update_gui() çağrısına Türkçe string geçilmesi.
    GUI durum algılayıcısı İngilizce keyword'lere bakıyor (LISTENING, PROCESSING vs.).
    """
    TURKISH_CHARS = set("çğışöüÇĞİŞÖÜ")
    pattern = re.compile(r'update_gui\s*\(', re.IGNORECASE)
    for lineno, line in enumerate(lines, 1):
        if pattern.search(line):
            strings = re.findall(r'"([^"]*)"', line) + re.findall(r"'([^']*)'", line)
            for s in strings:
                if any(c in TURKISH_CHARS for c in s):
                    report(
                        "WARNING", path, lineno,
                        "Turkish Status String in update_gui()",
                        f"`update_gui('{s}')` çağrısında Türkçe string var. "
                        f"GUI'nin durum algılayıcısı (interface.py _get_status_info) İngilizce keyword'lere bakıyor. "
                        f"Bu durum GUI HUD animasyonlarının yanlış renk/ikon göstermesine yol açar.",
                        f"DÜZELTME: Satır {lineno}'deki '{s}' stringini İngilizce karşılığıyla değiştirin "
                        f"(örn. 'YAZILI MOD' → 'TEXT MODE', 'KAPATILIYOR' → 'SHUTTING DOWN')."
                    )


def check_widget_not_packed(path: str, lines: list[str], tree):
    """
    INFO/WARNING: tk.Scrollbar / tk.Label vs. oluşturulup pack/grid/place çağrılmamış olabilir.
    Heuristik: aynı scope içinde variable oluşturulup hiç .pack/.grid çağrılmamış.
    """
    if tree is None:
        return
    # Basit pattern: değişkene atanan widget oluşturma, ardından değişken üzerinde pack/grid yok
    widget_create = re.compile(r'^\s*(\w+)\s*=\s*tk\.(Scrollbar|Label|Button|Frame|Text)\s*\(')
    widget_pack   = re.compile(r'\b(\w+)\.(pack|grid|place)\s*\(')

    # Metot bazlı analiz
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        func_lines = lines[node.lineno - 1: node.end_lineno]
        created: dict[str, int] = {}  # varname -> line_no
        packed:  set[str] = set()

        for rel_i, line in enumerate(func_lines, node.lineno):
            m = widget_create.match(line)
            if m:
                varname = m.group(1)
                if varname not in ("self",):
                    created[varname] = rel_i
            m2 = widget_pack.search(line)
            if m2:
                packed.add(m2.group(1))

        for varname, lineno in created.items():
            if varname not in packed:
                report(
                    "INFO", path, lineno,
                    f"Widget `{varname}` Created But Never Packed/Gridded",
                    f"`{varname} = tk.*(...)` satırında bir widget oluşturuluyor fakat "
                    f"bu değişken üzerinde `.pack()`, `.grid()` veya `.place()` çağrısı bulunamadı. "
                    f"Widget görünmeyebilir.",
                    f"DÜZELTME: Satır {lineno}'den sonra `{varname}.pack(...)` veya `{varname}.grid(...)` ekleyin. "
                    f"Eğer widget intentionally gizliyse bu bulguyu yok sayabilirsiniz."
                )


def check_duplicate_list_items(path: str, lines: list[str], tree):
    """
    INFO: Liste literallerinde tekrarlanan elemanlar.
    """
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.List):
            continue
        values = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant):
                values.append(str(elt.value))
        seen = set()
        duplicates = []
        for v in values:
            if v in seen and v not in duplicates:
                duplicates.append(v)
            seen.add(v)
        if duplicates:
            lineno = node.lineno
            report(
                "INFO", path, lineno,
                "Duplicate Items in List Literal",
                f"Satır {lineno}'deki listede tekrarlanan elemanlar var: {duplicates}. "
                f"Bu genellikle copy-paste hatasıdır ve gereksiz yere hafıza/döngü maliyeti yaratabilir.",
                f"DÜZELTME: Satır {lineno}'deki listeden tekrarlanan elemanları kaldırın: {duplicates}"
            )


def check_dead_parameters(path: str, lines: list[str], tree):
    """
    WARNING: Fonksiyon parametresi tanımlanmış ama fonksiyon gövdesinde hiç kullanılmamış.
    self, cls, *args, **kwargs hariç.
    """
    if tree is None:
        return
    SKIP = {"self", "cls", "args", "kwargs"}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Parametreleri topla
        params = []
        for arg in node.args.args:
            if arg.arg not in SKIP:
                params.append(arg.arg)
        if not params:
            continue
        # Gövde kaynak kodunda parametreyi ara
        body_src = "\n".join(lines[node.lineno: node.end_lineno])
        for param in params:
            # Parametre adını tam kelime olarak ara
            if not re.search(r'\b' + re.escape(param) + r'\b', body_src):
                report(
                    "WARNING", path, node.lineno,
                    f"Dead Parameter `{param}` in `{node.name}()`",
                    f"`{node.name}` fonksiyonu `{param}` parametresini kabul ediyor ama "
                    f"fonksiyon gövdesinde hiçbir yerde kullanılmıyor. "
                    f"Bu, yanıltıcı bir API yüzeyi oluşturur — çağıranlar parametreyi etkili sanır.",
                    f"DÜZELTME: Ya `{param}` parametresini fonksiyon içinde kullanın, "
                    f"ya da fonksiyon imzasından (`def {node.name}(...)`) kaldırın."
                )


def check_missing_english_shutdown_cmds(path: str, lines: list[str]):
    """
    WARNING: _is_shutdown_command içinde sadece Türkçe komutlar varsa İngilizce eksik.
    """
    for lineno, line in enumerate(lines, 1):
        if "_is_shutdown_command" in line and "def " not in line:
            continue
        if "def _is_shutdown_command" in line:
            # Sonraki 5 satırı oku
            snippet = "\n".join(lines[lineno - 1: lineno + 5])
            has_turkish = any(k in snippet for k in ["kapat", "jarvis kapan", "kendini kapat"])
            has_english = any(k in snippet for k in ["shut down", "close jarvis", "exit jarvis"])
            if has_turkish and not has_english:
                report(
                    "WARNING", path, lineno,
                    "_is_shutdown_command() Missing English Voice Commands",
                    "Kapatma komutu tespiti yalnızca Türkçe keyword'ler içeriyor. "
                    "İngilizce UI modunda 'close jarvis', 'shut down yourself' gibi sesli komutlar çalışmaz.",
                    "DÜZELTME: `_is_shutdown_command()` metodundaki listeye şunları ekleyin: "
                    "'shut down yourself', 'close yourself', 'turn off jarvis', 'close jarvis', 'exit jarvis', 'terminate yourself'"
                )


def check_stale_log_thresholds(path: str, lines: list[str]):
    """
    INFO: Log mesajlarında yanlış/eski threshold değerleri.
    """
    # Eğer "Threshold X" pattern'i var ama kod içindeki gerçek threshold farklıysa uyar
    for lineno, line in enumerate(lines, 1):
        m = re.search(r'Threshold\s+([\d.]+)', line, re.IGNORECASE)
        if m and "print" in line:
            stated = float(m.group(1))
            # Aynı dosyada gerçek threshold değerini bul
            # Basit kontrol: dosyada 0.35 veya 0.90 geçiyor mu ama log 0.25 diyor mu?
            if stated == 0.25:
                report(
                    "INFO", path, lineno,
                    "Stale Threshold Value in Log Message",
                    f"Satır {lineno}'deki log mesajı 'Threshold {stated}' diyor ama "
                    f"gerçekte kullanılan threshold değerleri kodda farklı (genellikle 0.35 normal, 0.90 personal). "
                    f"Bu, debug sırasında geliştiricileri yanıltır.",
                    f"DÜZELTME: Satır {lineno}'deki log mesajındaki '{stated}' değerini "
                    f"kodda gerçekte kullanılan threshold değerleriyle güncelleyin."
                )


def check_unused_self_attributes(path: str, lines: list[str], tree):
    """
    WARNING: __init__ içinde self.xxx = Something() atanan ama sınıfın hiçbir yerinde kullanılmayan attribute'lar.
    """
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # Tüm sınıf kaynak kodunu al
        class_src = "\n".join(lines[node.lineno - 1: node.end_lineno])

        # __init__ içindeki self.xxx = ... atamaları
        init_assigns: dict[str, int] = {}
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in ast.walk(item):
                    if (isinstance(stmt, ast.Assign) and
                            len(stmt.targets) == 1 and
                            isinstance(stmt.targets[0], ast.Attribute) and
                            isinstance(stmt.targets[0].value, ast.Name) and
                            stmt.targets[0].value.id == "self"):
                        attr = stmt.targets[0].attr
                        if attr.startswith("_"):
                            continue  # private attribute'ları atla
                        init_assigns[attr] = stmt.lineno

        # Her attribute'ın sınıf gövdesinde (init dışında) kullanılıp kullanılmadığını kontrol et
        for attr, lineno in init_assigns.items():
            # Kaç kez geçiyor?
            occurrences = len(re.findall(r'\bself\.' + re.escape(attr) + r'\b', class_src))
            if occurrences <= 1:  # Sadece atama satırında
                report(
                    "WARNING", path, lineno,
                    f"Potentially Unused Attribute `self.{attr}` in `{node.name}`",
                    f"`{node.name}.__init__` içinde `self.{attr}` atanıyor fakat "
                    f"sınıfın geri kalanında kullanıldığına dair bir işaret bulunamadı. "
                    f"Bu, ölü kod veya unimplemented bir özellik olabilir.",
                    f"DÜZELTME: `self.{attr}` gerçekten kullanılmıyorsa `{node.name}.__init__` "
                    f"içindeki satır {lineno}'i kaldırın. Eğer planlanmış bir özellikse bir TODO yorumu ekleyin."
                )


def check_os_exit(path: str, lines: list[str]):
    """
    WARNING: os._exit() kullanımı — tüm cleanup'ı atlar.
    """
    for lineno, line in enumerate(lines, 1):
        if "os._exit(" in line and not line.strip().startswith("#"):
            report(
                "WARNING", path, lineno,
                "os._exit() Bypasses All Python Cleanup",
                "`os._exit()` çağrısı Python'un tüm cleanup mekanizmasını (finally blokları, "
                "atexit handlers, __del__ metodları) devre dışı bırakır. "
                "Açık dosya handle'ları, DB bağlantıları veya in-flight async task'lar "
                "düzgün kapanmadan süreç sonlanır — veri kaybı riski taşır.",
                "DÜZELTME: `os._exit(0)` yerine koordineli bir shutdown sekansı kullanın: "
                "1) Engine'in `shutdown()` metodunu çağırın, "
                "2) Ardından `sys.exit(0)` kullanın veya `root.destroy()` ile Tkinter'ı kapatın."
            )


def check_multiword_stopwords(path: str, lines: list[str]):
    """
    INFO: Stop word listesinde çok kelimeli (boşluklu) string'ler var —
    bunlar regex word-tokenizer ile asla eşleşmez.
    """
    stopword_pattern = re.compile(r'stop_words\s*=\s*\{', re.IGNORECASE)
    in_block = False
    block_start = 0
    brace_depth = 0

    for lineno, line in enumerate(lines, 1):
        if stopword_pattern.search(line):
            in_block = True
            block_start = lineno
            brace_depth = line.count("{") - line.count("}")
            if brace_depth <= 0:
                in_block = False
            continue
        if in_block:
            brace_depth += line.count("{") - line.count("}")
            # Multi-word string var mı?
            strings = re.findall(r"'([^']*)'", line) + re.findall(r'"([^"]*)"', line)
            for s in strings:
                if " " in s.strip():
                    report(
                        "INFO", path, lineno,
                        f"Multi-Word Stop Word `'{s}'` Never Matches Tokenizer Output",
                        f"Stop words kümesi `'{s}'` gibi boşluklu bir string içeriyor. "
                        f"Ancak filtreleme kodu kelimeleri `re.findall(r'[\\w...]+', ...)` ile ayrı token'lara böler. "
                        f"Boşluklu string'ler asla tek bir token ile eşleşemez — bu stop word dead code.",
                        f"DÜZELTME: `'{s}'` string'ini tek kelimelere bölün: "
                        + ", ".join(f"'{w}'" for w in s.split()) +
                        f". Her birini ayrı ayrı stop_words kümesine ekleyin."
                    )
            if brace_depth <= 0:
                in_block = False


def check_ctk_label_text_in_apply_language(path: str, lines: list[str], tree):
    """
    WARNING: _apply_language() metodunda self.xxx.configure(text=...) çağrıları için
    o self.xxx attribute'ının gerçekten var olup olmadığını kontrol et.
    """
    if tree is None or "interface" not in path:
        return
    # _apply_language metodunu bul
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "_apply_language":
            continue
        # Bu metodun tüm satırlarını incele
        method_lines = lines[node.lineno - 1: node.end_lineno]
        configured_attrs = []
        for line in method_lines:
            m = re.search(r'self\.(\w+)\.configure\s*\(', line)
            if m:
                configured_attrs.append(m.group(1))

        # Tüm dosyada bu attribute'ların tanımlanıp tanımlanmadığını kontrol et
        full_src = "\n".join(lines)
        for attr in configured_attrs:
            # self.xxx = ... veya self.xxx: ... şeklinde tanımlama var mı?
            if not re.search(r'\bself\.' + re.escape(attr) + r'\s*=', full_src):
                report(
                    "CRITICAL", path, node.lineno,
                    f"_apply_language() References Possibly Undefined `self.{attr}`",
                    f"`_apply_language()` metodunda `self.{attr}.configure(text=...)` çağrısı var, "
                    f"ancak bu attribute'un `self.{attr} = ...` şeklinde atandığı bir satır bulunamadı. "
                    f"Eğer bu widget henüz oluşturulmamışsa `AttributeError` fırlatır.",
                    f"DÜZELTME: `self.{attr}` widget'ının `_build_ui()` veya ilgili panel metodunda "
                    f"oluşturulduğunu ve `self.{attr} = ctk.CTkLabel(...)` şeklinde atandığını doğrulayın. "
                    f"Eğer widget gerçekten oluşturulmuyor ama `_apply_language` onu güncellemeye çalışıyorsa "
                    f"ilgili `.configure()` satırını kaldırın."
                )


def check_except_pass(path: str, lines: list[str], tree):
    """
    WARNING: `except Exception: pass` veya `except: pass` — silent exception swallowing.
    """
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        # Handler gövdesi sadece Pass mu?
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            lineno = node.lineno
            report(
                "WARNING", path, lineno,
                "Silent Exception Swallowing — `except: pass`",
                f"Satır {lineno}'deki exception handler tüm hataları sessizce yutup devam ediyor. "
                f"Bu, kritik hataları tamamen gizleyerek debugging'i imkansız kılabilir.",
                f"DÜZELTME: Satır {lineno}'deki `pass` yerine en azından "
                f"`logging.getLogger(__name__).warning(f'Ignored error: {{e}}')` ekleyin."
            )


def check_tts_response_language(path: str, lines: list[str]):
    """
    INFO: brain.py içinde SPEAK protokolü Türkçe metin üretiyorsa uyar.
    Basit heuristik: f-string veya string içinde Türkçe karakter.
    """
    if "brain" not in path:
        return
    TURKISH = set("çğışöüÇĞİŞÖÜ")
    speak_inline = re.compile(r'\[PROTOCOL:\s*SPEAK\].*', re.IGNORECASE)
    for lineno, line in enumerate(lines, 1):
        if speak_inline.search(line):
            m = speak_inline.search(line)
            if m and any(c in TURKISH for c in m.group(0)):
                report(
                    "INFO", path, lineno,
                    "Turkish Text in Hardcoded SPEAK Protocol",
                    f"Satır {lineno}: Brain içinde hardcoded bir SPEAK komutu Türkçe karakter içeriyor. "
                    f"TTS motoru İngilizce — bu metin seslendirildiğinde bozuk çıkar.",
                    f"DÜZELTME: Satır {lineno}'deki Türkçe metni İngilizce karşılığıyla değiştirin."
                )


# ─────────────────────────────────────────────────────────────────────────────
#  ANA TARAYICI
# ─────────────────────────────────────────────────────────────────────────────
def audit_file(rel_path: str):
    abs_path = Path(rel_path).resolve()
    if not abs_path.exists():
        print(f"  {C.DIM}[atlandı] {rel_path} — dosya bulunamadı{C.RESET}")
        return

    text, lines = read_file(str(abs_path))
    if text is None:
        return

    tree = parse_ast(text, rel_path)

    # Tüm check'leri çalıştır
    check_syntax(rel_path, text)
    check_asyncio_lock_lazy(rel_path, lines, tree)
    check_blocking_in_async(rel_path, lines, tree)
    check_turkish_in_speak(rel_path, lines)
    check_update_gui_turkish(rel_path, lines)
    check_widget_not_packed(rel_path, lines, tree)
    check_duplicate_list_items(rel_path, lines, tree)
    check_dead_parameters(rel_path, lines, tree)
    check_missing_english_shutdown_cmds(rel_path, lines)
    check_stale_log_thresholds(rel_path, lines)
    check_unused_self_attributes(rel_path, lines, tree)
    check_os_exit(rel_path, lines)
    check_multiword_stopwords(rel_path, lines)
    check_ctk_label_text_in_apply_language(rel_path, lines, tree)
    check_except_pass(rel_path, lines, tree)
    check_tts_response_language(rel_path, lines)


# ─────────────────────────────────────────────────────────────────────────────
#  RAPOR ÇIKTISI
# ─────────────────────────────────────────────────────────────────────────────
def build_report() -> str:
    now = datetime.now()
    turkish_months = ["", "Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
                      "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
    date_str = f"{now.day} {turkish_months[now.month]} {now.year}"

    existing_files = [f for f in TARGET_FILES if Path(f).exists()]

    lines = [
        "=" * 70,
        "   J.A.R.V.I.S. AUTONOMOUS CODE AUDIT REPORT",
        "=" * 70,
        "",
        f"İncelenen dosyalar: {', '.join(Path(f).name for f in existing_files)}",
        f"İnceleme tarihi: {date_str}",
        f"Toplam bulgu: {len(findings)}",
        "",
    ]

    # Seviyelere göre grupla
    for level, color in [("CRITICAL", "🔴"), ("WARNING", "🟡"), ("INFO", "🔵")]:
        level_findings = [f for f in findings if f.level == level]
        if not level_findings:
            continue
        lines.append(f"{'─' * 70}")
        lines.append(f"  {color}  {level} ({len(level_findings)} adet)")
        lines.append(f"{'─' * 70}")
        for i, f in enumerate(level_findings, 1):
            lines.append(f"\n[{level} #{i}]")
            lines.append(f"  Dosya : {f.file}")
            lines.append(f"  Satır : {f.line}")
            lines.append(f"  Başlık: {f.title}")
            lines.append(f"  Sorun : {f.detail}")
            lines.append(f"  ✅ FIX: {f.fix}")
        lines.append("")

    if not findings:
        lines.append("  ✅ Hiçbir sorun bulunamadı. Harika iş!")

    lines += [
        "=" * 70,
        "  ÖZET TABLOSU",
        "=" * 70,
        f"  {'#':<4} {'SEVİYE':<10} {'DOSYA':<25} {'BAŞLIK'}",
        f"  {'─'*4} {'─'*10} {'─'*25} {'─'*30}",
    ]
    for i, f in enumerate(sorted(findings, key=lambda x: x.order), 1):
        fname = Path(f.file).name
        title_short = f.title[:38] + ("..." if len(f.title) > 38 else "")
        lines.append(f"  {i:<4} {f.level:<10} {fname:<25} {title_short}")

    lines += [
        "",
        f"  CRITICAL : {sum(1 for f in findings if f.level == 'CRITICAL')}",
        f"  WARNING  : {sum(1 for f in findings if f.level == 'WARNING')}",
        f"  INFO     : {sum(1 for f in findings if f.level == 'INFO')}",
        "=" * 70,
    ]
    return "\n".join(lines)


def print_colored_report():
    now = datetime.now()
    turkish_months = ["", "Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
                      "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
    date_str = f"{now.day} {turkish_months[now.month]} {now.year}"
    existing_files = [f for f in TARGET_FILES if Path(f).exists()]

    print(f"\n{C.BOLD}{'=' * 70}{C.RESET}")
    print(f"{C.BOLD}   J.A.R.V.I.S. AUTONOMOUS CODE AUDIT REPORT{C.RESET}")
    print(f"{C.BOLD}{'=' * 70}{C.RESET}\n")
    print(f"İncelenen dosyalar: {C.CYAN}{', '.join(Path(f).name for f in existing_files)}{C.RESET}")
    print(f"İnceleme tarihi   : {C.CYAN}{date_str}{C.RESET}")
    print(f"Toplam bulgu      : {C.BOLD}{len(findings)}{C.RESET}\n")

    COLORS = {"CRITICAL": C.RED, "WARNING": C.YELLOW, "INFO": C.CYAN}
    ICONS  = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}

    for level in ["CRITICAL", "WARNING", "INFO"]:
        level_findings = [f for f in findings if f.level == level]
        if not level_findings:
            continue
        clr = COLORS[level]
        print(f"{clr}{'─' * 70}{C.RESET}")
        print(f"{clr}{C.BOLD}  {ICONS[level]}  {level} ({len(level_findings)} adet){C.RESET}")
        print(f"{clr}{'─' * 70}{C.RESET}")
        for i, f in enumerate(level_findings, 1):
            print(f"\n{clr}[{level} #{i}]{C.RESET}")
            print(f"  {C.DIM}Dosya :{C.RESET} {f.file}:{f.line}")
            print(f"  {C.BOLD}Başlık:{C.RESET} {f.title}")
            print(f"  Sorun : {f.detail}")
            print(f"  {C.GREEN}✅ FIX:{C.RESET} {f.fix}")
        print()

    if not findings:
        print(f"  {C.GREEN}✅ Hiçbir sorun bulunamadı. Harika iş!{C.RESET}")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{C.DIM}Taranıyor...{C.RESET}")

    # Script'in çalıştığı dizinden dosyaları bul
    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    for rel_path in TARGET_FILES:
        print(f"  {C.DIM}→ {rel_path}{C.RESET}")
        audit_file(rel_path)

    print()
    print_colored_report()

    # Dosyaya kaydet (renksiz, temiz metin)
    report_text = build_report()
    output_path = script_dir / "audit_report.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\n{C.GREEN}📄 Rapor kaydedildi → audit_report.txt{C.RESET}")
    print(f"{C.DIM}   Bu dosyayı kopyalayıp AI'ya yapıştırabilirsiniz.{C.RESET}\n")


if __name__ == "__main__":
    main()
