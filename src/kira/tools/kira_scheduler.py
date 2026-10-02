"""KIRA becomes proactive: reminders fire by themselves.

Until now KIRA only answered when spoken to. A background thread in the API
server process polls the tasks store every 20 seconds; reminders that reach
their due time are pushed to every connected interface through ``/api/events``
(long-poll, up to 25 s) so the HUD shows and speaks the alert the moment it
happens. Fired events are kept in a small deque so the UI can also fetch
recent ones on load (GET /api/events?recent=1).

Also here: the morning briefing (weather + tasks + holidays, localized) used
by the "briefing" command route and the ``KIRA_BRIEFING=1`` boot option.
"""
from collections import deque
from datetime import datetime, timedelta
import os
import threading
import time

_LOCK = threading.Lock()
_EVENTS = deque(maxlen=50)
_FIRED = set()          # task ids already announced
_LAST_EVENT_ID = 0
_EVENT_COUNTER = 0
_POLL_SECONDS = 20
_STOP = threading.Event()
_THREAD = None


def _now():
    return datetime.now()


def _parse_due(due_at, now=None):
    """datetime from the stored formats ('HH:MM' or ISO), else None."""
    value = str(due_at or "").strip()
    if not value:
        return None
    now = now or _now()
    for fmt in ("%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%H:%M":
                # '14:30' means TODAY at 14:30 (the `now` reference passed by
                # the caller, so tests can simulate a clock). A time already
                # passed (KIRA was off, or the poller was busy) still fires —
                # late beats never for a proactive assistant.
                return now.replace(hour=parsed.hour, minute=parsed.minute,
                                   second=0, microsecond=0)
            return parsed
        except ValueError:
            continue
    return None


def scan_due_tasks(tasks=None, now=None):
    """[event, ...] for reminders whose time has come (and not yet fired)."""
    global _EVENT_COUNTER
    now = now or _now()
    if tasks is None:
        try:
            import kira_tasks
            tasks = kira_tasks.list_tasks(completed=False, limit=200)
        except Exception:
            return []
    events = []
    with _LOCK:
        for task in tasks:
            if str(task.get("type")) != "reminder" or task.get("id") in _FIRED:
                continue
            due = _parse_due(task.get("due_at"), now)
            if due is None:
                continue
            if due <= now:
                _FIRED.add(task["id"])
                _EVENT_COUNTER += 1
                event = {"id": _EVENT_COUNTER, "kind": "reminder",
                         "task_id": task.get("id"), "title": task.get("title", ""),
                         "due_at": task.get("due_at", ""),
                         "speak": True, "time": now.isoformat(timespec="seconds")}
                _EVENTS.append(event)
                events.append(event)
    return events


def pending_events(after_id=0):
    """Events newer than after_id (for long-poll and recent fetch)."""
    with _LOCK:
        return [dict(event) for event in _EVENTS if event["id"] > int(after_id or 0)]


def wait_for_events(after_id, timeout=25.0):
    """Block up to timeout waiting for events newer than after_id."""
    deadline = time.monotonic() + max(0.5, min(float(timeout or 25.0), 30.0))
    while time.monotonic() < deadline:
        events = pending_events(after_id)
        if events:
            return events
        if _STOP.wait(0.5):
            return []
    return pending_events(after_id)


def _poll_loop():
    while not _STOP.wait(_POLL_SECONDS):
        try:
            scan_due_tasks()
        except Exception:
            pass


def start_polling():
    """Start the background reminder poller (idempotent)."""
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return _THREAD
    _STOP.clear()
    _THREAD = threading.Thread(target=_poll_loop, name="kira-scheduler", daemon=True)
    _THREAD.start()
    return _THREAD


def stop_polling():
    _STOP.set()


def _reset_state():
    """Test hygiene only."""
    global _EVENT_COUNTER
    with _LOCK:
        _EVENTS.clear()
        _FIRED.clear()
        _EVENT_COUNTER = 0


# ── Morning briefing ─────────────────────────────────────────────────────────

def briefing(language="fr"):
    """(text, data) localized morning briefing: weather, tasks, holidays."""
    language = str(language or "fr").strip().lower()[:2]
    sections = []
    data = {}
    try:
        import kira_info
        city = kira_info.default_city()
        weather = kira_info.get_weather(city) if city else None
        if weather:
            data["weather"] = weather
            sections.append(
                f"Météo à {weather.get('city', city)} : {weather.get('condition', {}).get('fr', '')}, "
                f"{weather.get('temperature', '?')}°C (ressenti {weather.get('feels_like', '?')}°C), "
                f"pluie {weather.get('rain_chance_today', 0)}%."
                if language == "fr" else
                f"Weather in {weather.get('city', city)}: {weather.get('condition', {}).get('en', '')}, "
                f"{weather.get('temperature', '?')}°C (feels like {weather.get('feels_like', '?')}°C), "
                f"rain {weather.get('rain_chance_today', 0)}%.")
    except Exception:
        pass
    try:
        import kira_tasks
        tasks = kira_tasks.list_tasks(completed=False, limit=5)
        data["tasks"] = tasks
        if tasks:
            listed = "\n".join(f"- {task.get('title', '')}" for task in tasks)
            sections.append(f"Tâches en attente :\n{listed}" if language == "fr"
                            else f"Pending tasks:\n{listed}")
        else:
            sections.append("Aucune tâche en attente." if language == "fr"
                            else "No pending tasks.")
    except Exception:
        pass
    try:
        import kira_info
        holidays = kira_info.get_holidays("TN" if language == "fr" else "US")
        upcoming = list((holidays or {}).get("upcoming") or [])[:2]
        # Same date + name can appear twice from the upstream API (e.g.
        # Columbus Day / Columbus Day) — dedupe while keeping order.
        seen = set()
        unique = []
        for row in upcoming:
            key = (str(row.get("date") or ""), str(row.get("name") or ""))
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        upcoming = unique
        if upcoming:
            names = ", ".join(str(row.get("local_name") or row.get("name") or "") for row in upcoming)
            sections.append(f"Prochains jours fériés : {names}." if language == "fr"
                            else f"Upcoming holidays: {names}.")
    except Exception:
        pass
    try:
        import kira_info
        quote = kira_info.daily_quote()
        data["quote"] = quote
        sections.append(f"Citation du jour : « {quote.get('quote', '')} » — {quote.get('author', '')}"
                        if language == "fr"
                        else f"Quote of the day: “{quote.get('quote', '')}” — {quote.get('author', '')}")
    except Exception:
        pass  # never block the briefing on a decorative quote
    header = "Bonjour ! Voici votre point du matin." if language == "fr" \
        else "Good morning! Here is your briefing."
    return "\n\n".join([header] + sections), data
