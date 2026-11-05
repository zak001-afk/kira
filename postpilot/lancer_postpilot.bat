@echo off
REM ============================================================
REM  PostPilot - lancement en mode fenetre (sans console)
REM  Double-cliquez sur ce fichier.
REM ============================================================
cd /d E:\postpilot
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" launch_desktop.py
) else (
    start "" pythonw launch_desktop.py
)
