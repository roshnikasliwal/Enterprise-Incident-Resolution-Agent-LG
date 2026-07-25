"""Report Generator node -- runs only after human approval. Stored in
`metadata["incident_report"]` (no dedicated `IncidentState` field, same
reasoning as `root_cause_node`).
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.report_generator import ReportGeneratorAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import (
    format_draft_answer,
    format_execution_history,
    format_root_cause,
    format_validation_result,
)
from incident_agent.nodes.node_runner import run_node


def report_generator_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        agent = get_agent(ReportGeneratorAgent)
        citation_ids = ", ".join(c.citation_id for c in state.get("citations", [])) or "(none)"
        result = agent.invoke(
            incident_id=state["incident_id"],
            root_cause_analysis=format_root_cause(state.get("metadata", {}).get("root_cause_analysis")),
            draft_answer=format_draft_answer(state.get("draft_answer")),
            validated_answer=format_validation_result(state.get("validated_answer")),
            execution_history=format_execution_history(state.get("execution_history", [])),
            citation_ids=citation_ids,
        )

        updates: dict[str, Any] = {
            "metadata": {"incident_report": result.model_dump(mode="json")},
            "reasoning": [ReasoningStep(node_name="report_generator", content=f"Generated report: {result.title}")],
        }
        return updates, f"generated incident report '{result.title}'"

    return run_node("report_generator", work)
