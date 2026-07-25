"""Conversation memory repository (Repository pattern).

A rolling, capped text summary per session -- not a full transcript
store. Each resolved incident appends one line; once the summary grows
past `_MAX_SUMMARY_CHARS` the oldest lines are dropped. This is a
deliberately simple, deterministic summarizer (string concatenation, not
an LLM call) -- good enough to give the Planner/Root-Cause agents useful
"this user has been dealing with X" context without adding an 18th agent
to a spec that names exactly seventeen.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Protocol

_MAX_SUMMARY_CHARS = 2000


class ConversationRepository(Protocol):
    def get_summary(self, session_id: str) -> str | None: ...

    def append_incident(self, session_id: str, incident_id: str, user_query: str, resolution_summary: str) -> None: ...


class SqliteConversationRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def get_summary(self, session_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT summary FROM conversations WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row["summary"] if row and row["summary"] else None

    def append_incident(self, session_id: str, incident_id: str, user_query: str, resolution_summary: str) -> None:
        existing = self.get_summary(session_id) or ""
        line = f"[{incident_id}] asked: '{user_query[:120]}' -> resolved: '{resolution_summary[:200]}'"
        updated = f"{existing}\n{line}".strip()
        if len(updated) > _MAX_SUMMARY_CHARS:
            updated = updated[-_MAX_SUMMARY_CHARS:]
        self._conn.execute(
            "INSERT INTO conversations (session_id, summary, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (session_id) DO UPDATE SET summary = excluded.summary, updated_at = excluded.updated_at",
            (session_id, updated, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
