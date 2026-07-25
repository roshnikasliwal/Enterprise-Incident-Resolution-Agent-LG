"""Kafka Tool (mock) -- stands in for a real Kafka admin client / JMX metrics."""

from __future__ import annotations

from langchain_core.tools import tool

from incident_agent.tools.base import run_structured
from incident_agent.utils.mock_data import deterministic_rng, pick_scenario

_BROKER_SCENARIOS = ("healthy", "one_broker_down", "disk_full", "controller_unavailable")


def _broker_status_payload(cluster: str) -> dict:
    scenario = pick_scenario(cluster, _BROKER_SCENARIOS)
    rng = deterministic_rng(cluster)
    broker_count = rng.choice([3, 5])
    if scenario == "healthy":
        return {
            "cluster": cluster,
            "broker_count": broker_count,
            "brokers_online": broker_count,
            "under_replicated_partitions": 0,
            "controller_id": 0,
            "status": "healthy",
        }
    if scenario == "one_broker_down":
        return {
            "cluster": cluster,
            "broker_count": broker_count,
            "brokers_online": broker_count - 1,
            "under_replicated_partitions": rng.randint(5, 40),
            "controller_id": 0,
            "status": "degraded",
            "detail": "Broker 2 unreachable; partition leaders re-electing to remaining brokers.",
        }
    if scenario == "disk_full":
        return {
            "cluster": cluster,
            "broker_count": broker_count,
            "brokers_online": broker_count - 1,
            "under_replicated_partitions": rng.randint(10, 60),
            "controller_id": 0,
            "status": "degraded",
            "detail": "Broker 1 log directory at 100% disk utilization; broker refusing writes.",
        }
    return {
        "cluster": cluster,
        "broker_count": broker_count,
        "brokers_online": 0,
        "under_replicated_partitions": broker_count * 10,
        "controller_id": None,
        "status": "outage",
        "detail": "No broker can be elected controller; cluster-wide produce/consume stalled.",
    }


def _consumer_lag_payload(consumer_group: str, topic: str) -> dict:
    rng = deterministic_rng(f"{consumer_group}:{topic}")
    scenario = pick_scenario(f"{consumer_group}:{topic}", ("stable", "growing", "stalled"))
    partitions = rng.choice([6, 12, 24])
    if scenario == "stable":
        lag_per_partition = [rng.randint(0, 200) for _ in range(partitions)]
    elif scenario == "growing":
        lag_per_partition = [rng.randint(5_000, 50_000) for _ in range(partitions)]
    else:
        lag_per_partition = [rng.randint(200_000, 800_000) for _ in range(partitions)]
    return {
        "consumer_group": consumer_group,
        "topic": topic,
        "partition_count": partitions,
        "total_lag": sum(lag_per_partition),
        "max_partition_lag": max(lag_per_partition),
        "trend": {"stable": "stable", "growing": "degrading", "stalled": "degrading"}[scenario],
    }


def _topic_partitions_payload(topic: str) -> dict:
    rng = deterministic_rng(topic)
    partitions = rng.choice([6, 12, 24])
    replication_factor = rng.choice([2, 3])
    return {
        "topic": topic,
        "partition_count": partitions,
        "replication_factor": replication_factor,
        "under_replicated": pick_scenario(topic, (0, 0, 0, replication_factor - 1)),
    }


@tool
def kafka_get_broker_status(cluster: str = "default") -> str:
    """Get the health status of the Kafka broker cluster: broker count online,
    under-replicated partitions, and controller status."""
    return run_structured("kafka_get_broker_status", lambda: _broker_status_payload(cluster))


@tool
def kafka_get_consumer_lag(consumer_group: str, topic: str) -> str:
    """Get per-topic consumer lag for a consumer group, including the trend
    (stable vs. degrading) and the worst single partition's lag."""
    return run_structured("kafka_get_consumer_lag", lambda: _consumer_lag_payload(consumer_group, topic))


@tool
def kafka_get_topic_partitions(topic: str) -> str:
    """Get partition count, replication factor, and under-replicated partition
    count for a Kafka topic."""
    return run_structured("kafka_get_topic_partitions", lambda: _topic_partitions_payload(topic))
