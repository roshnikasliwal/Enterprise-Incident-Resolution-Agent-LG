"""Critic node -- adversarial quality review of `draft_answer`, independent
of the Validator's evidence-grounding check (see `schemas/critique.py`).
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.critic import CriticAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_draft_answer, format_root_cause
from incident_agent.nodes.node_runner import run_node


def critic_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        agent = get_agent(CriticAgent)
        result = agent.invoke(
            root_cause_analysis=format_root_cause(state.get("metadata", {}).get("root_cause_analysis")),
            draft_answer=format_draft_answer(state.get("draft_answer")),
        )

        updates: dict[str, Any] = {
            "critic_feedback": result,
            "reasoning": [
                ReasoningStep(node_name="critic", content=f"approve={result.approve}: {result.overall_assessment}")
            ],
        }
        return updates, f"approve={result.approve}, {len(result.issues)} issue(s) raised"

    return run_node("critic", work)
