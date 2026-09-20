import os
import sys
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "main_window.py"

# Files/folders that should trigger an automatic restart.
WATCH_EXTENSIONS = {".py", ".json", ".png", ".jpg", ".jpeg", ".ico"}

# Ignore generated/cache files.
IGNORED_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
}

POLL_INTERVAL = 0.8


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

    print("[KIRA DEV] Restarting KIRA...")
    try:
        process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except Exception:
        pass


def main():
    if not APP.exists():
        print(f"[KIRA DEV] ERROR: {APP} was not found.")
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
    print("Press Ctrl+C here to stop development mode.")
    print("=" * 60)

    previous = snapshot()
    process = start_app()

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

            # If KIRA was closed manually, restart it automatically.
            if process.poll() is not None:
                print("[KIRA DEV] KIRA was closed. Restarting...")
                previous = snapshot()
                process = start_app()

    except KeyboardInterrupt:
        print("\n[KIRA DEV] Stopping...")
        stop_app(process)
        print("[KIRA DEV] Development mode stopped.")


if __name__ == "__main__":
    main()
