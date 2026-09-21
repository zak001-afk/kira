"""
KIRA Task Manager — Timers, Reminders, Notes, and To-Do Lists.

Provides persistent task management using the existing SQLite memory system.
Resource-efficient: tasks are loaded lazily and timers use lightweight threads.
"""

import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "kira_memory.db",
)

# Active timer threads keyed by task_id
_active_timers: Dict[str, threading.Timer] = {}
_timer_lock = threading.Lock()

# Callback registry — UI or backend can register to be notified
_callbacks: List[Callable] = []


def _connect():
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def initialize():
    """Create the tasks table if it does not exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL DEFAULT 'todo',
                title TEXT NOT NULL,
                body TEXT DEFAULT '',
                due_at TEXT DEFAULT '',
                priority INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_type
            ON tasks(type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_completed
            ON tasks(completed)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_due
            ON tasks(due_at)
        """)


def register_callback(callback: Callable):
    """Register a callback that fires when a timer triggers."""
    _callbacks.append(callback)


def _notify(task_id: str, title: str, task_type: str):
    """Notify all registered callbacks about a fired timer/reminder."""
    for cb in _callbacks:
        try:
            cb(task_id, title, task_type)
        except Exception:
            pass


# ─────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────

def add_task(
    title: str,
    task_type: str = "todo",
    body: str = "",
    due_at: str = "",
    priority: int = 0,
) -> str:
    """Add a new task. Returns the task ID."""
    task_id = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat(timespec="seconds")

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, type, title, body, due_at, priority, completed, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (task_id, task_type, title.strip(), body.strip(), due_at.strip(), priority, now, now),
        )

    # If it is a reminder with a due time, schedule a timer
    if task_type == "reminder" and due_at:
        _schedule_timer(task_id, title, due_at)

    return task_id


def list_tasks(
    task_type: Optional[str] = None,
    completed: Optional[bool] = None,
    limit: int = 50,
) -> List[dict]:
    """List tasks with optional filters."""
    conditions = []
    params = []

    if task_type is not None:
        conditions.append("type = ?")
        params.append(task_type)

    if completed is not None:
        conditions.append("completed = ?")
        params.append(1 if completed else 0)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    try:
        with _connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, type, title, body, due_at, priority, completed, created_at, updated_at
                FROM tasks
                {where}
                ORDER BY
                    completed ASC,
                    priority DESC,
                    due_at ASC,
                    created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [
            {
                "id": r[0],
                "type": r[1],
                "title": r[2],
                "body": r[3],
                "due_at": r[4],
                "priority": r[5],
                "completed": bool(r[6]),
                "created_at": r[7],
                "updated_at": r[8],
            }
            for r in rows
        ]
    except sqlite3.Error:
        return []


def complete_task(task_id: str) -> bool:
    """Mark a task as completed."""
    now = datetime.now().isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET completed = 1, updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            return cursor.rowcount > 0
    except sqlite3.Error:
        return False


def delete_task(task_id: str) -> bool:
    """Permanently delete a task."""
    # Cancel any active timer
    _cancel_timer(task_id)

    try:
        with _connect() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0
    except sqlite3.Error:
        return False


def update_task(task_id: str, **kwargs) -> bool:
    """Update task fields."""
    allowed = {"title", "body", "due_at", "priority", "completed"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False

    fields["updated_at"] = datetime.now().isoformat(timespec="seconds")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [task_id]

    try:
        with _connect() as conn:
            cursor = conn.execute(
                f"UPDATE tasks SET {set_clause} WHERE id = ?",
                values,
            )
            return cursor.rowcount > 0
    except sqlite3.Error:
        return False


def get_task(task_id: str) -> Optional[dict]:
    """Get a single task by ID."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT id, type, title, body, due_at, priority, completed, created_at, updated_at
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()

        if row:
            return {
                "id": row[0],
                "type": row[1],
                "title": row[2],
                "body": row[3],
                "due_at": row[4],
                "priority": row[5],
                "completed": bool(row[6]),
                "created_at": row[7],
                "updated_at": row[8],
            }
    except sqlite3.Error:
        pass
    return None


def clear_completed() -> int:
    """Delete all completed tasks. Returns count deleted."""
    try:
        with _connect() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE completed = 1")
            return cursor.rowcount
    except sqlite3.Error:
        return 0


# ─────────────────────────────────────────────
# Timer / Reminder scheduling
# ─────────────────────────────────────────────

def _parse_duration(text: str) -> Optional[int]:
    """Parse human-readable duration into seconds.

    Supports: '5m', '2h', '30s', '1h30m', '90 seconds', '2 hours', etc.
    """
    text = text.strip().lower()

    # "in 5 minutes" style
    m = re.match(
        r"(?:in\s+)?(\d+)\s*(s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?|h(?:ours?|r)?|d(?:ays?)?)",
        text,
    )
    if m:
        val = int(m.group(1))
        unit = m.group(2)[0]
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return val * multipliers.get(unit, 60)

    # "1h30m" compound
    total = 0
    for match in re.finditer(r"(\d+)\s*(h|m|s)", text):
        val = int(match.group(1))
        unit = match.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600}
        total += val * multipliers[unit]

    return total if total > 0 else None


def _schedule_timer(task_id: str, title: str, due_at: str):
    """Schedule a timer thread for a reminder."""
    seconds = _parse_duration(due_at)
    if seconds is None:
        return

    # Cap at 24 hours for safety
    seconds = min(seconds, 86400)

    timer = threading.Timer(seconds, _timer_fired, args=(task_id, title))
    timer.daemon = True

    with _timer_lock:
        # Cancel any existing timer for this task
        old = _active_timers.pop(task_id, None)
        if old:
            old.cancel()
        _active_timers[task_id] = timer

    timer.start()


def _timer_fired(task_id: str, title: str):
    """Called when a timer expires."""
    with _timer_lock:
        _active_timers.pop(task_id, None)

    _notify(task_id, title, "reminder")

    # Auto-complete the task
    complete_task(task_id)


def _cancel_timer(task_id: str):
    """Cancel an active timer for a task."""
    with _timer_lock:
        timer = _active_timers.pop(task_id, None)
        if timer:
            timer.cancel()


def get_active_timers() -> List[str]:
    """Return IDs of tasks with active timers."""
    with _timer_lock:
        return list(_active_timers.keys())


# ─────────────────────────────────────────────
# Natural language parsing helpers
# ─────────────────────────────────────────────

def parse_reminder_command(text: str) -> Optional[dict]:
    """Parse natural language reminder commands.

    Examples:
        'remind me to call mom in 5 minutes'
        'set a timer for 30 minutes'
        'remind me about the meeting in 2 hours'
    """
    text = text.strip()
    lower = text.lower()

    # "remind me to X in Y"
    m = re.match(
        r"(?:remind\s+me\s+(?:to|about|that)\s+)(.+?)\s+in\s+(.+)",
        lower,
    )
    if m:
        return {"title": m.group(1).strip(), "due_at": m.group(2).strip()}

    # "set a timer for X"
    m = re.match(r"(?:set\s+(?:a\s+)?timer\s+for\s+)(.+)", lower)
    if m:
        return {"title": f"Timer: {m.group(1).strip()}", "due_at": m.group(1).strip()}

    # "alarm in X"
    m = re.match(r"(?:alarm\s+in\s+)(.+)", lower)
    if m:
        return {"title": f"Alarm", "due_at": m.group(1).strip()}

    return None


def parse_todo_command(text: str) -> Optional[str]:
    """Parse natural language todo commands.

    Examples:
        'add todo buy groceries'
        'add note check email'
        'remember to call dentist'
    """
    lower = text.strip().lower()

    for prefix in [
        "add todo ", "add to-do ", "add to do ",
        "add note ", "add a note ",
        "add task ", "new task ", "new todo ",
    ]:
        if lower.startswith(prefix):
            return text[len(prefix):].strip()

    return None


# ─────────────────────────────────────────────
# Startup: restore pending reminders
# ─────────────────────────────────────────────

def restore_timers():
    """On startup, re-schedule any pending reminders that haven't fired yet."""
    pending = list_tasks(task_type="reminder", completed=False, limit=100)
    for task in pending:
        if task["due_at"]:
            _schedule_timer(task["id"], task["title"], task["due_at"])


# Initialize on import
initialize()
