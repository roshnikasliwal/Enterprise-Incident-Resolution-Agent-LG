"""Kubernetes Tool (mock) -- stands in for a real `kubectl`/K8s API client.

Four independently-callable LangChain tools rather than one do-everything
tool, matching how an LLM tool-calling loop actually works best: the
model chooses `k8s_get_pod_status` when it needs status and
`k8s_get_pod_logs` when it needs logs, instead of parsing a combined
mega-payload every time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from incident_agent.models.enums import LogSeverity
from incident_agent.models.tool_results import LogEntry
from incident_agent.tools._mock_utils import deterministic_rng, pick_scenario
from incident_agent.tools.base import run_structured

_SCENARIOS = ("oom_killed", "probe_failure", "image_pull_backoff", "healthy")

_SCENARIO_LOG_LINES: dict[str, list[tuple[LogSeverity, str]]] = {
    "oom_killed": [
        (LogSeverity.INFO, "Starting application server on port 8080"),
        (LogSeverity.WARNING, "Heap usage at 85% of container memory limit"),
        (LogSeverity.WARNING, "Heap usage at 96% of container memory limit"),
        (LogSeverity.ERROR, "java.lang.OutOfMemoryError: Java heap space"),
    ],
    "probe_failure": [
        (LogSeverity.INFO, "Starting application server on port 8080"),
        (LogSeverity.INFO, "Waiting for downstream dependency 'config-service' to become ready"),
        (LogSeverity.WARNING, "Readiness probe failed: connection refused on :8080/healthz"),
        (LogSeverity.WARNING, "Readiness probe failed: connection refused on :8080/healthz"),
    ],
    "image_pull_backoff": [
        (LogSeverity.ERROR, "Failed to pull image: manifest not found for tag"),
    ],
    "healthy": [
        (LogSeverity.INFO, "Starting application server on port 8080"),
        (LogSeverity.INFO, "Readiness probe succeeded"),
        (LogSeverity.INFO, "Handled 1,204 requests in the last minute, p99 latency 42ms"),
    ],
}


def _pod_status_payload(namespace: str, pod_name: str) -> dict:
    scenario = pick_scenario(pod_name, _SCENARIOS)
    rng = deterministic_rng(pod_name)
    if scenario == "healthy":
        return {
            "namespace": namespace,
            "pod_name": pod_name,
            "phase": "Running",
            "ready": True,
            "restart_count": 0,
            "reason": None,
        }
    if scenario == "oom_killed":
        return {
            "namespace": namespace,
            "pod_name": pod_name,
            "phase": "CrashLoopBackOff",
            "ready": False,
            "restart_count": rng.randint(4, 22),
            "reason": "OOMKilled",
            "last_state_message": "Container exceeded its 512Mi memory limit",
        }
    if scenario == "probe_failure":
        return {
            "namespace": namespace,
            "pod_name": pod_name,
            "phase": "CrashLoopBackOff",
            "ready": False,
            "restart_count": rng.randint(2, 9),
            "reason": "ReadinessProbeFailed",
            "last_state_message": "Readiness probe failed 3 consecutive times",
        }
    return {
        "namespace": namespace,
        "pod_name": pod_name,
        "phase": "Pending",
        "ready": False,
        "restart_count": 0,
        "reason": "ImagePullBackOff",
        "last_state_message": "Back-off pulling image; manifest not found for the requested tag",
    }


def _pod_logs_payload(namespace: str, pod_name: str, tail_lines: int) -> dict:
    scenario = pick_scenario(pod_name, _SCENARIOS)
    lines = _SCENARIO_LOG_LINES[scenario]
    now = datetime.now(timezone.utc)
    entries = [
        LogEntry(
            timestamp=now - timedelta(seconds=(len(lines) - i) * 5),
            source=pod_name,
            severity=severity,
            message=message,
            labels={"namespace": namespace},
        )
        for i, (severity, message) in enumerate(lines)
    ][-tail_lines:]
    return {"namespace": namespace, "pod_name": pod_name, "entries": [e.model_dump(mode="json") for e in entries]}


def _recent_events_payload(namespace: str, pod_name: str) -> dict:
    status = _pod_status_payload(namespace, pod_name)
    events: list[dict] = [
        {"type": "Normal", "reason": "Scheduled", "message": f"Successfully assigned {namespace}/{pod_name} to node"}
    ]
    if status["reason"]:
        events.append(
            {
                "type": "Warning",
                "reason": status["reason"],
                "message": status.get("last_state_message", status["reason"]),
                "count": status["restart_count"] or 1,
            }
        )
    return {"namespace": namespace, "pod_name": pod_name, "events": events}


def _describe_deployment_payload(namespace: str, deployment_name: str) -> dict:
    rng = deterministic_rng(deployment_name)
    desired = rng.choice([2, 3, 4, 5])
    scenario = pick_scenario(deployment_name, _SCENARIOS)
    available = 0 if scenario in ("oom_killed", "probe_failure") else desired
    return {
        "namespace": namespace,
        "deployment_name": deployment_name,
        "desired_replicas": desired,
        "available_replicas": available,
        "updated_replicas": desired,
        "conditions": [
            {
                "type": "Available",
                "status": "True" if available == desired else "False",
            }
        ],
    }


@tool
def k8s_get_pod_status(namespace: str, pod_name: str) -> str:
    """Get the current status (phase, ready, restart count, reason) of a
    Kubernetes pod."""
    return run_structured("k8s_get_pod_status", lambda: _pod_status_payload(namespace, pod_name))


@tool
def k8s_get_pod_logs(namespace: str, pod_name: str, tail_lines: int = 50) -> str:
    """Get the most recent log lines emitted by a Kubernetes pod's container."""
    return run_structured("k8s_get_pod_logs", lambda: _pod_logs_payload(namespace, pod_name, tail_lines))


@tool
def k8s_get_recent_events(namespace: str, pod_name: str) -> str:
    """Get recent Kubernetes events (`kubectl get events`) associated with a pod."""
    return run_structured("k8s_get_recent_events", lambda: _recent_events_payload(namespace, pod_name))


@tool
def k8s_describe_deployment(namespace: str, deployment_name: str) -> str:
    """Describe a Kubernetes Deployment's replica status (desired/available/updated)."""
    return run_structured(
        "k8s_describe_deployment", lambda: _describe_deployment_payload(namespace, deployment_name)
    )
