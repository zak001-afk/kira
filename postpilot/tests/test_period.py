"""Début / fin des tâches et fréquence 1 minute → 24 heures (sans navigateur)."""
from __future__ import annotations

import datetime as dt

from postpilot import agent, config, store
from postpilot.scheduler import (Scheduler, next_run_label, parse_when,
                             period_ended, seconds_until_start)


def setup_function():
    config.ensure_dirs()
    store.save_tasks([])
    store.save_links([])


def _create(extra: dict) -> dict:
    base = {"content": "salut"}
    base.update(extra)
    return agent.create_task_from_command(
        "Publie ce post toutes les 1 heure sur Facebook", base)


def _future(hours: float = 1) -> str:
    return (dt.datetime.now() + dt.timedelta(hours=hours)) \
        .isoformat(timespec="seconds")


def _past(minutes: float = 5) -> str:
    return (dt.datetime.now() - dt.timedelta(minutes=minutes)) \
        .isoformat(timespec="seconds")


# ── Période début / fin ─────────────────────────────────────────────────────
def test_task_period_stored():
    res = _create({"start_at": "2026-10-10T14:00",
                   "end_at": "2026-10-12T18:00"})
    assert res["ok"] is True, res.get("message")
    assert res["task"]["start_at"] == "2026-10-10T14:00:00"
    assert res["task"]["end_at"] == "2026-10-12T18:00:00"
    store.remove_task(res["task"]["id"])


def test_task_end_before_start_rejected():
    res = _create({"start_at": "2026-10-12T18:00",
                   "end_at": "2026-10-10T14:00"})
    assert res["ok"] is False
    assert "APRÈS le début" in res["message"]
    assert store.tasks() == []


def test_task_unreadable_date_rejected():
    res = _create({"start_at": "n'importe quoi"})
    assert res["ok"] is False
    assert "illisible" in res["message"]


def test_task_without_period_ok():
    res = _create({})
    assert res["ok"] is True, res.get("message")
    assert res["task"]["start_at"] is None
    assert res["task"]["end_at"] is None
    store.remove_task(res["task"]["id"])


# ── Fréquence : minutes, plafonné à 24 h ────────────────────────────────────
def test_frequency_in_minutes_up_to_24h():
    for minutes, expected in ((1, 60), (180, 10800), (720, 43200),
                              (1440, 86400)):
        res = _create({"interval_seconds": minutes * 60})
        assert res["ok"] is True, res.get("message")
        assert res["task"]["interval_seconds"] == expected
        store.remove_task(res["task"]["id"])


def test_frequency_over_24h_rejected():
    res = _create({"interval_seconds": 90000})
    assert res["ok"] is False
    assert "24 heures" in res["message"]


def test_frequency_under_1_minute_rejected():
    res = _create({"interval_seconds": 30})
    assert res["ok"] is False
    assert "1 minute" in res["message"]


# ── Planificateur : démarre au début, s'arrête à la fin ─────────────────────
def _add_task(**fields) -> dict:
    base = {"platform": "facebook", "kind": "post", "target": "profile",
            "content": "x", "interval_seconds": 60, "summary": "test période"}
    base.update(fields)
    return store.add_task(base)


def test_parse_when_handles_datetime_local():
    assert parse_when("2026-10-10T14:00") is not None
    assert parse_when("2026-10-10T14:00:00") is not None
    assert parse_when("") is None
    assert parse_when("bidule") is None


def test_scheduler_waits_for_start():
    calls = []
    s = Scheduler(lambda t: (calls.append(t), {"ok": True, "message": "ok"})[1])
    task = _add_task(start_at=_future(1))
    s._tick()
    assert calls == [], "la tâche s'est exécutée avant sa date de début"
    assert s.due_in(task["id"]) > 3500            # ≈ 1 h avant la 1re exécution
    assert seconds_until_start(task) > 3500
    assert next_run_label(s, task).startswith("à partir du")
    store.remove_task(task["id"])


def test_scheduler_stops_at_end():
    task = _add_task(end_at=_past(5))
    s = Scheduler(lambda t: {"ok": True, "message": "ok"})
    s._tick()
    fresh = next(t for t in store.tasks() if t["id"] == task["id"])
    assert fresh["enabled"] is False, "la tâche aurait dû se mettre en pause"
    assert period_ended(task) is True
    assert any("Fin de période" in e["message"] for e in store.journal(20))
    assert next_run_label(s, fresh) == "en pause"
    store.remove_task(task["id"])


def test_scheduler_runs_normally_between_start_and_end():
    """Début déjà passé, fin lointaine : la tâche reste armée."""
    task = _add_task(start_at=_past(5), end_at=_future(24))
    s = Scheduler(lambda t: {"ok": True, "message": "ok"})
    s._tick()
    fresh = next(t for t in store.tasks() if t["id"] == task["id"])
    assert fresh["enabled"] is True
    assert s.due_in(task["id"]) <= 60             # échéance dans ~1 minute
    store.remove_task(task["id"])
