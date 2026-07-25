"""Log Analysis node -- one branch of the parallel evidence-gathering
subgraph (see `graphs/evidence_subgraph.py`). Dispatched via the Send API
when the Planner includes a `log_analysis` task.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.log_analysis import LogAnalysisAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.models.tool_results import LogEntry, ToolResult
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_logs
from incident_agent.nodes.node_runner import run_node
from incident_agent.nodes.target_inference import infer_target_name
from incident_agent.nodes.tool_invocation import invoke_tool, tool_succeeded
from incident_agent.tools.kubernetes_tool import k8s_get_pod_logs, k8s_get_recent_events

_NAMESPACE = "production"


def log_analysis_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        task = state.get("current_task")
        pod_name = infer_target_name(state)

        logs_payload = invoke_tool(k8s_get_pod_logs, namespace=_NAMESPACE, pod_name=pod_name)
        events_payload = invoke_tool(k8s_get_recent_events, namespace=_NAMESPACE, pod_name=pod_name)

        log_entries = (
            [LogEntry.model_validate(e) for e in logs_payload["data"]["entries"]]
            if tool_succeeded(logs_payload)
            else []
        )
        events_tool_result = ToolResult.model_validate(events_payload)

        agent = get_agent(LogAnalysisAgent)
        result = agent.invoke(
            task_description=task.description if task else "General log review for anomalies.",
            raw_logs=format_logs(log_entries),
        )

        updates: dict[str, Any] = {
            "logs": log_entries,
            "tool_results": [events_tool_result],
            "reasoning": [
                ReasoningStep(
                    node_name="log_analysis",
                    content=(
                        f"{result.summary} | error_patterns={result.error_patterns} | "
                        f"anomaly_count={result.anomaly_count} | confidence={result.confidence}"
                    ),
                )
            ],
        }
        return updates, result.summary

    return run_node("log_analysis", work)
