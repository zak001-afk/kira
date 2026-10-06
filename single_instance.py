"""Un seul KIRA à la fois — verrou d'instance multiplateforme.

Historique : l'icône du bureau lançait le mode dev, dont le watcher
relançait la fenêtre à chaque fermeture. Résultat observé sur la machine :
deux ``dev.py`` et deux ``main_window.py`` simultanés, qui se disputaient
les ports 8765/8766 (l'API parti sur 8767, l'UI répondait 503…).

Chaque point d'entrée (``main_window.py``, ``dev.py``) prend ce verrou
avant de faire quoi que ce soit :

- ``acquire()`` crée un fichier de verrou exclusif contenant le PID du
  détenteur et renvoie ``None`` — ou un message lisible si un KIRA vivant
  le tient déjà ;
- ``is_running()`` renvoie le PID du détenteur vivant, sinon ``None`` ;
- un verrou périmé (crash, PID recyclé) est détecté via la vivacité du PID
  et nettoyé au lancement suivant : un crash ne peut jamais bloquer
  définitivement le lancement d'après.

Le serveur API garde sa propre garde fine par port
(``tests/test_api_single_instance.py``) ; ce module protège l'application
entière, watcher compris. Limite assumée : un PID recyclé vers un process
vivant non-KIRA donnerait un faux « déjà lancé » — rare, et contournable
avec ``--force`` ou en supprimant ``kira.lock``.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOCK_FILENAME = "kira.lock"

# Code de sortie utilisé par main_window.py quand le verrou est refusé ;
# dev.py le reconnaît pour arrêter proprement au lieu de relancer en boucle.
LOCK_REFUSED_EXIT_CODE = 3


def _lock_path() -> Path:
    """Emplacement du verrou : racine du dépôt, ou %APPDATA%\\KIRA en figé."""
    if getattr(sys, "frozen", False):
        # En exécutable PyInstaller, __file__ vit dans _MEIPASS (temporaire) :
        # le verrou doit survivre ailleurs que dans un dossier jetable.
        base = Path(os.environ.get("APPDATA") or Path.home()) / "KIRA"
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = Path.home()
        return base / LOCK_FILENAME
    return Path(__file__).resolve().parent / LOCK_FILENAME


def _pid_is_alive(pid: int) -> bool:
    """True si un processus vivant porte ce PID (best effort, cross-OS)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        SYNCHRONIZE = 0x00100000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            exit_code = ctypes.c_ulong()
            try:
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return True  # lisible en partie : prudence, on dit vivant
            finally:
                kernel32.CloseHandle(handle)
        if ctypes.get_last_error() == ERROR_ACCESS_DENIED:
            return True  # existe mais protégé : prudence, on dit vivant
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True  # impossible de trancher : prudence, on dit vivant
    return True


def is_running():
    """PID du KIRA vivant qui tient le verrou, sinon ``None``.

    Nettoie au passage un verrou laissé par un processus mort.
    """
    path = _lock_path()
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        pid = int(raw.split()[0]) if raw else 0
    except (OSError, ValueError, IndexError):
        return None  # absent ou illisible : rien de vérifiable ne tourne
    if _pid_is_alive(pid):
        return pid
    try:
        path.unlink()
    except OSError:
        pass
    return None


def acquire(force: bool = False):
    """Prend le verrou d'instance unique.

    Renvoie ``None`` en cas de succès, sinon un message lisible expliquant
    quel KIRA vivant le retient. ``force=True`` écrase un verrou existant
    (deuxième copie de développement volontaire).
    """
    path = _lock_path()
    if force:
        try:
            path.unlink()
        except OSError:
            pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder = is_running()
        if holder == os.getpid():
            return None  # déjà à nous : acquire est réentrant (idempotent)
        if holder is not None:
            return (
                f"KIRA is already running (process {holder}). "
                f"Close it first, or launch with --force to override "
                f"(lock file: {path})."
            )
        # Verrou périmé (crash, PID recyclé) : on l'écrase.
        try:
            fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
        except OSError as error:
            return f"KIRA lock file {path} is not writable: {error}"
    except OSError as error:
        return f"KIRA lock file {path} is not writable: {error}"
    with os.fdopen(fd, "w", encoding="utf-8") as lock:
        lock.write(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
    return None


def release() -> None:
    """Retire le verrou si ce processus en est le propriétaire (best effort).

    Appelé dans un ``finally`` par les lanceurs. Si le process est tué
    brutalement, ``is_running()`` auto-réparera au lancement suivant.
    """
    path = _lock_path()
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        owner = int(raw.split()[0]) if raw else 0
    except (OSError, ValueError, IndexError):
        return
    if owner == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    _holder = is_running()
    if _holder is None:
        print("No KIRA instance is running (no live lock).")
        raise SystemExit(0)
    print(f"KIRA is running (process {_holder}).")
    raise SystemExit(LOCK_REFUSED_EXIT_CODE)
