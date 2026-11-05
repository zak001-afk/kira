"""Tests du stockage, de la tâche et du planificateur (sans navigateur)."""
from __future__ import annotations

import time

from postpilot import agent, config, store
from postpilot.scheduler import Scheduler


def setup_function():
    config.ensure_dirs()


def test_create_task_from_command_ok():
    res = agent.create_task_from_command(
        "Publie ce post toutes les 1 heure sur mon compte Facebook",
        {"content": "Hello monde"})
    assert res["ok"] is True, res.get("message")
    task = res["task"]
    assert task["platform"] == "facebook"
    assert task["interval_seconds"] == 3600
    assert task["enabled"] is True
    assert "1 heure" in task["summary"]
    # nettoyage
    store.remove_task(task["id"])


def test_create_task_missing_content():
    res = agent.create_task_from_command("publie sur facebook toutes les 1 heure")
    assert res["ok"] is False
    assert "contenu" in res["message"]


def test_create_task_missing_interval():
    res = agent.create_task_from_command("publie sur facebook stp",
                                         {"content": "yo"})
    assert res["ok"] is False
    assert "fréquence" in res["message"]


def test_account_roundtrip():
    store.upsert_account("facebook", "https://www.facebook.com/moi", label="Moi")
    assert store.account_for("facebook") is None        # pas encore connecté
    store.set_account_status("facebook", "connected")
    acc = store.account_for("facebook")
    assert acc and acc["profile_url"] == "https://www.facebook.com/moi"
    store.remove_account("facebook")
    assert store.account_for("facebook") is None


def test_scheduler_runs_task():
    calls = []

    def runner(task):
        calls.append(task["id"])
        return {"ok": True, "message": "ok"}

    task = store.add_task({
        "platform": "facebook", "kind": "post", "target": "profile",
        "content": "test", "interval_seconds": 1, "summary": "test auto",
    })
    s = Scheduler(runner)
    s.start()
    try:
        # attendre jusqu'à 2 exécutions (tick 1 s + première échéance)
        deadline = time.time() + 6
        while time.time() < deadline and len(calls) < 1:
            time.sleep(0.2)
    finally:
        s.stop()
    assert calls, "la tâche ne s'est jamais exécutée"
    fresh = next(t for t in store.tasks() if t["id"] == task["id"])
    assert fresh["runs"] >= 1
    store.remove_task(task["id"])


def test_journal_written():
    store.log("test journal", source="test")
    entries = store.journal(5)
    assert entries and entries[-1]["message"] == "test journal"
