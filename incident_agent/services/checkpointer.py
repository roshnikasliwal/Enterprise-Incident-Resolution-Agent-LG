"""Checkpointer factory -- the Strategy/Factory that decides *how* LangGraph
persists graph execution state, independent of the graph topology itself.

`graphs/main_graph.build_incident_graph()` defaults to an in-memory
checkpointer so it stays safe to build in tests without touching disk;
this module is what production callers (the FastAPI app, Phase 9) use
instead: `build_incident_graph(checkpointer=get_checkpointer())` swaps in
durable SQLite-backed persistence with no change to the graph itself --
this is "Checkpoint Memory" from requirements.md, and it's exactly the
kind of infrastructure decision that should be a one-line call-site
change, not a topology change.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from langgraph.checkpoint.sqlite import SqliteSaver

from incident_agent.config.settings import get_settings


def build_checkpointer(database_path: str) -> SqliteSaver:
    """Construct a `SqliteSaver` against an explicit path -- the DI-friendly
    entry point tests use to point at a `tmp_path` file instead of the real
    project database."""
    connection = sqlite3.connect(database_path, check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    return saver


@lru_cache(maxsize=1)
def get_checkpointer() -> SqliteSaver:
    """Process-wide singleton backed by `settings.checkpoint.database_path`."""
    settings = get_settings()
    settings.ensure_data_directories()
    return build_checkpointer(settings.checkpoint.database_path)


def list_thread_ids(checkpointer: SqliteSaver) -> list[str]:
    """All distinct thread IDs with at least one checkpoint -- the SQLite
    checkpointer has no built-in "list all threads" API (`.list()` expects
    a config to filter by), so this queries its underlying table directly.
    Used by `GET /history` (Phase 9) and multi-thread/multi-user tests.
    """
    cursor = checkpointer.conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")
    return [row[0] for row in cursor.fetchall()]
