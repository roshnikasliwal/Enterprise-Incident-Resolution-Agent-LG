"""Validator node -- checks `draft_answer` against gathered evidence and
sets `confidence_score`, the value the confidence-check edge routes on.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.validator import ValidatorAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_draft_answer, format_root_cause
from incident_agent.nodes.node_runner import run_node


def validator_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        agent = get_agent(ValidatorAgent)
        result = agent.invoke(
            draft_answer=format_draft_answer(state.get("draft_answer")),
            root_cause_analysis=format_root_cause(state.get("metadata", {}).get("root_cause_analysis")),
            evidence_bundle=state.get("metadata", {}).get("evidence_bundle", "(no evidence gathered)"),
        )

        updates: dict[str, Any] = {
            "validated_answer": result,
            "confidence_score": result.confidence_score,
            "reasoning": [
                ReasoningStep(
                    node_name="validator",
                    content=f"is_valid={result.is_valid}, confidence={result.confidence_score}",
                )
            ],
        }
        return updates, f"validation confidence={result.confidence_score}"

    return run_node("validator", work)
