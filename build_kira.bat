@echo off
title KIRA - Build
color 0B

echo.
echo ==========================================
echo              KIRA AI ASSISTANT
echo ==========================================
echo.

cd /d "%~dp0"

echo [1/4] Checking Python...
python --version
if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo.
echo [2/4] Installing PyInstaller...
python -m pip install --upgrade pyinstaller

echo.
echo [3/4] Building KIRA...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

python -m PyInstaller --noconfirm --clean --windowed ^
 --name "KIRA" ^
 --paths "src" ^
 --icon "assets\kira_app.ico" ^
 --add-data "kira_config.json;." ^
 --add-data "assets;assets" ^
 --add-data "ui;ui" ^
 --collect-all customtkinter ^
 --collect-all PIL ^
 main_window.py

if errorlevel 1 (
    echo.
    echo ==========================================
    echo BUILD FAILED
    echo ==========================================
    pause
    exit /b 1
)

echo.
echo [4/4] Copying KIRA to Desktop...

set "DESKTOP=%USERPROFILE%\Desktop"
set "KIRA_DESKTOP=%DESKTOP%\KIRA"

rmdir /s /q "%KIRA_DESKTOP%" 2>nul
mkdir "%KIRA_DESKTOP%"

xcopy /E /I /Y "dist\KIRA\*" "%KIRA_DESKTOP%\" >nul

echo.
echo Creating Desktop shortcut...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\KIRA.lnk'); $Shortcut.TargetPath = '%DESKTOP%\KIRA\KIRA.exe'; $Shortcut.WorkingDirectory = '%DESKTOP%\KIRA'; $Shortcut.IconLocation = '%DESKTOP%\KIRA\KIRA.exe,0'; $Shortcut.Description = 'KIRA AI Assistant'; $Shortcut.Save()"

echo.
echo ==========================================
echo          KIRA BUILD SUCCESSFUL
echo ==========================================
echo.
echo KIRA has been installed here:
echo %KIRA_DESKTOP%
echo.
echo Desktop shortcut created:
echo %DESKTOP%\KIRA.lnk
echo.
echo ==========================================
echo.

pause