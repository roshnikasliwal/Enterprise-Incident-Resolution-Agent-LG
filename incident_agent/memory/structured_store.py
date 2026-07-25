"""SQLite schema/connection for the structured memory stores (user
preferences, frequently used fixes, conversation summaries).

Distinct from `services/mock_database.py` (which simulates a monitoring
Postgres for the SQL Agent to investigate) and from the LangGraph
checkpointer's own SQLite database (Phase 7, graph execution state) --
this is *this project's own* durable memory about users and past
resolutions, at `settings.memory.database_path`.

Also distinct from Chroma (`memory/episodic.py`): preferences/fixes/
conversation summaries are looked up by exact key (user/session id),
not by semantic similarity, so a relational table is the right tool --
using a vector store for everything would mean an unnecessary embedding
call on every read/write of a simple key-value fact.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from incident_agent.config.settings import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_preferences (
    session_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    learned_at TEXT NOT NULL,
    PRIMARY KEY (session_id, key)
);

CREATE TABLE IF NOT EXISTS frequent_fixes (
    fix_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 1,
    last_used_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_frequent_fixes_category ON frequent_fixes (category);

CREATE TABLE IF NOT EXISTS conversations (
    session_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_threads (
    session_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, thread_id)
);
CREATE INDEX IF NOT EXISTS idx_session_threads_session ON session_threads (session_id);
"""


def _initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


@lru_cache(maxsize=1)
def get_connection() -> sqlite3.Connection:
    """Process-wide connection to the memory database, schema created on first use."""
    settings = get_settings()
    settings.ensure_data_directories()
    conn = sqlite3.connect(settings.memory.database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _initialize(conn)
    return conn


def reset_for_tests() -> sqlite3.Connection:
    """A fresh, isolated in-memory database, bypassing the process-wide cache."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _initialize(conn)
    return conn
