import os
import re
import sqlite3
import uuid
import threading
from datetime import datetime

# Import caching
try:
    from kira_cache import memory_cache
    CACHE_ENABLED = True
except ImportError:
    CACHE_ENABLED = False

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "kira_memory.db",
)

# Thread-local storage for connection pooling
_connection_local = threading.local()


def _connect():
    """Get thread-local database connection with optimizations."""
    if not hasattr(_connection_local, "connection"):
        connection = sqlite3.connect(
            DB_PATH,
            timeout=5,
            check_same_thread=False,
        )
        
        # Performance optimizations
        connection.execute("PRAGMA journal_mode=WAL")           # Write-Ahead Logging
        connection.execute("PRAGMA synchronous=NORMAL")         # Balance safety/speed
        connection.execute("PRAGMA temp_store=MEMORY")          # Temp tables in RAM
        connection.execute("PRAGMA cache_size=-64000")          # 64MB cache (was 2MB)
        connection.execute("PRAGMA mmap_size=268435456")        # 256MB memory-mapped I/O
        connection.execute("PRAGMA page_size=4096")             # Optimal page size
        
        _connection_local.connection = connection
    
    return _connection_local.connection


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
        connection = _connect()
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
        
        # Invalidate cache for this memory
        if CACHE_ENABLED:
            cache_key = f"memory:{category}:{key}"
            memory_cache.set(cache_key, value)  # Update cache with new value

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
    # Check cache first
    if CACHE_ENABLED:
        cache_key = f"memory:{category}:{key}"
        cached_value = memory_cache.get(cache_key)
        if cached_value is not None:
            return cached_value
    
    try:
        connection = _connect()
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
            value = row[0]
            # Cache the result
            if CACHE_ENABLED:
                memory_cache.set(cache_key, value)
            return value

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


def prune_old_conversations(keep_days=30):
    """Delete conversations older than the given number of days."""
    try:
        cutoff = (
            datetime.now()
            - __import__("datetime").timedelta(days=keep_days)
        ).isoformat(timespec="seconds")

        with _connect() as conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE created_at < ?",
                (cutoff,),
            )
            return cursor.rowcount
    except (sqlite3.Error, Exception):
        return 0


def conversation_count():
    """Return the total number of stored conversation messages."""
    try:
        with _connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
            return row[0] if row else 0
    except sqlite3.Error:
        return 0


def build_memory_context(category=None, limit=20):
    """Build a text summary of stored memories for chat context injection."""
    memories = load_memories(category=category)
    if not memories:
        return ""

    lines = ["KIRA MEMORY CONTEXT:"]
    for mem in memories[:limit]:
        lines.append(f"- [{mem['category']}] {mem['key']}: {mem['value']}")
    return "\n".join(lines)


initialize()