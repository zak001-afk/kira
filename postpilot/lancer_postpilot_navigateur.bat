@echo off
REM ============================================================
REM  PostPilot - mode navigateur (ouvre l'interface dans Chrome)
REM ============================================================
cd /d E:\postpilot
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
) else (
    python run.py
)
pause
