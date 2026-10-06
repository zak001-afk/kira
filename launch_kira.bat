@echo off
setlocal
title KIRA - Neural Interface
color 0C

echo.
echo ==========================================
echo        KIRA - NEURAL INTERFACE
echo ==========================================
echo.

cd /d "%~dp0"

rem Prefer the project's own virtual environment so every dependency resolves.
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" goto :check

echo [WARN] .venv\Scripts\python.exe was not found - falling back to PATH python.
echo        Run setup_venv.bat to create or repair the virtual environment.
set "PY=python"

:check
echo [1/2] Checking Python...
"%PY%" --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: No usable Python interpreter was found.
    echo Run setup_venv.bat, then try again.
    pause
    exit /b 1
)

echo [2/2] Launching KIRA...
echo.

rem %* forwards --force etc.; main_window.py enforces the single-instance lock.
"%PY%" main_window.py %*

pause
