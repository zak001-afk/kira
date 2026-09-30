"""KIRA checks herself: one harmless probe per specialist agent.

"diagnostic" (or /api/health) runs every agent's cheapest safe tool and
reports green/red per agent plus the model backend — so a degraded local
model under RAM pressure is VISIBLE instead of mysterious.

Probes never change anything: reads, a temp-sandbox write inside the code
workspace, a memory ping. Network probes (weather) are informational.
"""
from datetime import datetime

_TIMEOUT_SECONDS = 12


def _probe_research():
    import kira_info
    city = kira_info.default_city() or "Tunis"
    data = kira_info.get_weather(city)
    return bool(data and data.get("temperature") is not None), f"météo {city}"


def _probe_memory():
    import kira_memory
    rows = kira_memory.search_messages("kira", limit=1)
    return True, "mémoire locale lue"  # empty result is still a healthy DB


def _probe_windows():
    import kira_tasks
    tasks = kira_tasks.list_tasks(completed=False, limit=1)
    return isinstance(tasks, list), f"{len(tasks)} tâche(s) lue(s)"


def _probe_plugins():
    import kira_plugins
    names = kira_plugins.list_plugins()
    return True, f"{len(names)} plugin(s)"


def _probe_programming():
    import kira_code
    result = kira_code.write_file(".health-probe.py", "value = 42\n")
    if not result.get("ok"):
        return False, result.get("error", "écriture refusée")
    kira_code.delete_path(".health-probe.py")
    return True, "écriture + suppression OK"


def _probe_docs():
    import kira_docs
    result = kira_docs.list_documents()
    return bool(result.get("ok")), f"{result.get('count', 0)} document(s)"


def _probe_brain():
    """The chat brain answers one trivial prompt (local or cloud)."""
    try:
        import kira_ai
        reply = kira_ai.chat("Reply with the single word: OK", timeout=_TIMEOUT_SECONDS,
                             options={"temperature": 0, "num_predict": 8}, think=False)
        text = (reply.text or "").strip().upper()
        return bool(reply.ok and "OK" in text[:12]), \
            (reply.text or "").strip()[:40] or "réponse vide"
    except Exception as error:
        return False, str(error)[:80]


PROBES = {
    "research": _probe_research,
    "memory": _probe_memory,
    "windows": _probe_windows,
    "plugins": _probe_plugins,
    "programming": _probe_programming,
    "docs": _probe_docs,
    "brain": _probe_brain,
}

_LABELS = {
    "research": "Recherche", "memory": "Mémoire", "windows": "Tâches",
    "plugins": "Plugins", "programming": "Programmation", "docs": "Documents",
    "brain": "Cerveau IA",
}


def run_health_check(agents=None):
    """{ok, checks: [{agent, label, ok, detail, ms}], response}."""
    checks = []
    for agent, probe in PROBES.items():
        if agents and agent not in agents:
            continue
        started = datetime.now()
        ok, detail = False, "sonde indisponible"
        try:
            ok, detail = probe()
        except Exception as error:
            ok, detail = False, str(error)[:80]
        elapsed = int((datetime.now() - started).total_seconds() * 1000)
        checks.append({"agent": agent, "label": _LABELS.get(agent, agent),
                       "ok": bool(ok), "detail": str(detail)[:120], "ms": elapsed})
    failed = [row["label"] for row in checks if not row["ok"]]
    healthy = len(checks) - len(failed)
    text = (f"Diagnostic : {healthy}/{len(checks)} systèmes OK."
            if not failed else
            f"Diagnostic : {healthy}/{len(checks)} systèmes OK — problème : "
            + ", ".join(failed) + ".")
    return {"ok": not failed, "checks": checks, "response": text}
