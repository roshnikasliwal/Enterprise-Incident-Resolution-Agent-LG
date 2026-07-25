"""Metrics Analysis node -- one branch of the parallel evidence-gathering
subgraph. Combines a time-series pull (`metrics_collector`) with a
category-appropriate infrastructure snapshot tool, since a single metric
series rarely tells the whole story on its own.

This is the one evidence node where the Tool Selection Agent is actually
consulted (the other five have no interchangeable tool choice to make --
e.g. log analysis always wants pod logs + events, and the SQL Agent's job
of choosing the *query* already subsumes tool selection). Here there's a
genuine, bounded decision -- "is the category snapshot tool worth calling
in addition to the metric time series for this task?" -- over a small,
known candidate set, which is exactly what `ToolSelectionDecision` is
shaped for. We don't generalize this into a fully dynamic dispatch-by-name
engine: the two candidate tools this node knows how to invoke are still
called directly, only *whether* to call the snapshot one is LLM-decided.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.metrics_analysis import MetricsAnalysisAgent
from incident_agent.agents.tool_selection import ToolSelectionAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.enums import IncidentCategory
from incident_agent.models.execution import ReasoningStep
from incident_agent.models.tool_results import MetricSample, ToolResult
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_metrics
from incident_agent.nodes.node_runner import run_node
from incident_agent.nodes.target_inference import infer_target_name
from incident_agent.nodes.tool_invocation import invoke_tool, tool_succeeded
from incident_agent.tools.kafka_tool import kafka_get_broker_status
from incident_agent.tools.kubernetes_tool import k8s_get_pod_status
from incident_agent.tools.metrics_collector import metrics_collector
from incident_agent.tools.postgres_tool import postgres_get_connection_pool_stats
from incident_agent.tools.redis_tool import redis_get_memory_stats

_SNAPSHOT_TOOL_NAME_BY_CATEGORY: dict[IncidentCategory, str] = {
    IncidentCategory.KUBERNETES: k8s_get_pod_status.name,
    IncidentCategory.KAFKA: kafka_get_broker_status.name,
    IncidentCategory.DATABASE: postgres_get_connection_pool_stats.name,
    IncidentCategory.CACHE: redis_get_memory_stats.name,
}

_METRIC_BY_CATEGORY: dict[IncidentCategory, tuple[str, str]] = {
    IncidentCategory.KUBERNETES: ("kubernetes", "memory_usage_percent"),
    IncidentCategory.KAFKA: ("kafka", "consumer_lag"),
    IncidentCategory.DATABASE: ("database", "connection_pool_utilization_percent"),
    IncidentCategory.CACHE: ("cache", "eviction_rate_per_min"),
    IncidentCategory.APPLICATION: ("application", "http_5xx_rate_percent"),
}


def _snapshot_tool_result(category: IncidentCategory, target: str) -> ToolResult | None:
    if category == IncidentCategory.KUBERNETES:
        payload = invoke_tool(k8s_get_pod_status, namespace="production", pod_name=target)
    elif category == IncidentCategory.KAFKA:
        payload = invoke_tool(kafka_get_broker_status, cluster=target)
    elif category == IncidentCategory.DATABASE:
        payload = invoke_tool(postgres_get_connection_pool_stats, service_name=target)
    elif category == IncidentCategory.CACHE:
        payload = invoke_tool(redis_get_memory_stats, instance=target)
    else:
        return None
    return ToolResult.model_validate(payload)


def metrics_analysis_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        task = state.get("current_task")
        task_description = task.description if task else "General metrics review for anomalies."
        intent = state.get("intent")
        category = intent.category if intent else IncidentCategory.UNKNOWN
        target = infer_target_name(state)

        component, metric_name = _METRIC_BY_CATEGORY.get(category, ("application", "http_5xx_rate_percent"))
        metrics_payload = invoke_tool(metrics_collector, component=component, metric_name=metric_name)
        samples = (
            [MetricSample.model_validate(s) for s in metrics_payload["data"]["samples"]]
            if tool_succeeded(metrics_payload)
            else []
        )

        snapshot_tool_name = _SNAPSHOT_TOOL_NAME_BY_CATEGORY.get(category)
        snapshot: ToolResult | None = None
        if snapshot_tool_name:
            selection_agent = get_agent(ToolSelectionAgent)
            decision = selection_agent.invoke(
                task_description=task_description,
                available_tools=(
                    f"{metrics_collector.name}: {metrics_collector.description}\n"
                    f"{snapshot_tool_name}: category-specific current-state snapshot, complements the "
                    "time series with a point-in-time health check."
                ),
            )
            if snapshot_tool_name in decision.selected_tools:
                snapshot = _snapshot_tool_result(category, target)

        agent = get_agent(MetricsAnalysisAgent)
        result = agent.invoke(task_description=task_description, raw_metrics=format_metrics(samples))

        updates: dict[str, Any] = {
            "metrics": samples,
            "tool_results": [snapshot] if snapshot else [],
            "reasoning": [
                ReasoningStep(
                    node_name="metrics_analysis",
                    content=(
                        f"{result.summary} | trend={result.trend} | breached={result.breached_thresholds} | "
                        f"confidence={result.confidence}"
                    ),
                )
            ],
        }
        return updates, result.summary

    return run_node("metrics_analysis", work)
