"""Root Cause Analysis node -- synthesizes the merged evidence into one
causal claim. Stored in `metadata["root_cause_analysis"]` since
`IncidentState` has no dedicated field for it (see `nodes/formatting.
format_root_cause`).
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.root_cause import RootCauseAnalysisAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_intent
from incident_agent.nodes.node_runner import run_node


def root_cause_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        agent = get_agent(RootCauseAnalysisAgent)
        evidence_bundle = state.get("metadata", {}).get("evidence_bundle", "(no evidence gathered)")
        result = agent.invoke(
            user_query=state["user_query"],
            intent=format_intent(state.get("intent")),
            evidence_bundle=evidence_bundle,
        )

        updates: dict[str, Any] = {
            "confidence_score": result.confidence,
            "metadata": {"root_cause_analysis": result.model_dump(mode="json")},
            "reasoning": [
                ReasoningStep(
                    node_name="root_cause_analysis",
                    content=f"{result.root_cause} (confidence={result.confidence})",
                )
            ],
        }
        return updates, result.root_cause

    return run_node("root_cause_analysis", work)
