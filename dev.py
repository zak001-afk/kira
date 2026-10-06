import os
import sys
import time
import subprocess
from pathlib import Path

import single_instance

ROOT = Path(__file__).resolve().parent
APP = ROOT / "main_window.py"

# Files/folders that should trigger an automatic restart.
WATCH_EXTENSIONS = {
    ".py", ".json", ".png", ".jpg", ".jpeg", ".ico", ".webp",
    ".html", ".css", ".js", ".mjs", ".svg", ".woff2",
}

# Ignore generated/cache files.
IGNORED_DIRS = {
    "__pycache__",
    ".git",
    ".cache",
    "node_modules",
    ".venv",
    "venv",
    "build",
    "dist",
}

POLL_INTERVAL = 0.8

# A child that dies less than this many seconds after start is a crash-loop
# candidate, not a user close; three in a row stop the watcher.
FAST_EXIT_SECONDS = 10.0
MAX_CONSECUTIVE_FAST_EXITS = 3


def snapshot():
    """Return modification times for project files that matter to the app."""
    state = {}

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue

        if any(part in IGNORED_DIRS for part in path.parts):
            continue

        if path.suffix.lower() not in WATCH_EXTENSIONS:
            continue

        try:
            state[str(path.relative_to(ROOT))] = path.stat().st_mtime_ns
        except OSError:
            pass

    return state


def start_app():
    print("\n[KIRA DEV] Starting KIRA...")
    return subprocess.Popen(
        [sys.executable, str(APP)],
        cwd=str(ROOT),
    )


def stop_app(process):
    if process is None or process.poll() is not None:
        return

    print("[KIRA DEV] Stopping KIRA...")
    try:
        if os.name == "nt":
            # Sur Windows 3.14, le python.exe du venv est un tremplin qui
            # lance le vrai interprete en enfant : tuer seulement le
            # processus racine orphelinerait la fenetre KIRA (verrou plus
            # tenu par personne, ports occupes). /T tue l'arbre entier.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
            process.wait()
        except Exception:
            pass


def main():
    auto_restart = "--auto-restart" in sys.argv[1:]

    if not APP.exists():
        print(f"[KIRA DEV] ERROR: {APP} was not found.")
        input("Press Enter to close...")
        return

    holder = single_instance.is_running()
    if holder is not None:
        print(f"[KIRA DEV] ERROR: KIRA is already running (process {holder}).")
        print("           Close it first, then relaunch dev mode.")
        input("Press Enter to close...")
        return

    print("=" * 60)
    print("                 KIRA DEV MODE")
    print("=" * 60)
    print(f"Project: {ROOT}")
    print(f"App:     {APP}")
    print()
    print("Edit and save your Python/UI files.")
    print("KIRA will automatically restart when a relevant file changes.")
    print("Closing the KIRA window stops dev mode"
          + (" (auto-restart is on)." if auto_restart else "."))
    print("Press Ctrl+C here to stop development mode.")
    print("=" * 60)

    previous = snapshot()
    process = start_app()
    started = time.monotonic()
    consecutive_fast_exits = 0

    try:
        while True:
            time.sleep(POLL_INTERVAL)

            current = snapshot()

            if current != previous:
                changed = sorted(
                    set(previous) ^ set(current)
                    | {
                        key for key in set(previous) & set(current)
                        if previous[key] != current[key]
                    }
                )

                print("\n[KIRA DEV] Change detected:")
                for item in changed[:20]:
                    print(f"  - {item}")
                if len(changed) > 20:
                    print(f"  ... and {len(changed) - 20} more")

                stop_app(process)
                previous = current
                process = start_app()
                started = time.monotonic()
                consecutive_fast_exits = 0

            # A closed window now stays closed: silently relaunching KIRA
            # used to stack a second instance on top of the first one.
            if process.poll() is not None:
                exit_code = process.returncode
                runtime = time.monotonic() - started

                if exit_code == single_instance.LOCK_REFUSED_EXIT_CODE:
                    print("[KIRA DEV] Another KIRA instance holds the lock."
                          " Dev mode stops.")
                    break

                if runtime < FAST_EXIT_SECONDS:
                    consecutive_fast_exits += 1
                else:
                    consecutive_fast_exits = 0

                if not auto_restart:
                    print("[KIRA DEV] KIRA was closed. Dev mode stops here.")
                    break

                if consecutive_fast_exits >= MAX_CONSECUTIVE_FAST_EXITS:
                    print("[KIRA DEV] KIRA keeps dying right after start."
                          " Giving up; fix the startup error first.")
                    break

                print("[KIRA DEV] KIRA was closed. Restarting...")
                previous = snapshot()
                process = start_app()
                started = time.monotonic()

    except KeyboardInterrupt:
        print("\n[KIRA DEV] Stopping...")
        stop_app(process)
        print("[KIRA DEV] Development mode stopped.")


if __name__ == "__main__":
    main()
