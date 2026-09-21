@echo off
title KIRA — Neural Interface
color 0C

echo.
echo ==========================================
echo        KIRA — NEURAL INTERFACE
echo ==========================================
echo.

cd /d "%~dp0"

echo [1/2] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

echo [2/2] Launching KIRA...
echo.

python launch_web.py

pause
