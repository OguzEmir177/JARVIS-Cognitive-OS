@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

:: ============================================================
::  Renk ve ekran ayarları
:: ============================================================
color 0A
mode con: cols=72 lines=40
title J.A.R.V.I.S. Kurulum Sihirbazı

:: ============================================================
::  KARŞILAMA EKRANI
:: ============================================================
cls
echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║                                                                  ║
echo  ║        ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗                  ║
echo  ║        ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝                  ║
echo  ║        ██║███████║██████╔╝██║   ██║██║███████╗                  ║
echo  ║   ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║                  ║
echo  ║   ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║                  ║
echo  ║    ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝                  ║
echo  ║                                                                  ║
echo  ║          Just A Rather Very Intelligent System                   ║
echo  ║                                                                  ║
echo  ╠══════════════════════════════════════════════════════════════════╣
echo  ║                                                                  ║
echo  ║              K U R U L U M   S İ H İ R B A Z I                  ║
echo  ║                    v1.0  —  Hoş Geldiniz                        ║
echo  ║                                                                  ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.
echo.
timeout /t 2 /nobreak >nul

:: ============================================================
::  ÇALIŞMA DİZİNİNİ BELİRLE
:: ============================================================
set "PROJ_DIR=%~dp0"
:: Sondaki ters eğik çizgiyi kaldır
if "%PROJ_DIR:~-1%"=="\" set "PROJ_DIR=%PROJ_DIR:~0,-1%"

:: ============================================================
::  [1/6]  PYTHON KONTROLÜ
:: ============================================================
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │  [1/7]  Python Kontrolü                                          │
echo  └──────────────────────────────────────────────────────────────────┘
echo.

python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo.
    echo  ╔══════════════════════════════════════════════════════════════════╗
    echo  ║                      !!!  HATA  !!!                             ║
    echo  ╠══════════════════════════════════════════════════════════════════╣
    echo  ║                                                                  ║
    echo  ║   Python bulunamadı!                                             ║
    echo  ║                                                                  ║
    echo  ║   Lütfen aşağıdaki adresten Python'u indirin ve kurun:           ║
    echo  ║                                                                  ║
    echo  ║       https://www.python.org/downloads/                          ║
    echo  ║                                                                  ║
    echo  ║   Kurulum sırasında en alttaki                                   ║
    echo  ║                                                                  ║
    echo  ║       >>> "Add Python to PATH" <<<                               ║
    echo  ║                                                                  ║
    echo  ║   kutucuğunu KESİNLİKLE işaretleyin!                            ║
    echo  ║   Aksi hâlde J.A.R.V.I.S. çalışmayacaktır.                     ║
    echo  ║                                                                  ║
    echo  ╚══════════════════════════════════════════════════════════════════╝
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo      [OK]  %PYVER% tespit edildi.
echo.
timeout /t 1 /nobreak >nul

:: ============================================================
::  [2/6]  SANAL ORTAM (venv)
:: ============================================================
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │  [2/7]  Sanal Ortam Oluşturuluyor (venv)                         │
echo  └──────────────────────────────────────────────────────────────────┘
echo.

set "VENV_DIR=%PROJ_DIR%\venv"

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo      [OK]  Mevcut venv bulundu, atlanıyor...
) else (
    echo      Sanal ortam oluşturuluyor, lütfen bekleyin...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        color 0C
        echo.
        echo      [HATA]  Sanal ortam oluşturulamadı!
        echo              Lütfen Python kurulumunuzu kontrol edin.
        echo.
        pause
        exit /b 1
    )
    echo      [OK]  Sanal ortam oluşturuldu.
)
echo.
timeout /t 1 /nobreak >nul

:: ============================================================
::  [3/6]  BAĞIMLILIKLARIN KURULUMU
:: ============================================================
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │  [3/7]  Kütüphaneler Kuruluyor (requirements.txt)                │
echo  └──────────────────────────────────────────────────────────────────┘
echo.

if not exist "%PROJ_DIR%\requirements.txt" (
    color 0E
    echo      [UYARI]  requirements.txt bulunamadı, bu adım atlanıyor.
) else (
    echo      Pip güncelleniyor...
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip --quiet
    echo.
    echo      Kütüphaneler kuruluyor, bu işlem birkaç dakika sürebilir...
    echo      (İnternet bağlantınızın aktif olduğundan emin olun)
    echo.
    "%VENV_DIR%\Scripts\pip.exe" install -r "%PROJ_DIR%\requirements.txt"
    if errorlevel 1 (
        color 0C
        echo.
        echo      [HATA]  Kütüphane kurulumu başarısız!
        echo              İnternet bağlantınızı kontrol edip tekrar deneyin.
        echo.
        pause
        exit /b 1
    )
    echo.
    echo      [OK]  Tüm kütüphaneler başarıyla kuruldu.
)
echo.
timeout /t 1 /nobreak >nul

:: ============================================================
::  [4/7]  FFMPEG KURULUMU
:: ============================================================
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │  [4/7]  FFmpeg İndiriliyor ve Kuruluyor                        │
echo  └──────────────────────────────────────────────────────────────────┘
echo.

set "FFMPEG_DIR=%PROJ_DIR%\ffmpeg"
if exist "%FFMPEG_DIR%\bin\ffmpeg.exe" (
    echo      [OK]  FFmpeg zaten mevcut, atlanıyor...
) else (
    echo      FFmpeg (Gyan.dev) indiriliyor, lütfen bekleyin...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%TEMP%\ffmpeg.zip' -ErrorAction Stop } catch { Write-Error 'İnternet bağlantısı koptu veya erişim reddedildi.'; exit 1 }"
    if errorlevel 1 (
        color 0C
        echo.
        echo      [HATA]  FFmpeg indirilemedi! İnternet bağlantınızı kontrol edin.
        echo.
        pause
        exit /b 1
    )
    
    echo      FFmpeg zip'ten çıkarılıyor...
    powershell -Command "try { Expand-Archive -Path '%TEMP%\ffmpeg.zip' -DestinationPath '%TEMP%\ffmpeg_ext' -Force -ErrorAction Stop } catch { Write-Error 'Zip çıkarma hatası.'; exit 1 }"
    if errorlevel 1 (
        color 0C
        echo.
        echo      [HATA]  FFmpeg zip dosyası çıkarılamadı!
        echo.
        pause
        exit /b 1
    )
    
    :: Klasör ismini tespit edip ffmpeg içine taşıma
    for /d %%d in ("%TEMP%\ffmpeg_ext\ffmpeg-*") do (
        move /Y "%%d" "%FFMPEG_DIR%" >nul
    )
    
    del "%TEMP%\ffmpeg.zip" >nul 2>&1
    rd /s /q "%TEMP%\ffmpeg_ext" >nul 2>&1
    
    echo      [OK]  FFmpeg başarıyla kuruldu.
)

:: PATH'e ekleme (Kullanıcı için)
echo      FFmpeg PATH'e ekleniyor...
powershell -Command "$userPath = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($userPath -notmatch [regex]::Escape('%FFMPEG_DIR%\bin')) { [Environment]::SetEnvironmentVariable('Path', $userPath + ';%FFMPEG_DIR%\bin', 'User') }"

echo.
timeout /t 1 /nobreak >nul

:: ============================================================
::  [5/7]  API KEY VE .env DOSYASI
:: ============================================================
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │  [5/7]  API Anahtarı Yapılandırması                              │
echo  └──────────────────────────────────────────────────────────────────┘
echo.

set "ENV_FILE=%PROJ_DIR%\.env"

if exist "%ENV_FILE%" (
    echo      [OK]  Mevcut .env dosyası bulundu.
    echo      Mevcut yapılandırmanızı korumak ister misiniz?
    echo.
    echo         [1]  Evet, mevcut .env dosyasını koru  (Önerilen)
    echo         [2]  Hayır, yeni API Key gir
    echo.
    set /p "ENV_CHOICE=      Seçiminiz (1/2): "
    if "!ENV_CHOICE!"=="2" goto :ask_api_key
    echo.
    echo      [OK]  Mevcut .env dosyası korundu.
    goto :env_done
)

:ask_api_key
echo.
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │   Groq API Key'inizi nereden alabilirsiniz:                      │
echo  │                                                                  │
echo  │       https://console.groq.com/keys                             │
echo  │                                                                  │
echo  │   Siteye gidin  →  Üye olun / Giriş yapın  →  "Create API Key" │
echo  └──────────────────────────────────────────────────────────────────┘
echo.
set /p "GROQ_KEY=      Groq API Key'inizi buraya yapıştırın: "

if "!GROQ_KEY!"=="" (
    color 0E
    echo.
    echo      [UYARI]  API Key girilmedi. .env dosyası boş bırakıldı.
    echo               J.A.R.V.I.S.'i ilk çalıştırmada tekrar sorulacak.
    (
        echo GROQ_API_KEY=
    ) > "%ENV_FILE%"
    goto :env_done
)

(
    echo GROQ_API_KEY=!GROQ_KEY!
) > "%ENV_FILE%"
echo.
echo      [OK]  .env dosyası oluşturuldu ve API Key kaydedildi.

:env_done
echo.
timeout /t 1 /nobreak >nul

:: ============================================================
::  [6/7]  contacts.json KORUMASI
:: ============================================================
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │  [6/7]  contacts.json Kontrolü                                   │
echo  └──────────────────────────────────────────────────────────────────┘
echo.

set "CONTACTS_FILE=%PROJ_DIR%\contacts.json"

if exist "%CONTACTS_FILE%" (
    echo      [OK]  contacts.json mevcut, dokunulmadı.
) else (
    echo      contacts.json bulunamadı, şablon oluşturuluyor...
    (
        echo {
        echo     "Örnek Kişi": "+905550000000"
        echo }
    ) > "%CONTACTS_FILE%"
    echo      [OK]  Şablon contacts.json oluşturuldu.
)
echo.
timeout /t 1 /nobreak >nul

:: ============================================================
::  [7/7]  MASAÜSTÜ KISAYOLU
:: ============================================================
echo  ┌──────────────────────────────────────────────────────────────────┐
echo  │  [7/7]  Masaüstü Kısayolu Oluşturuluyor                         │
echo  └──────────────────────────────────────────────────────────────────┘
echo.

set "PYTHONW=%VENV_DIR%\Scripts\pythonw.exe"
set "TARGET_SCRIPT=%PROJ_DIR%\launch_jarvis.pyw"
set "ICON_PATH=%PROJ_DIR%\assets\jarvis_icon.ico"

:: Kısayol oluşturmak için bir geçici VBScript kullan
set "VBS_FILE=%TEMP%\create_jarvis_shortcut.vbs"
set "DESKTOP=%USERPROFILE%\Desktop"

(
    echo Set oShell = CreateObject("WScript.Shell"^)
    echo sDesktop = oShell.SpecialFolders("Desktop"^)
    echo Set oLink = oShell.CreateShortcut(sDesktop ^& "\J.A.R.V.I.S..lnk"^)
    echo oLink.TargetPath = "%PYTHONW%"
    echo oLink.Arguments = """%TARGET_SCRIPT%"""
    echo oLink.WorkingDirectory = "%PROJ_DIR%"
    echo oLink.IconLocation = "%ICON_PATH%"
    echo oLink.Description = "J.A.R.V.I.S. - Just A Rather Very Intelligent System"
    echo oLink.Save
) > "%VBS_FILE%"

cscript //nologo "%VBS_FILE%"
if errorlevel 1 (
    color 0E
    echo      [UYARI]  Masaüstü kısayolu oluşturulamadı.
    echo               J.A.R.V.I.S.'i launch_jarvis.pyw dosyasından
    echo               çalıştırabilirsiniz: %TARGET_SCRIPT%
) else (
    echo      [OK]  Masaüstünde "J.A.R.V.I.S." kısayolu oluşturuldu.
)

:: Geçici VBS dosyasını sil
del "%VBS_FILE%" >nul 2>&1
echo.
timeout /t 1 /nobreak >nul

:: ============================================================
::  KURULUM TAMAMLANDI
:: ============================================================
color 0A
cls
echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║                                                                  ║
echo  ║        ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗                  ║
echo  ║        ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝                  ║
echo  ║        ██║███████║██████╔╝██║   ██║██║███████╗                  ║
echo  ║   ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║                  ║
echo  ║   ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║                  ║
echo  ║    ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝                  ║
echo  ║                                                                  ║
echo  ╠══════════════════════════════════════════════════════════════════╣
echo  ║                                                                  ║
echo  ║   ✓  Python ortamı hazır                                         ║
echo  ║   ✓  Tüm kütüphaneler kuruldu                                    ║
echo  ║   ✓  API Key yapılandırıldı                                      ║
echo  ║   ✓  contacts.json hazır                                         ║
echo  ║   ✓  Masaüstü kısayolu oluşturuldu                               ║
echo  ║                                                                  ║
echo  ╠══════════════════════════════════════════════════════════════════╣
echo  ║                                                                  ║
echo  ║   Kurulum başarıyla tamamlandı!                                  ║
echo  ║   Masaüstündeki J.A.R.V.I.S. ikonuna çift tıklayarak            ║
echo  ║   sistemi başlatabilirsiniz.                                     ║
echo  ║                                                                  ║
echo  ║                    Hoşça kalın, efendim.                        ║
echo  ║                                                                  ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.
echo.
pause
endlocal
exit /b 0
