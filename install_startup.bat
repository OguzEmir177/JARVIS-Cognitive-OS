@echo off
:: J.A.R.V.I.S. v5.9 Stable - Kurulum Sihirbazı
:: Bu dosya J.A.R.V.I.S.'i Windows Başlangıç klasörüne (Startup) ekler.

setlocal
set "SCRIPT_PATH=%~dp0startup_jarvis.bat"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LNK_NAME=JARVIS_AUTORUN.lnk"

echo [KURULUM] J.A.R.V.I.S. Otomatik Başlatma kuruluyor...

powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%STARTUP_FOLDER%\%LNK_NAME%'); $Shortcut.TargetPath = '%SCRIPT_PATH%'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.Save()"

if %ERRORLEVEL% EQU 0 (
    echo [BAŞARILI] J.A.R.V.I.S. artık Windows açıldığında otomatik olarak sizi duyacak.
    echo Konum: %STARTUP_FOLDER%
) else (
    echo [HATA] Kurulum sırasında bir sorun oluştu. Lütfen yönetici haklarını kontrol edin.
)

pause
exit
