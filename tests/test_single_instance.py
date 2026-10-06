"""Un seul KIRA : sémantique du verrou d'instance unique.

Régression 2026-10-04 : l'icône du bureau pointait sur le mode dev, dont le
watcher ressuscitait la fenêtre à chaque fermeture — deux ``dev.py`` et deux
``main_window.py`` tournaient en même temps et se disputaient les ports
8765/8766. Tous les lanceurs passent désormais par
``single_instance.acquire()`` ; ces tests épinglent le verrou sur tous les
OS où tourne la CI (Windows local, ubuntu-latest).
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import single_instance  # noqa: E402  (bootstrap du chemin, convention tests)


def _spawn_live_foreign_process():
    """Un processus vivant qui n'est pas le nôtre (pour simuler un KIRA)."""
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not single_instance._pid_is_alive(child.pid):
        time.sleep(0.05)
    return child


class PidLivenessTests(unittest.TestCase):
    def test_own_pid_is_alive(self):
        self.assertTrue(single_instance._pid_is_alive(os.getpid()))

    def test_impossible_pid_is_not_alive(self):
        # 2**31 - 1 dépasse tout intervalle de PID réaliste (pid_max Linux
        # plafonne à 2**22, les PID Windows restent bien en dessous de
        # 2**24), donc ce PID ne peut jamais être un processus vivant.
        self.assertFalse(single_instance._pid_is_alive(2**31 - 1))

    def test_non_positive_pid_is_not_alive(self):
        self.assertFalse(single_instance._pid_is_alive(0))
        self.assertFalse(single_instance._pid_is_alive(-1))


class LockLifecycleTests(unittest.TestCase):
    def setUp(self):
        # Les tests vivent dans un verrou isolé : toucher le vrai
        # kira.lock volerait le verrou d'un KIRA lancé à côté
        # (acquire(force=True) l'écraserait, release() le supprimerait).
        tmp = tempfile.mkdtemp(prefix="kira-lock-tests-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        patcher = mock.patch.object(
            single_instance,
            "_lock_path",
            lambda: Path(tmp) / single_instance.LOCK_FILENAME,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # Ne jamais hériter d'un verrou laissé par un run précédent.
        self.assertIsNone(single_instance.acquire(force=True))
        self.addCleanup(single_instance.release)

    def test_acquire_is_idempotent_for_the_same_process(self):
        self.assertIsNone(single_instance.acquire())
        self.assertIsNone(single_instance.acquire())  # déjà à nous : OK
        self.assertEqual(single_instance.is_running(), os.getpid())

    def test_foreign_live_lock_is_refused(self):
        child = _spawn_live_foreign_process()
        self.addCleanup(self._stop_child, child)
        path = single_instance._lock_path()
        path.write_text(f"{child.pid}\n", encoding="utf-8")
        refused = single_instance.acquire()
        self.assertIsInstance(refused, str)
        self.assertIn(str(child.pid), refused)
        self.assertIn("--force", refused)
        self.assertEqual(single_instance.is_running(), child.pid)

    def test_force_overrides_a_foreign_live_lock(self):
        child = _spawn_live_foreign_process()
        self.addCleanup(self._stop_child, child)
        path = single_instance._lock_path()
        path.write_text(f"{child.pid}\n", encoding="utf-8")
        self.assertIsNone(single_instance.acquire(force=True))
        self.assertEqual(single_instance.is_running(), os.getpid())

    @staticmethod
    def _stop_child(child):
        if child.poll() is None:
            if os.name == "nt":
                child.kill()
            else:
                child.send_signal(signal.SIGKILL)
        child.wait(timeout=10)

    def test_release_clears_the_lock(self):
        self.assertIsNone(single_instance.acquire())
        single_instance.release()
        self.assertIsNone(single_instance.is_running())

    def test_release_never_touches_another_owner_lock(self):
        self.assertIsNone(single_instance.acquire())
        path = single_instance._lock_path()
        path.write_text("2147483647 2026-10-04T00:00:00+00:00\n", encoding="utf-8")
        self.addCleanup(single_instance.release)
        single_instance.release()  # PID étranger : le fichier doit rester
        self.assertTrue(path.exists())

    def test_stale_lock_from_dead_pid_is_ignored_and_cleaned(self):
        path = single_instance._lock_path()
        path.write_text("2147483647\n", encoding="utf-8")
        self.assertIsNone(single_instance.is_running())
        self.assertFalse(path.exists())

    def test_empty_or_garbage_lock_holds_nothing(self):
        path = single_instance._lock_path()
        path.write_text("", encoding="utf-8")
        self.assertIsNone(single_instance.is_running())
        path.write_text("not-a-pid\n", encoding="utf-8")
        self.assertIsNone(single_instance.is_running())
        # acquire() doit malgré tout reprendre la main sur un tel fichier.
        self.assertIsNone(single_instance.acquire())
        self.assertEqual(single_instance.is_running(), os.getpid())


if __name__ == "__main__":
    unittest.main()
