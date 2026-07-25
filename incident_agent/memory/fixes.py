"""Frequently-used-fix repository (Repository pattern).

Tracks resolution patterns by a stable `fix_id` derived from
`(category, description)` so recording the *same* fix again increments
its usage count instead of creating a duplicate row -- that's what makes
"frequently used" a meaningful signal rather than a list of one-off
resolutions.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Protocol

from incident_agent.models.enums import IncidentCategory
from incident_agent.models.memory import FrequentFix


def _fix_id(category: IncidentCategory, description: str) -> str:
    digest = hashlib.sha256(f"{category.value}:{description.strip().lower()}".encode()).hexdigest()
    return f"FIX-{digest[:12]}"


class FixRepository(Protocol):
    def record_fix_usage(self, category: IncidentCategory, description: str) -> None: ...

    def get_frequent_fixes(self, category: IncidentCategory, k: int = 3) -> list[FrequentFix]: ...


class SqliteFixRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def record_fix_usage(self, category: IncidentCategory, description: str) -> None:
        fix_id = _fix_id(category, description)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO frequent_fixes (fix_id, category, description, usage_count, last_used_at) "
            "VALUES (?, ?, ?, 1, ?) "
            "ON CONFLICT (fix_id) DO UPDATE SET usage_count = usage_count + 1, last_used_at = excluded.last_used_at",
            (fix_id, category.value, description, now),
        )
        self._conn.commit()

    def get_frequent_fixes(self, category: IncidentCategory, k: int = 3) -> list[FrequentFix]:
        rows = self._conn.execute(
            "SELECT fix_id, description, category, usage_count, last_used_at FROM frequent_fixes "
            "WHERE category = ? ORDER BY usage_count DESC, last_used_at DESC LIMIT ?",
            (category.value, k),
        ).fetchall()
        return [
            FrequentFix(
                fix_id=r["fix_id"],
                description=r["description"],
                category=r["category"],
                usage_count=r["usage_count"],
                last_used_at=r["last_used_at"],
            )
            for r in rows
        ]
