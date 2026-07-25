"""A small, seeded SQLite database standing in for a production Postgres
instance.

Backs two tools: `tools/sql_query.py` (arbitrary read-only SELECTs, as an
LLM-driven text-to-SQL agent would run) and `tools/postgres_tool.py`'s
slow-query lookup (a fixed, higher-level "health check" query). Sharing
one seeded database between them means the SQL Agent can genuinely
discover the same slow queries the Postgres mock tool reports --
consistent evidence across tools, not two disconnected fakes.

SQLite (not a real Postgres) is a deliberate, explicit simplification for
this project's "mocked infrastructure" tools -- see the Kubernetes/Kafka/
Redis mock tools for the same pattern applied to non-SQL backends.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from incident_agent.config.settings import PROJECT_ROOT

MOCK_DB_PATH = PROJECT_ROOT / "data" / "sqlite" / "mock_postgres.sqlite"

_SCHEMA_DESCRIPTION = """\
Table deployments(id INTEGER, service_name TEXT, version TEXT, deployed_at TEXT, status TEXT)
  -- one row per deployment event; status is one of 'success', 'failed', 'rolled_back'.
Table connection_pool_stats(id INTEGER, service_name TEXT, recorded_at TEXT, pool_size INTEGER, active_connections INTEGER, waiting_requests INTEGER)
  -- periodic snapshots of each service's DB connection pool utilization.
Table slow_queries(id INTEGER, query_text TEXT, mean_exec_time_ms REAL, calls INTEGER, last_seen TEXT)
  -- aggregated slow-query log, analogous to pg_stat_statements.
Table incident_log(id INTEGER, incident_id TEXT, component TEXT, message TEXT, created_at TEXT)
  -- append-only log of noteworthy events across past incidents.
"""


def get_schema_description() -> str:
    """Human/LLM-readable schema summary -- fed to the SQL Agent's prompt so
    it can write informed queries without a live schema-introspection round trip."""
    return _SCHEMA_DESCRIPTION


def _create_and_seed(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE deployments (
            id INTEGER PRIMARY KEY,
            service_name TEXT NOT NULL,
            version TEXT NOT NULL,
            deployed_at TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE connection_pool_stats (
            id INTEGER PRIMARY KEY,
            service_name TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            pool_size INTEGER NOT NULL,
            active_connections INTEGER NOT NULL,
            waiting_requests INTEGER NOT NULL
        );
        CREATE TABLE slow_queries (
            id INTEGER PRIMARY KEY,
            query_text TEXT NOT NULL,
            mean_exec_time_ms REAL NOT NULL,
            calls INTEGER NOT NULL,
            last_seen TEXT NOT NULL
        );
        CREATE TABLE incident_log (
            id INTEGER PRIMARY KEY,
            incident_id TEXT NOT NULL,
            component TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.executemany(
        "INSERT INTO deployments (service_name, version, deployed_at, status) VALUES (?, ?, ?, ?)",
        [
            ("checkout-api", "v2.14.0", "2026-07-25T08:02:00Z", "success"),
            ("checkout-api", "v2.13.3", "2026-07-18T09:15:00Z", "success"),
            ("payments-worker", "v1.9.1", "2026-07-24T22:41:00Z", "success"),
        ],
    )
    conn.executemany(
        "INSERT INTO connection_pool_stats (service_name, recorded_at, pool_size, active_connections, "
        "waiting_requests) VALUES (?, ?, ?, ?, ?)",
        [
            ("checkout-api", "2026-07-25T08:10:00Z", 20, 20, 47),
            ("checkout-api", "2026-07-25T08:05:00Z", 20, 18, 12),
            ("checkout-api", "2026-07-25T07:55:00Z", 20, 9, 0),
            ("payments-worker", "2026-07-25T08:10:00Z", 10, 4, 0),
        ],
    )
    conn.executemany(
        "INSERT INTO slow_queries (query_text, mean_exec_time_ms, calls, last_seen) VALUES (?, ?, ?, ?)",
        [
            (
                "SELECT * FROM orders WHERE customer_id = $1 ORDER BY created_at DESC",
                842.3,
                1204,
                "2026-07-25T08:09:00Z",
            ),
            (
                "UPDATE inventory SET reserved = reserved + $1 WHERE sku = $2",
                310.7,
                8931,
                "2026-07-25T08:11:00Z",
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO incident_log (incident_id, component, message, created_at) VALUES (?, ?, ?, ?)",
        [
            (
                "INC-20260710-aaaa1111",
                "checkout-api",
                "Connection pool exhausted after v2.13.3 deploy; missing index on orders.customer_id "
                "caused the pool to saturate under normal load.",
                "2026-07-10T14:20:00Z",
            ),
        ],
    )
    conn.commit()


@lru_cache(maxsize=1)
def get_connection() -> sqlite3.Connection:
    """Process-wide connection to the seeded mock database, created on first use."""
    MOCK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not MOCK_DB_PATH.exists()
    conn = sqlite3.connect(str(MOCK_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if is_new:
        _create_and_seed(conn)
    return conn


def reset_for_tests(db_path: Path | None = None) -> sqlite3.Connection:
    """Build a fresh, seeded in-memory (or scratch-file) database, bypassing the
    process-wide cache -- used by tests that need an isolated instance."""
    conn = sqlite3.connect(str(db_path) if db_path else ":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _create_and_seed(conn)
    return conn
