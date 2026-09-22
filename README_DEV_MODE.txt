KIRA DEVELOPMENT MODE
=====================

1. Copy these files into your KIRA project folder:

   C:\KIRA\
      dev.py
      dev_mode.bat

2. Double-click:

   dev_mode.bat

3. KIRA will start normally.

4. Edit and save:
   - main_window.py
   - kira_voice_agent.py
   - kira_config.json
   - files inside assets\

5. When you save a relevant file, Dev Mode automatically:
   - detects the change
   - closes the running KIRA process
   - starts KIRA again

You do NOT need to rebuild the EXE while developing.

When the UI is finished, use your PyInstaller build process to create
the final KIRA.exe.

Press Ctrl+C in the Dev Mode terminal to stop it.
