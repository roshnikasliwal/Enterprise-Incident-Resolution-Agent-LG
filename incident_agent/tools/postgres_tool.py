"""Postgres Tool (mock) -- higher-level "health check" style monitoring API,
as opposed to `tools/sql_query.py` which runs arbitrary SELECTs.

Where real seed data exists in the shared mock database (`services.
mock_database`) for a given `service_name` (currently `checkout-api` and
`payments-worker`), this tool reads it -- so the SQL Agent and this tool
can corroborate each other on the same underlying facts. For any other
service name it falls back to deterministic synthetic data so the tool
still works generically.
"""

from __future__ import annotations

from langchain_core.tools import tool

from incident_agent.services.mock_database import get_connection
from incident_agent.tools.base import run_structured
from incident_agent.utils.mock_data import deterministic_rng, pick_scenario


def _connection_pool_payload(service_name: str) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT recorded_at, pool_size, active_connections, waiting_requests "
        "FROM connection_pool_stats WHERE service_name = ? ORDER BY recorded_at DESC LIMIT 5",
        (service_name,),
    ).fetchall()
    if rows:
        latest = rows[0]
        return {
            "service_name": service_name,
            "source": "observed",
            "pool_size": latest["pool_size"],
            "active_connections": latest["active_connections"],
            "waiting_requests": latest["waiting_requests"],
            "utilization_percent": round(100 * latest["active_connections"] / latest["pool_size"], 1),
            "recent_history": [dict(row) for row in rows],
        }
    rng = deterministic_rng(service_name)
    pool_size = rng.choice([10, 20, 30])
    scenario = pick_scenario(service_name, ("healthy", "saturated"))
    active = pool_size if scenario == "saturated" else rng.randint(1, pool_size // 2)
    return {
        "service_name": service_name,
        "source": "synthetic",
        "pool_size": pool_size,
        "active_connections": active,
        "waiting_requests": rng.randint(20, 80) if scenario == "saturated" else 0,
        "utilization_percent": round(100 * active / pool_size, 1),
        "recent_history": [],
    }


def _slow_queries_payload(limit: int) -> dict:
    conn = get_connection()
    rows = conn.execute(
        "SELECT query_text, mean_exec_time_ms, calls, last_seen FROM slow_queries "
        "ORDER BY mean_exec_time_ms DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"queries": [dict(row) for row in rows]}


def _replication_status_payload(replica_name: str) -> dict:
    scenario = pick_scenario(replica_name, ("in_sync", "lagging"))
    rng = deterministic_rng(replica_name)
    lag_seconds = rng.uniform(0.0, 0.5) if scenario == "in_sync" else rng.uniform(30.0, 600.0)
    return {
        "replica_name": replica_name,
        "status": scenario,
        "replication_lag_seconds": round(lag_seconds, 2),
    }


@tool
def postgres_get_connection_pool_stats(service_name: str) -> str:
    """Get a service's current PostgreSQL connection pool utilization
    (pool size, active connections, requests waiting for a connection)."""
    return run_structured("postgres_get_connection_pool_stats", lambda: _connection_pool_payload(service_name))


@tool
def postgres_get_slow_queries(limit: int = 5) -> str:
    """Get the slowest queries by mean execution time (analogous to
    pg_stat_statements), most expensive first."""
    return run_structured("postgres_get_slow_queries", lambda: _slow_queries_payload(limit))


@tool
def postgres_get_replication_status(replica_name: str = "replica-1") -> str:
    """Get a read replica's replication lag and sync status."""
    return run_structured("postgres_get_replication_status", lambda: _replication_status_payload(replica_name))
