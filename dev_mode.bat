@echo off
setlocal
title KIRA - Development Mode (auto-reload)
cd /d "%~dp0"

echo.
echo ==========================================
echo          KIRA DEVELOPMENT MODE
echo ==========================================
echo.

rem Prefer the project's own virtual environment so every dependency resolves.
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" goto :run

echo [WARN] .venv\Scripts\python.exe was not found - falling back to PATH python.
echo        Run setup_venv.bat to create or repair the virtual environment.
set "PY=python"

:run
echo [1/2] Checking Python...
"%PY%" --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: No usable Python interpreter was found.
    echo Run setup_venv.bat, then try again.
    pause
    exit /b 1
)

echo [2/2] Launching KIRA in auto-reload mode...
echo        Edit and save any code file: KIRA restarts itself.
echo        Closing the KIRA window now stops dev mode.
echo.

"%PY%" -u dev.py
set "RC=%ERRORLEVEL%"

echo.
echo KIRA DEV MODE CLOSED. (exit code %RC%)
pause
exit /b %RC%
