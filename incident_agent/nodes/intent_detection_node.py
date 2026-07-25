"""Intent Detection node -- the graph's entry point."""

from __future__ import annotations

from typing import Any

from incident_agent.agents.intent_detection import IntentDetectionAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_memory_context
from incident_agent.nodes.node_runner import run_node


def intent_detection_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        agent = get_agent(IntentDetectionAgent)
        result = agent.invoke(
            user_query=state["user_query"],
            memory_context=format_memory_context(state.get("memory")),
        )
        updates: dict[str, Any] = {
            "intent": result,
            "reasoning": [
                ReasoningStep(
                    node_name="intent_detection",
                    content=f"Classified as {result.category.value}/{result.urgency.value}: {result.summary}",
                )
            ],
        }
        return updates, f"classified as {result.category.value} ({result.urgency.value} urgency)"

    return run_node("intent_detection", work)
