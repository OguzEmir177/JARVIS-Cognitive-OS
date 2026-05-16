@echo off
:: J.A.R.V.I.S. v5.9 Stable - Arka Plan Başlatıcı
:: Bu dosya J.A.R.V.I.S.'i Pythonw (Headless) modunda başlatır.

setlocal
cd /d "%~dp0"

echo [STARTUP] J.A.R.V.I.S. sistemi arka planda uyandırılıyor...
start "" pythonw.exe "launch_jarvis.pyw"

exit
