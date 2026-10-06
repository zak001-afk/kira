@echo off
REM ============================================================================
REM KIRA - Kokoro TTS setup (one-time, requires internet)
REM
REM Installs the local voice engine used by KIRA's speech system:
REM   1. A Python 3.13 side-venv at .kokoro-venv (the main .venv is 3.14 and
REM      the Kokoro ONNX runtime is built for <= 3.13)
REM   2. The kokoro-onnx package (CPU, no torch needed)
REM   3. The Kokoro v1.0 model + voices (~354 MB, downloaded ONCE)
REM
REM After this, the voice works 100% OFFLINE: KIRA starts the server
REM (scripts/kokoro_server.py, http://127.0.0.1:7860) by itself.
REM ============================================================================
setlocal
cd /d "%~dp0.."

echo.
echo === KIRA voice engine setup (Kokoro, local and free) ===
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] The Python launcher "py" was not found.
    echo         Install Python 3.13 from python.org, then run this script again.
    pause
    exit /b 1
)

py -3.13 --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.13 is not installed. Kokoro needs it (the main KIRA
    echo         venv uses 3.14, which the Kokoro ONNX runtime does not support).
    echo         Install Python 3.13 from python.org and re-run this script.
    pause
    exit /b 1
)

if not exist ".kokoro-venv\Scripts\python.exe" (
    echo [1/3] Creating the Python 3.13 side-venv: .kokoro-venv ...
    py -3.13 -m venv .kokoro-venv
    if errorlevel 1 goto :failed
) else (
    echo [1/3] .kokoro-venv already exists - reusing it.
)

echo [2/3] Installing kokoro-onnx + soundfile into the side-venv ...
".kokoro-venv\Scripts\python.exe" -m pip install --upgrade pip
".kokoro-venv\Scripts\python.exe" -m pip install kokoro-onnx soundfile
if errorlevel 1 goto :failed

if exist "models\kokoro\kokoro-v1.0.onnx" if exist "models\kokoro\voices-v1.0.bin" (
    echo [3/3] Model files already downloaded - skipping.
    goto :check
)

echo [3/3] Downloading the Kokoro v1.0 model (~354 MB, one time only) ...
if not exist "models\kokoro" mkdir "models\kokoro"
".kokoro-venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, 'scripts'); import kokoro_server as s; import pathlib; ok1 = s.download_once(pathlib.Path('models/kokoro/kokoro-v1.0.onnx'), s.MODEL_URL); ok2 = s.download_once(pathlib.Path('models/kokoro/voices-v1.0.bin'), s.VOICES_URL); sys.exit(0 if ok1 and ok2 else 1)"
if errorlevel 1 goto :failed

:check
echo.
echo === Setup complete. Testing a short synthesis (bf_emma) ... ===
".kokoro-venv\Scripts\python.exe" -c "import json, urllib.request; body = json.dumps({'text': 'KIRA voice installed. All systems are online.', 'voice': 'bf_emma'}).encode(); request = urllib.request.Request('http://127.0.0.1:7860/tts', data=body, headers={'Content-Type': 'application/json'}); urllib.request.urlopen(request, timeout=300).read(); print('Kokoro answered on port 7860 (a KIRA server is already running).')" 2>nul
if errorlevel 1 (
    echo      No server running yet - KIRA will start one automatically on next launch.
)
echo.
echo Done. Launch KIRA normally: the voice layer starts with the app.
echo Config: the KIRA_TTS_* variables in the .env file (see .env.example).
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] Setup failed. Check the messages above, then re-run this script.
pause
exit /b 1
