"""Incident Resolution node -- turns the confirmed root cause into `draft_answer`."""

from __future__ import annotations

from typing import Any

from incident_agent.agents.incident_resolution import IncidentResolutionAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_root_cause
from incident_agent.nodes.node_runner import run_node


def incident_resolution_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        agent = get_agent(IncidentResolutionAgent)
        root_cause_analysis = format_root_cause(state.get("metadata", {}).get("root_cause_analysis"))
        result = agent.invoke(user_query=state["user_query"], root_cause_analysis=root_cause_analysis)

        updates: dict[str, Any] = {
            "draft_answer": result,
            "reasoning": [
                ReasoningStep(
                    node_name="incident_resolution",
                    content=f"Proposed {len(result.resolution_steps)}-step resolution, risk={result.risk_level.value}",
                )
            ],
        }
        return updates, result.summary

    return run_node("incident_resolution", work)
