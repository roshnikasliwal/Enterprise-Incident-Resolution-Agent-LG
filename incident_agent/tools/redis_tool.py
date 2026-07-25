"""Redis Tool (mock) -- stands in for `redis-cli INFO` / a Redis monitoring API."""

from __future__ import annotations

from langchain_core.tools import tool

from incident_agent.tools._mock_utils import deterministic_rng, pick_scenario
from incident_agent.tools.base import run_structured

_MEMORY_SCENARIOS = ("healthy", "near_maxmemory", "over_maxmemory")


def _memory_stats_payload(instance: str) -> dict:
    scenario = pick_scenario(instance, _MEMORY_SCENARIOS)
    rng = deterministic_rng(instance)
    maxmemory_mb = rng.choice([512, 1024, 2048])
    if scenario == "healthy":
        used_mb = round(maxmemory_mb * rng.uniform(0.2, 0.5), 1)
    elif scenario == "near_maxmemory":
        used_mb = round(maxmemory_mb * rng.uniform(0.85, 0.97), 1)
    else:
        used_mb = round(maxmemory_mb * rng.uniform(1.0, 1.02), 1)
    return {
        "instance": instance,
        "maxmemory_mb": maxmemory_mb,
        "used_memory_mb": used_mb,
        "utilization_percent": round(100 * used_mb / maxmemory_mb, 1),
        "maxmemory_policy": "noeviction" if scenario != "healthy" else "allkeys-lru",
    }


def _connection_status_payload(instance: str) -> dict:
    scenario = pick_scenario(instance, ("healthy", "near_maxclients", "refusing_connections"))
    rng = deterministic_rng(instance)
    maxclients = 10_000
    if scenario == "healthy":
        connected = rng.randint(50, 500)
    elif scenario == "near_maxclients":
        connected = rng.randint(9_000, 9_900)
    else:
        connected = maxclients
    return {
        "instance": instance,
        "connected_clients": connected,
        "maxclients": maxclients,
        "status": "refusing_connections" if connected >= maxclients else "accepting_connections",
        "blocked_clients": rng.randint(0, 5) if scenario != "healthy" else 0,
    }


def _eviction_stats_payload(instance: str) -> dict:
    scenario = pick_scenario(instance, _MEMORY_SCENARIOS)
    rng = deterministic_rng(instance)
    evicted_keys_per_min = 0 if scenario == "healthy" else rng.randint(500, 50_000)
    return {
        "instance": instance,
        "evicted_keys_per_min": evicted_keys_per_min,
        "expired_keys_per_min": rng.randint(0, 300),
        "keyspace_misses_ratio": round(rng.uniform(0.01, 0.05) if scenario == "healthy" else rng.uniform(0.3, 0.8), 2),
    }


@tool
def redis_get_memory_stats(instance: str) -> str:
    """Get a Redis instance's memory usage vs. its configured maxmemory,
    plus its eviction policy."""
    return run_structured("redis_get_memory_stats", lambda: _memory_stats_payload(instance))


@tool
def redis_get_connection_status(instance: str) -> str:
    """Get a Redis instance's current connected-client count vs. maxclients,
    and whether it is currently refusing new connections."""
    return run_structured("redis_get_connection_status", lambda: _connection_status_payload(instance))


@tool
def redis_get_eviction_stats(instance: str) -> str:
    """Get a Redis instance's key eviction/expiry rate and cache miss ratio."""
    return run_structured("redis_get_eviction_stats", lambda: _eviction_stats_payload(instance))
