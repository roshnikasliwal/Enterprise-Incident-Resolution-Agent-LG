"""Reflection node -- the retry cycle's diagnostic step. Runs only when
`edges/confidence_check.route_after_confidence_check` decides confidence
is too low (or the Critic rejected the draft) and retries remain; its
`retry_count` increment is what eventually lets that same edge stop
looping and force a decision.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.reflection import ReflectionAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import (
    format_critic_feedback,
    format_draft_answer,
    format_plan,
    format_validation_result,
)
from incident_agent.nodes.node_runner import run_node


def reflection_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        agent = get_agent(ReflectionAgent)
        result = agent.invoke(
            plan=format_plan(state.get("plan")),
            draft_answer=format_draft_answer(state.get("draft_answer")),
            critic_feedback=format_critic_feedback(state.get("critic_feedback")),
            validated_answer=format_validation_result(state.get("validated_answer")),
            confidence_score=str(state.get("confidence_score", 0.0)),
        )

        updates: dict[str, Any] = {
            "retry_count": state.get("retry_count", 0) + 1,
            "reasoning": [
                ReasoningStep(
                    node_name="reflection",
                    content=result.guidance_for_replanner,
                )
            ],
            "metadata": {"last_reflection_should_replan": result.should_replan},
        }
        return updates, result.what_went_wrong

    return run_node("reflection", work)
