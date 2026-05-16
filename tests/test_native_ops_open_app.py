"""
test_native_ops_open_app.py — NativeOps.open_app çok katmanlı strateji testleri.

Tüm subprocess/os/psutil/time çağrıları mock'lanır; gerçek uygulama başlatılmaz.

V8.4 Güncellemeleri:
    - Popen sonrası psutil süreç doğrulama mock'ları eklendi
    - APP_MAP: epic games, whatsapp güncellemeleri test ediliyor
    - _verify_process birim testleri eklendi
    - time.sleep mock'lanarak testlerin hızlı kalması sağlandı
"""

import os
import subprocess
from unittest.mock import patch, MagicMock, call

import pytest

from tools.utils.native_ops import NativeOps


# ─────────────────────────────────────────────────────────────────────────────
#  Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────

def _popen_ok(*args, **kwargs):
    """Başarılı bir Popen çağrısını simüle eder."""
    return MagicMock()


def _popen_fail(*args, **kwargs):
    """Başarısız bir Popen çağrısını simüle eder."""
    raise OSError("popen failed")


def _startfile_ok(target):
    """Başarılı os.startfile simülasyonu."""
    return None


def _startfile_fail(target):
    """Başarısız os.startfile simülasyonu."""
    raise OSError("startfile failed")


def _make_proc(name: str):
    """Sahte bir psutil process nesnesi döner."""
    proc = MagicMock()
    proc.info = {"name": name}
    return proc


# ─────────────────────────────────────────────────────────────────────────────
#  Ortak patch dekoratörü: time.sleep her yerde sıfırlanır
# ─────────────────────────────────────────────────────────────────────────────

_SLEEP_PATCH = patch("tools.utils.native_ops.time.sleep")


# ─────────────────────────────────────────────────────────────────────────────
#  _APP_MAP Çözümleme Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestAppMapResolution:
    """Bilinen uygulama adlarının doğru exe'ye eşlendiğini doğrular."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_discord_maps_to_discord(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("discord")
        assert result.startswith("BAŞARILI")
        mock_popen.assert_called_once_with(["discord"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_vscode_maps_to_code(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("vscode")
        assert result.startswith("BAŞARILI")
        mock_popen.assert_called_once_with(["code"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_vs_code_maps_to_code(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("vs code")
        assert result.startswith("BAŞARILI")
        mock_popen.assert_called_once_with(["code"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_chrome_maps_to_chrome(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("chrome")
        assert result.startswith("BAŞARILI")
        mock_popen.assert_called_once_with(["chrome"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_whatsapp_maps_to_whatsapp(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("whatsapp")
        assert result.startswith("BAŞARILI")
        mock_popen.assert_called_once_with("start whatsapp:", shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    @patch("tools.utils.native_ops.NativeOps._resolve_app_map",
           return_value=r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe")
    def test_epic_games_maps_to_launcher(self, mock_resolve, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("epic games")
        assert result.startswith("BAŞARILI")
        mock_resolve.assert_called_once_with("epic games")

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    @patch("tools.utils.native_ops.NativeOps._resolve_app_map",
           return_value=r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe")
    def test_epic_shorthand_maps_to_launcher(self, mock_resolve, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("epic")
        assert result.startswith("BAŞARILI")
        mock_resolve.assert_called_once_with("epic")


# ─────────────────────────────────────────────────────────────────────────────
#  _resolve_app_map Birim Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveAppMap:
    """_resolve_app_map: str, list, ve bilinmeyen uygulama çözümleme."""

    def test_str_value_returns_directly(self):
        """str değer doğrudan dönmeli."""
        assert NativeOps._resolve_app_map("discord") == "discord"
        assert NativeOps._resolve_app_map("vscode") == "code"

    @patch("tools.utils.native_ops.os.path.exists", side_effect=lambda p: "Win32" in p)
    def test_list_value_returns_first_existing(self, mock_exists):
        """list değerde ilk mevcut yol dönmeli."""
        result = NativeOps._resolve_app_map("epic games")
        assert "Win32" in result
        assert result.endswith(".exe")

    @patch("tools.utils.native_ops.os.path.exists", return_value=False)
    def test_list_value_no_existing_returns_last(self, mock_exists):
        """Hiçbir yol yoksa listedeki son eleman dönmeli."""
        result = NativeOps._resolve_app_map("epic")
        paths = NativeOps._APP_MAP["epic"]
        assert result == paths[-1]

    def test_unknown_app_returns_clean_name(self):
        """MAP'te olmayan uygulama ham ismiyle dönmeli."""
        assert NativeOps._resolve_app_map("xyz123") == "xyz123"

    def test_app_map_epic_is_list(self):
        """'epic' ve 'epic games' değerleri list olmalı."""
        assert isinstance(NativeOps._APP_MAP["epic"], list)
        assert isinstance(NativeOps._APP_MAP["epic games"], list)
        assert len(NativeOps._APP_MAP["epic"]) >= 2


# ─────────────────────────────────────────────────────────────────────────────
#  Strateji Geçiş (Fallback) Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategyFallback:
    """Her stratejinin başarısızlıkta sıradakine devrettiğini doğrular."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_strategy1_succeeds_immediately(self, mock_popen, mock_verify, mock_sleep):
        """Strateji 1 başarılıysa Strateji 2/3 çağrılmamalı."""
        result = NativeOps.open_app("notepad")
        assert "BAŞARILI" in result
        assert mock_popen.call_count == 1

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_ok)
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=False)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_popen_ok_but_no_process_falls_to_startfile(
        self, mock_popen, mock_verify, mock_startfile, mock_sleep
    ):
        """Popen exception vermez ama psutil süreç bulamaz → startfile'a düşer."""
        result = NativeOps.open_app("notepad")
        assert "BAŞARILI" in result
        # Popen 2 kez (S1+S2), verify 2 kez, sonra startfile
        assert mock_popen.call_count == 2
        mock_startfile.assert_called_once_with("notepad")

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_ok)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_fail)
    def test_fallback_to_strategy3_startfile(self, mock_popen, mock_startfile, mock_sleep):
        """Popen hep exception → os.startfile'a (Strateji 3) düşmeli."""
        result = NativeOps.open_app("notepad")
        assert "BAŞARILI" in result
        assert mock_popen.call_count == 2
        mock_startfile.assert_called_once_with("notepad")

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_fail)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_fail)
    def test_all_strategies_fail(self, mock_popen, mock_startfile, mock_sleep):
        """Tüm stratejiler başarısızsa BAŞARISIZ dönmeli."""
        result = NativeOps.open_app("nonexistent_app_xyz")
        assert "BAŞARISIZ" in result

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_ok)
    @patch(
        "tools.utils.native_ops.NativeOps._verify_process",
        side_effect=[False, True],  # S1 bulamaz, S2 bulur
    )
    @patch(
        "tools.utils.native_ops.subprocess.Popen",
        side_effect=[MagicMock(), MagicMock()],
    )
    def test_strategy2_start_command_succeeds(
        self, mock_popen, mock_verify, mock_startfile, mock_sleep
    ):
        """S1 Popen OK ama verify fail → S2 verify OK → startfile çağrılmamalı."""
        result = NativeOps.open_app("firefox")
        assert "BAŞARILI" in result
        assert mock_popen.call_count == 2
        mock_startfile.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
#  Süreç Doğrulama (psutil) Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessVerification:
    """_verify_process'in psutil ile doğru çalıştığını doğrular."""

    @patch("tools.utils.native_ops.psutil.process_iter")
    def test_verify_finds_matching_process(self, mock_iter):
        mock_iter.return_value = [
            _make_proc("System"),
            _make_proc("discord.exe"),
            _make_proc("svchost.exe"),
        ]
        assert NativeOps._verify_process("discord", "discord") is True

    @patch("tools.utils.native_ops.psutil.process_iter")
    def test_verify_no_matching_process(self, mock_iter):
        mock_iter.return_value = [
            _make_proc("System"),
            _make_proc("svchost.exe"),
        ]
        assert NativeOps._verify_process("discord", "discord") is False

    @patch("tools.utils.native_ops.psutil.process_iter")
    def test_verify_uses_process_names_map(self, mock_iter):
        """'vscode' → _PROCESS_NAMES'de 'code' olarak aranmalı."""
        mock_iter.return_value = [
            _make_proc("Code.exe"),
        ]
        assert NativeOps._verify_process("vscode", "code") is True

    @patch("tools.utils.native_ops.psutil.process_iter")
    def test_verify_unknown_app_uses_target(self, mock_iter):
        """_PROCESS_NAMES'te olmayan app → target ismi kullanılmalı."""
        mock_iter.return_value = [
            _make_proc("myapp.exe"),
        ]
        assert NativeOps._verify_process("myapp", "myapp") is True

    @patch("tools.utils.native_ops.psutil.process_iter")
    def test_verify_handles_access_denied(self, mock_iter):
        """psutil.AccessDenied güvenle atlanmalı."""
        import psutil as _psutil

        bad_proc = MagicMock()
        bad_proc.info.__getitem__ = MagicMock(side_effect=_psutil.AccessDenied(1))

        mock_iter.return_value = [bad_proc]
        assert NativeOps._verify_process("discord", "discord") is False

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_sleep_called_before_verify(self, mock_popen, mock_verify, mock_sleep):
        """Popen'dan sonra 1.5s time.sleep çağrılmalı."""
        NativeOps.open_app("discord")
        mock_sleep.assert_called_with(1.5)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=False)
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_fail)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_popen_success_but_verify_fails_returns_basarili_via_shell(
        self, mock_popen, mock_startfile, mock_verify, mock_sleep
    ):
        """[V8.6] APP_MAP fails verify -> Start Menu fails -> psutil fails -> Shell Exec as fallback returns BAŞARILI."""
        result = NativeOps.open_app("nonexistent_app_xyz")
        assert "BAŞARILI" in result
        assert "shell" in result


# ─────────────────────────────────────────────────────────────────────────────
#  Girdi Normalizasyon Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestInputNormalization:
    """Case/whitespace normalizasyonunu doğrular."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_uppercase_input(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("DISCORD")
        assert "BAŞARILI" in result
        mock_popen.assert_called_once_with(["discord"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_whitespace_trimmed(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("  Spotify  ")
        assert "BAŞARILI" in result
        mock_popen.assert_called_once_with(["spotify"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_mixed_case_with_spaces(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("  VS Code  ")
        assert "BAŞARILI" in result
        mock_popen.assert_called_once_with(["code"], shell=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Bilinmeyen Uygulama Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestUnknownApp:
    """_APP_MAP'te olmayan uygulamaların ham adla denendiğini doğrular."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_unknown_app_passes_raw_name(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("someRandomApp")
        assert "BAŞARILI" in result
        mock_popen.assert_called_once_with('start "" "someRandomApp"', shell=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Dönüş Formatı Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestReturnFormat:
    """Dönüş stringinin sözleşmeye uyduğunu doğrular."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_success_format(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("notepad")
        assert result == "BAŞARILI: notepad başlatıldı."

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_fail)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_fail)
    def test_failure_format(self, mock_popen, mock_startfile, mock_sleep):
        result = NativeOps.open_app("fail_app")
        assert result.startswith("BAŞARISIZ:")


# ─────────────────────────────────────────────────────────────────────────────
#  İmza Sözleşme Testi
# ─────────────────────────────────────────────────────────────────────────────

class TestSignatureContract:
    """open_app'in imzasının değişmediğini doğrular."""

    def test_is_static_method(self):
        assert isinstance(
            NativeOps.__dict__["open_app"], staticmethod
        )

    def test_accepts_single_string_arg(self):
        import inspect
        sig = inspect.signature(NativeOps.open_app)
        params = list(sig.parameters.keys())
        assert params == ["app_name"]

    def test_return_type_is_str(self):
        import inspect
        sig = inspect.signature(NativeOps.open_app)
        assert sig.return_annotation is str

    def test_verify_process_is_static(self):
        assert isinstance(
            NativeOps.__dict__["_verify_process"], staticmethod
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Import Güvenliği Testi
# ─────────────────────────────────────────────────────────────────────────────

class TestImportSafety:
    """Modülün stderr'e debug print basmadığını doğrular."""

    def test_no_stderr_debug_print(self):
        """native_ops.py'de sys.stderr'e print çağrısı bulunmamalı."""
        import inspect
        source = inspect.getsource(NativeOps)
        assert "print(" not in source or "file=sys.stderr" not in source
