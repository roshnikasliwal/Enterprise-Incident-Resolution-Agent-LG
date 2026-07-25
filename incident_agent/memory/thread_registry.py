"""Thread registry (Repository pattern) -- the session-to-checkpoint-thread
index backing "multiple users" support.

LangGraph's checkpointer (see `services/checkpointer.py`) partitions
persisted state purely by `thread_id`; it has no concept of "which user
owns this thread." Multi-user support therefore has to live at the
application level -- this repository is that: every graph run registers
its `(session_id, thread_id, incident_id)` here (see
`nodes/recall_memory_node.py`), so `GET /history?session_id=...`
(Phase 9) can answer "what has this session/user investigated" without
scanning the entire checkpoint database.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Protocol

from incident_agent.models.memory import ThreadRecord


class ThreadRegistry(Protocol):
    def register(self, session_id: str, thread_id: str, incident_id: str) -> None: ...

    def list_for_session(self, session_id: str) -> list[ThreadRecord]: ...


class SqliteThreadRegistry:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def register(self, session_id: str, thread_id: str, incident_id: str) -> None:
        self._conn.execute(
            "INSERT INTO session_threads (session_id, thread_id, incident_id, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (session_id, thread_id) DO NOTHING",
            (session_id, thread_id, incident_id, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def list_for_session(self, session_id: str) -> list[ThreadRecord]:
        rows = self._conn.execute(
            "SELECT session_id, thread_id, incident_id, created_at FROM session_threads "
            "WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ).fetchall()
        return [
            ThreadRecord(
                session_id=r["session_id"],
                thread_id=r["thread_id"],
                incident_id=r["incident_id"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
