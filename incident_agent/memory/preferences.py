"""User preference repository (Repository pattern).

`PreferenceRepository` is the interface `MemoryService` (and tests) code
against; `SqlitePreferenceRepository` is the only implementation today,
but the split means swapping storage backends later touches one class,
not every caller.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Protocol

from incident_agent.models.memory import UserPreference


class PreferenceRepository(Protocol):
    def get_preferences(self, session_id: str) -> list[UserPreference]: ...

    def set_preference(self, session_id: str, key: str, value: str) -> None: ...


class SqlitePreferenceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def get_preferences(self, session_id: str) -> list[UserPreference]:
        rows = self._conn.execute(
            "SELECT key, value, learned_at FROM user_preferences WHERE session_id = ? ORDER BY learned_at DESC",
            (session_id,),
        ).fetchall()
        return [UserPreference(key=r["key"], value=r["value"], learned_at=r["learned_at"]) for r in rows]

    def set_preference(self, session_id: str, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO user_preferences (session_id, key, value, learned_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (session_id, key) DO UPDATE SET value = excluded.value, learned_at = excluded.learned_at",
            (session_id, key, value, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
