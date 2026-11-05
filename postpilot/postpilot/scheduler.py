"""Planificateur : exécute les tâches programmées en boucle (bloc indépendant).

Une thread dédiée vérifie chaque seconde les tâches « enabled » dont le
prochain passage est atteint, puis lance la publication via le moteur
(navigateur visible) de la plateforme.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
import traceback

from . import store


class Scheduler:
    def __init__(self, runner) -> None:
        """runner(task) -> dict résultat {ok, message}"""
        self._runner = runner
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_due: dict[str, float] = {}
        self.busy: dict[str, bool] = {}

    # ── cycle de vie ───────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="socia-scheduler")
        self._thread.start()
        store.log("Programmateur démarré — les tâches vont s'exécuter seules.",
                  source="programmation")

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── boucle ─────────────────────────────────────────────────────────
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:                       # jamais de crash silencieux
                store.log("Erreur interne du programmateur :\n"
                          + traceback.format_exc(limit=3),
                          level="error", source="programmation")
            self._stop.wait(1.0)

    def _tick(self) -> None:
        now = time.monotonic()
        for task in store.tasks():
            tid = task.get("id")
            if not tid or not task.get("enabled"):
                continue
            # ── date de fin atteinte : la tâche s'arrête d'elle-même ──
            if period_ended(task):
                store.update_task(tid, enabled=False)
                self._next_due.pop(tid, None)
                store.log(f"⏹ Fin de période — « "
                          f"{(task.get('summary') or '')[:60]} » mise en pause "
                          f"(terminée le {task.get('end_at')}).",
                          source="programmation")
                continue
            interval = int(task.get("interval_seconds") or 0)
            if interval <= 0:
                continue
            due = self._next_due.get(tid)
            if due is None:
                # première exécution : à la prochaine échéance (pas d'emballement)
                self._next_due[tid] = now + interval
                due = self._next_due[tid]
            # ── date de début : rien ne part avant elle ──
            delay = seconds_until_start(task)
            if delay is not None and delay > 0:
                wanted = now + delay            # première exécution = début
                if due < wanted:
                    due = self._next_due[tid] = wanted
            if now < due:
                continue
            if self.busy.get(tid):
                continue
            # décalage de la prochaine échéance AVANT l'exécution
            self._next_due[tid] = now + interval
            self.busy[tid] = True
            threading.Thread(target=self._run_one, args=(task,), daemon=True,
                             name=f"socia-task-{tid}").start()

    def reschedule(self, task_id: str) -> None:
        """Oublie la prochaine échéance mémorisée (ex. après modification
        de la fréquence) — elle sera recalculée au prochain tour."""
        self._next_due.pop(task_id, None)

    def _run_one(self, task: dict) -> None:
        tid = task.get("id")
        store.clear_cancel(tid or "")   # nouveau départ : pas d'arrêt demandé
        summary = task.get("summary") or (task.get("content") or "")[:60]
        store.log(f"▶ Exécution : {summary}", source="programmation")
        try:
            result = self._runner(task) or {"ok": False, "message": "aucun résultat"}
        except Exception as exc:
            result = {"ok": False,
                      "message": f"{exc}"}
            store.log("✖ Échec : " + traceback.format_exc(limit=3),
                      level="error", source="programmation")
        runs = int(task.get("runs") or 0) + 1
        store.update_task(
            tid,
            runs=runs,
            last_run_at=store.now_iso(),
            last_status="ok" if result.get("ok") else f"erreur: {result.get('message')}",
        )
        level = "info" if result.get("ok") else "error"
        store.log(("✔ " if result.get("ok") else "✖ ") + str(result.get("message")),
                  level=level, source="programmation")
        self.busy[tid] = False

    # ── pilotage ───────────────────────────────────────────────────────
    def trigger(self, task: dict) -> None:
        """Exécute une tâche immédiatement (bouton « Lancer maintenant »)."""
        tid = task.get("id")
        if tid and self.busy.get(tid):
            return
        if tid:
            store.clear_cancel(tid)
            self.busy[tid] = True
        threading.Thread(target=self._run_one, args=(task,), daemon=True).start()

    def due_in(self, task_id: str) -> float | None:
        due = self._next_due.get(task_id)
        if due is None:
            return None
        return max(0.0, due - time.monotonic())

    def status(self) -> dict:
        tasks = store.tasks()
        return {
            "running": self.running,
            "tasks": len(tasks),
            "enabled": sum(1 for t in tasks if t.get("enabled")),
            "busy": [tid for tid, b in self.busy.items() if b],
        }


def parse_when(value) -> float | None:
    """'2026-10-10T14:00[:00]' → timestamp, ou None si vide/illisible."""
    raw = (value or "").strip()
    if not raw:
        return None
    if len(raw) == 16:
        raw += ":00"
    try:
        return dt.datetime.fromisoformat(raw).timestamp()
    except (ValueError, TypeError):
        return None


def seconds_until_start(task: dict) -> float | None:
    """Secondes restantes avant la date de début (négatif = déjà commencé)."""
    ts = parse_when(task.get("start_at"))
    if ts is None:
        return None
    return ts - time.time()


def period_ended(task: dict) -> bool:
    ts = parse_when(task.get("end_at"))
    return ts is not None and time.time() >= ts


def next_run_label(scheduler: Scheduler, task: dict) -> str:
    if not task.get("enabled"):
        return "en pause"
    if period_ended(task):
        return "terminée"
    delay = seconds_until_start(task)
    if delay is not None and delay > 0:
        when = dt.datetime.fromtimestamp(parse_when(task.get("start_at")))
        return "à partir du " + when.strftime("%d/%m %H:%M")
    left = scheduler.due_in(task.get("id", ""))
    if left is None:
        return "planifiée"
    secs = int(left)
    if secs < 60:
        return f"dans {secs}s"
    if secs < 3600:
        return f"dans {secs // 60}min"
    return f"dans {secs // 3600}h{(secs % 3600) // 60:02d}m"
