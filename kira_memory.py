import os
import re
import json
import sqlite3
import uuid
from datetime import datetime


DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "kira_memory.db",
)

def _connect():
    connection = sqlite3.connect(
        DB_PATH,
        timeout=5,
    )

    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=NORMAL")

    return connection


def initialize():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(category, memory_key)
            )
            """
        )

        # ── the agent's own mind ──────────────────────────────────────
        # Episodes: what KIRA understood, planned, did, and how it went.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_text TEXT NOT NULL,
                thought TEXT NOT NULL DEFAULT '',
                action_json TEXT NOT NULL,
                source TEXT NOT NULL,
                outcome TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # Learnings: command -> action mappings that worked before.
        # KIRA recalls these instead of asking the model again, and
        # demotes them when they fail (so it stops repeating mistakes).
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_learnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_text TEXT NOT NULL UNIQUE,
                action_json TEXT NOT NULL,
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_episodes_created
            ON agent_episodes(created_at)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_created
            ON conversations(created_at)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_session
            ON conversations(session_id)
            """
        )


def new_session_id():
    return uuid.uuid4().hex


def save_message(session_id, role, content):
    content = str(content or "").strip()

    if not content:
        return

    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations
                (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
    except sqlite3.Error:
        pass


def load_recent_messages(limit=12):
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversations
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        rows.reverse()

        return [
            {
                "role": role,
                "content": content,
            }
            for role, content in rows
        ]

    except sqlite3.Error:
        return []


def search_messages(query, limit=6):
    query = str(query or "").strip()

    if not query:
        return []

    words = [
        word.lower()
        for word in re.findall(r"[A-Za-zÀ-ÿ0-9_]+", query)
        if len(word) >= 3
    ]

    if not words:
        return []

    words = words[:8]

    conditions = " OR ".join(
        ["LOWER(content) LIKE ?" for _ in words]
    )

    parameters = [
        f"%{word}%"
        for word in words
    ]

    try:
        with _connect() as connection:
            rows = connection.execute(
                f"""
                SELECT role, content, created_at
                FROM conversations
                WHERE {conditions}
                ORDER BY id DESC
                LIMIT ?
                """,
                (*parameters, max(1, int(limit))),
            ).fetchall()

        rows.reverse()

        return [
            {
                "role": role,
                "content": content,
                "created_at": created_at,
            }
            for role, content, created_at in rows
        ]

    except sqlite3.Error:
        return []


def save_memory(category, key, value, confidence=1.0):
    category = str(category or "").strip()
    key = str(key or "").strip()
    value = str(value or "").strip()

    if not category or not key or not value:
        return False

    now = datetime.now().isoformat(timespec="seconds")

    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO memories
                (
                    category,
                    memory_key,
                    memory_value,
                    confidence,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)

                ON CONFLICT(category, memory_key)
                DO UPDATE SET
                    memory_value = excluded.memory_value,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
                """,
                (
                    category,
                    key,
                    value,
                    float(confidence),
                    now,
                    now,
                ),
            )

        return True

    except sqlite3.Error:
        return False
def remember_explicit_fact(text):
    """
    Detect simple explicit user facts and store them permanently.
    Only high-confidence statements are stored.
    """

    text = str(text or "").strip()

    if not text:
        return

    patterns = [
        (
            r"my favorite programming language is (.+)",
            "preference",
            "favorite_programming_language",
        ),
        (
            r"my favorite language is (.+)",
            "preference",
            "favorite_programming_language",
        ),
        (
            r"my name is (.+)",
            "identity",
            "name",
        ),
        (
            r"i am (.+)",
            "identity",
            "user_identity",
        ),
        (
            r"i prefer (.+)",
            "preference",
            "general_preference",
        ),
        (
            r"i like (.+)",
            "preference",
            "general_like",
        ),
    ]

    for pattern, category, key in patterns:
        match = re.fullmatch(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            value = match.group(1).strip(" .!?")

            if value:
                save_memory(
                    category=category,
                    key=key,
                    value=value,
                    confidence=1.0,
                )

            return

def load_memories(category=None):
    try:
        with _connect() as connection:

            if category:
                rows = connection.execute(
                    """
                    SELECT category, memory_key, memory_value, confidence
                    FROM memories
                    WHERE category = ?
                    ORDER BY updated_at DESC
                    """,
                    (category,),
                ).fetchall()

            else:
                rows = connection.execute(
                    """
                    SELECT category, memory_key, memory_value, confidence
                    FROM memories
                    ORDER BY updated_at DESC
                    """
                ).fetchall()

        return [
            {
                "category": category,
                "key": key,
                "value": value,
                "confidence": confidence,
            }
            for category, key, value, confidence in rows
        ]

    except sqlite3.Error:
        return []


def get_memory(category, key, default=None):
    try:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT memory_value
                FROM memories
                WHERE category = ?
                AND memory_key = ?
                LIMIT 1
                """,
                (category, key),
            ).fetchone()

        if row:
            return row[0]

    except sqlite3.Error:
        pass

    return default

def forget_memory(category, key) -> bool:
    category = str(category or "").strip()
    key = str(key or "").strip()

    if not category or not key:
        return False

    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM memories
                WHERE category = ?
                AND memory_key = ?
                """,
                (
                    category,
                    key,
                ),
            )

            return cursor.rowcount > 0

    except sqlite3.Error:
        return False
def memory_exists(category, key) -> bool:
    category = str(category or "").strip()
    key = str(key or "").strip()

    if not category or not key:
        return False

    try:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM memories
                WHERE category = ?
                AND memory_key = ?
                LIMIT 1
                """,
                (
                    category,
                    key,
                ),
            ).fetchone()

            return row is not None

    except sqlite3.Error:
        return False
def update_memory(category, key, value, confidence=1.0) -> bool:
    category = str(category or "").strip()
    key = str(key or "").strip()
    value = str(value or "").strip()

    if not category or not key or not value:
        return False

    return save_memory(
        category=category,
        key=key,
        value=value,
        confidence=confidence,
    )


# ── the agent's own mind: episodes & learnings ──────────────────────────────

def normalize_agent_command(text) -> str:
    """Canonical form used to match commands to past learnings."""
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return value.strip(" .!?,;:")


def save_episode(command, thought, action, source, outcome) -> bool:
    if outcome not in {"success", "failed", "unknown"}:
        outcome = "unknown"
    try:
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_episodes
                (command_text, thought, action_json, source, outcome, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalize_agent_command(command) or str(command or ""),
                    str(thought or ""),
                    json.dumps(action or {}, ensure_ascii=False),
                    str(source or "unknown"),
                    outcome,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        return True
    except sqlite3.Error:
        return False


def recent_episodes(limit=10):
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT command_text, thought, action_json, source, outcome, created_at
                FROM agent_episodes
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [
            {
                "command": command,
                "thought": thought,
                "action": json.loads(action_json),
                "source": source,
                "outcome": outcome,
                "created_at": created_at,
            }
            for command, thought, action_json, source, outcome, created_at in rows
        ]
    except sqlite3.Error:
        return []


def learn_from_outcome(command, action, succeeded) -> bool:
    """Upsert a command->action learning; bumps success/failure counters."""
    command_key = normalize_agent_command(command)
    if not command_key or not isinstance(action, dict):
        return False
    now = datetime.now().isoformat(timespec="seconds")
    bumped = "success_count" if succeeded else "failure_count"
    try:
        with _connect() as connection:
            connection.execute(
                f"""
                INSERT INTO agent_learnings
                (command_text, action_json, success_count, failure_count,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(command_text) DO UPDATE SET
                    action_json = excluded.action_json,
                    {bumped} = {bumped} + 1,
                    updated_at = excluded.updated_at
                """,
                (
                    command_key,
                    json.dumps(action, ensure_ascii=False),
                    1 if succeeded else 0,
                    0 if succeeded else 1,
                    now,
                    now,
                ),
            )
        return True
    except sqlite3.Error:
        return False


def recall_action(command):
    """Return a stored action for a command — only while successes dominate.

    Reflexion: the first failure that pulls failures level with successes
    makes the learning ineligible again, so KIRA stops repeating mistakes.
    """
    command_key = normalize_agent_command(command)
    if not command_key:
        return None
    try:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT action_json, success_count, failure_count
                FROM agent_learnings
                WHERE command_text = ?
                LIMIT 1
                """,
                (command_key,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    action_json, success_count, failure_count = row
    if success_count < 1 or success_count <= failure_count:
        return None
    try:
        action = json.loads(action_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(action, dict):
        return None
    return {
        "action": action,
        "success_count": success_count,
        "failure_count": failure_count,
    }


def find_similar_learnings(command, limit=5):
    """Candidate learnings sharing content words with the command (fuzzy recall)."""
    words = {
        w for w in re.findall(r"[\w\u0600-\u06FF]{4,}", str(command or "").lower())
    }
    if not words:
        return []
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT command_text, action_json, success_count, failure_count
                FROM agent_learnings
                """
            ).fetchall()
    except sqlite3.Error:
        return []

    scored = []
    for command_text, action_json, success_count, failure_count in rows:
        if success_count < 1 or success_count <= failure_count:
            continue
        stored_words = set(
            re.findall(r"[\w\u0600-\u06FF]{4,}", command_text.lower())
        )
        if not stored_words:
            continue
        overlap = len(words & stored_words)
        # both directions must mostly agree — guards against one shared word
        score = overlap / max(1, min(len(words), len(stored_words)))
        if score >= 0.75 and overlap:
            scored.append((score, command_text, action_json))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, command_text, action_json in scored[: max(1, int(limit))]:
        try:
            results.append({"command": command_text, "action": json.loads(action_json)})
        except json.JSONDecodeError:
            continue
    return results


def top_learnings(limit=5):
    try:
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT command_text, action_json, success_count, failure_count
                FROM agent_learnings
                ORDER BY success_count DESC, updated_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
    except sqlite3.Error:
        return []
    results = []
    for command_text, action_json, success_count, failure_count in rows:
        try:
            action = json.loads(action_json)
        except json.JSONDecodeError:
            continue
        results.append(
            {
                "command": command_text,
                "action": action,
                "success_count": success_count,
                "failure_count": failure_count,
            }
        )
    return results


def clear_learnings() -> int:
    try:
        with _connect() as connection:
            cursor = connection.execute("DELETE FROM agent_learnings")
            return cursor.rowcount
    except sqlite3.Error:
        return 0


def clear_episodes() -> int:
    try:
        with _connect() as connection:
            cursor = connection.execute("DELETE FROM agent_episodes")
            return cursor.rowcount
    except sqlite3.Error:
        return 0


initialize()