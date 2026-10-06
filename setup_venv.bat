@echo off
title KIRA - Virtual Environment
color 0B

echo.
echo ==========================================
echo     KIRA VIRTUAL ENVIRONMENT REPAIR
echo ==========================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    echo Install Python or add it to PATH.
    pause
    exit /b 1
)

python scripts\setup_venv.py %*
set SETUP_RESULT=%errorlevel%

echo.
if not "%SETUP_RESULT%"=="0" (
    echo SETUP FAILED - see the messages above.
    pause
    exit /b %SETUP_RESULT%
)

echo You can now start KIRA with:
echo     .venv\Scripts\python.exe main_window.py
echo.
pause
