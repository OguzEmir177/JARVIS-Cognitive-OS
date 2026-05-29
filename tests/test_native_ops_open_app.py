"""test_native_ops_open_app.py — NativeOps.open_app multilayered strategy tests.

All subprocess/os/psutil/time calls are mocked; the actual application is not started.

V8.4 Updates:
    - Added psutil process validation mocks after Popen
    - APP_MAP: testing epic games, whatsapp updates
    - Added _verify_process unit tests
    - Time.sleep was mocked to ensure that the tests remained fast"""

import os
import subprocess
from unittest.mock import patch, MagicMock, call

import pytest

from tools.utils.native_ops import NativeOps


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _popen_ok(*args, **kwargs):
    """Simulates a successful Popen call."""
    return MagicMock()


def _popen_fail(*args, **kwargs):
    """Simulates a failed Popen call."""
    raise OSError("popen failed")


def _startfile_ok(target):
    """Successful os.startfile simulation."""
    return None


def _startfile_fail(target):
    """Failed os.startfile simulation."""
    raise OSError("startfile failed")


def _make_proc(name: str):
    """Returns a dummy psutil process object."""
    proc = MagicMock()
    proc.info = {"name": name}
    return proc


# ─────────────────────────────────────────────────────────────────────────────
# Common patch decorator: time.sleep resets everywhere
# ─────────────────────────────────────────────────────────────────────────────

_SLEEP_PATCH = patch("tools.utils.native_ops.time.sleep")


# ─────────────────────────────────────────────────────────────────────────────
# _APP_MAP Analysis Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAppMapResolution:
    """Verifies that known application names are mapped to the correct exe."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_discord_maps_to_discord(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("discord")
        assert result.startswith("SUCCESSFUL")
        mock_popen.assert_called_once_with(["discord"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_vscode_maps_to_code(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("vscode")
        assert result.startswith("SUCCESSFUL")
        mock_popen.assert_called_once_with(["code"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_vs_code_maps_to_code(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("vs code")
        assert result.startswith("SUCCESSFUL")
        mock_popen.assert_called_once_with(["code"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_chrome_maps_to_chrome(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("chrome")
        assert result.startswith("SUCCESSFUL")
        mock_popen.assert_called_once_with(["chrome"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_whatsapp_maps_to_whatsapp(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("whatsapp")
        assert result.startswith("SUCCESSFUL")
        mock_popen.assert_called_once_with("start whatsapp:", shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    @patch("tools.utils.native_ops.NativeOps._resolve_app_map",
           return_value=r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe")
    def test_epic_games_maps_to_launcher(self, mock_resolve, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("epic games")
        assert result.startswith("SUCCESSFUL")
        mock_resolve.assert_called_once_with("epic games")

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    @patch("tools.utils.native_ops.NativeOps._resolve_app_map",
           return_value=r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe")
    def test_epic_shorthand_maps_to_launcher(self, mock_resolve, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("epic")
        assert result.startswith("SUCCESSFUL")
        mock_resolve.assert_called_once_with("epic")


# ─────────────────────────────────────────────────────────────────────────────
#  _resolve_app_map Birim Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveAppMap:
    """_resolve_app_map: str, list, and unknown app resolution."""

    def test_str_value_returns_directly(self):
        """str value should be returned directly."""
        assert NativeOps._resolve_app_map("discord") == "discord"
        assert NativeOps._resolve_app_map("vscode") == "code"

    @patch("tools.utils.native_ops.os.path.exists", side_effect=lambda p: "Win32" in p)
    def test_list_value_returns_first_existing(self, mock_exists):
        """list should return the first available path in the value."""
        result = NativeOps._resolve_app_map("epic games")
        assert "Win32" in result
        assert result.endswith(".exe")

    @patch("tools.utils.native_ops.os.path.exists", return_value=False)
    def test_list_value_no_existing_returns_last(self, mock_exists):
        """If there is no path, the last element in the list should be returned."""
        result = NativeOps._resolve_app_map("epic")
        paths = NativeOps._APP_MAP["epic"]
        assert result == paths[-1]

    def test_unknown_app_returns_clean_name(self):
        """The application that is not in the MAP should return with its raw name."""
        assert NativeOps._resolve_app_map("xyz123") == "xyz123"

    def test_app_map_epic_is_list(self):
        """'epic' and 'epic games' values ​​should be list."""
        assert isinstance(NativeOps._APP_MAP["epic"], list)
        assert isinstance(NativeOps._APP_MAP["epic games"], list)
        assert len(NativeOps._APP_MAP["epic"]) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Transition (Fallback) Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategyFallback:
    """It confirms that when each strategy fails, it is handed over to the next one."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_strategy1_succeeds_immediately(self, mock_popen, mock_verify, mock_sleep):
        """If Strategy 1 is successful, Strategy 2/3 should not be called."""
        result = NativeOps.open_app("notepad")
        assert "SUCCESSFUL" in result
        assert mock_popen.call_count == 1

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_ok)
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=False)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_popen_ok_but_no_process_falls_to_startfile(
        self, mock_popen, mock_verify, mock_startfile, mock_sleep
    ):
        """Popen does not throw an exception, but psutil cannot find a process → it falls into the startfile."""
        result = NativeOps.open_app("notepad")
        assert "SUCCESSFUL" in result
        # Popen 2 kez (S1+S2), verify 2 kez, sonra startfile
        assert mock_popen.call_count == 2
        mock_startfile.assert_called_once_with("notepad")

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_ok)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_fail)
    def test_fallback_to_strategy3_startfile(self, mock_popen, mock_startfile, mock_sleep):
        """Popen should always fall into exception → os.startfile (Strategy 3)."""
        result = NativeOps.open_app("notepad")
        assert "SUCCESSFUL" in result
        assert mock_popen.call_count == 2
        mock_startfile.assert_called_once_with("notepad")

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_fail)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_fail)
    def test_all_strategies_fail(self, mock_popen, mock_startfile, mock_sleep):
        """If all strategies fail, FAIL should be returned."""
        result = NativeOps.open_app("nonexistent_app_xyz")
        assert "UNSUCCESSFUL" in result

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
        """S1 Popen OK but verify fail → S2 verify OK → startfile should not be called."""
        result = NativeOps.open_app("firefox")
        assert "SUCCESSFUL" in result
        assert mock_popen.call_count == 2
        mock_startfile.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Process Verification (psutil) Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestProcessVerification:
    """Verifies that _verify_process works correctly with psutil."""

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
        """'vscode' → Should be searched for 'code' in _PROCESS_NAMES."""
        mock_iter.return_value = [
            _make_proc("Code.exe"),
        ]
        assert NativeOps._verify_process("vscode", "code") is True

    @patch("tools.utils.native_ops.psutil.process_iter")
    def test_verify_unknown_app_uses_target(self, mock_iter):
        """The name app → target, which is not in _PROCESS_NAMES, should be used."""
        mock_iter.return_value = [
            _make_proc("myapp.exe"),
        ]
        assert NativeOps._verify_process("myapp", "myapp") is True

    @patch("tools.utils.native_ops.psutil.process_iter")
    def test_verify_handles_access_denied(self, mock_iter):
        """psutil.AccessDenied should be safely omitted."""
        import psutil as _psutil

        bad_proc = MagicMock()
        bad_proc.info.__getitem__ = MagicMock(side_effect=_psutil.AccessDenied(1))

        mock_iter.return_value = [bad_proc]
        assert NativeOps._verify_process("discord", "discord") is False

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_sleep_called_before_verify(self, mock_popen, mock_verify, mock_sleep):
        """1.5s time.sleep should be called after Popen."""
        NativeOps.open_app("discord")
        mock_sleep.assert_called_with(1.5)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=False)
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_fail)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_popen_success_but_verify_fails_returns_basarili_via_shell(
        self, mock_popen, mock_startfile, mock_verify, mock_sleep
    ):
        """[V8.6] APP_MAP fails verify -> Start Menu fails -> psutil fails -> Shell Exec as fallback returns SUCCESSFUL."""
        result = NativeOps.open_app("nonexistent_app_xyz")
        assert "SUCCESSFUL" in result
        assert "shell" in result


# ─────────────────────────────────────────────────────────────────────────────
#  Girdi Normalizasyon Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestInputNormalization:
    """Verifies case/whitespace normalization."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_uppercase_input(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("DISCORD")
        assert "SUCCESSFUL" in result
        mock_popen.assert_called_once_with(["discord"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_whitespace_trimmed(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("  Spotify  ")
        assert "SUCCESSFUL" in result
        mock_popen.assert_called_once_with(["spotify"], shell=True)

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_mixed_case_with_spaces(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("  VS Code  ")
        assert "SUCCESSFUL" in result
        mock_popen.assert_called_once_with(["code"], shell=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Bilinmeyen Uygulama Testleri
# ─────────────────────────────────────────────────────────────────────────────

class TestUnknownApp:
    """Verifies that applications not in _APP_MAP are tried with the raw name."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_unknown_app_passes_raw_name(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("someRandomApp")
        assert "SUCCESSFUL" in result
        mock_popen.assert_called_once_with('start "" "someRandomApp"', shell=True)


# ─────────────────────────────────────────────────────────────────────────────
# Return Format Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReturnFormat:
    """Verifies that the return string complies with the contract."""

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.NativeOps._verify_process", return_value=True)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_ok)
    def test_success_format(self, mock_popen, mock_verify, mock_sleep):
        result = NativeOps.open_app("notepad")
        assert result == "SUCCESSFUL: notepad started."

    @_SLEEP_PATCH
    @patch("tools.utils.native_ops.os.startfile", side_effect=_startfile_fail)
    @patch("tools.utils.native_ops.subprocess.Popen", side_effect=_popen_fail)
    def test_failure_format(self, mock_popen, mock_startfile, mock_sleep):
        result = NativeOps.open_app("fail_app")
        assert result.startswith("UNSUCCESSFUL:")


# ─────────────────────────────────────────────────────────────────────────────
# Signature Contract Test
# ─────────────────────────────────────────────────────────────────────────────

class TestSignatureContract:
    """Verifies that the signature of open_app has not changed."""

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
# Import Security Test
# ─────────────────────────────────────────────────────────────────────────────

class TestImportSafety:
    """Verifies that the module does not debug print to stderr."""

    def test_no_stderr_debug_print(self):
        """There should be no print calls to sys.stderr in native_ops.py."""
        import inspect
        source = inspect.getsource(NativeOps)
        assert "print(" not in source or "file=sys.stderr" not in source
