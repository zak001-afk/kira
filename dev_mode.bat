@echo off
title KIRA - Development Mode
cd /d "%~dp0"

echo.
echo ==========================================
echo          KIRA DEVELOPMENT MODE
echo ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    echo Install Python or add it to PATH.
    pause
    exit /b 1
)

python dev.py

echo.
echo KIRA DEV MODE CLOSED.
pause
