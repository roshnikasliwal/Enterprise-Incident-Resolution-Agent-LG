"""Recall Memory node -- the graph's entry point, before intent detection.

Runs first (not after intent detection) so that even the Intent
Detection Agent benefits from recalled context (e.g. "this user has
reported three checkout-api OOM incidents this week" is relevant to
urgency classification, not just to planning). The tradeoff: incident
*category* isn't known yet at this point, so `frequent_fixes` -- which is
looked up per-category -- is necessarily empty on this first pass.
Similar-past-incidents (semantic search needs only the raw query text),
conversation summary, and user preferences are all category-independent
and fully populated.
"""

from __future__ import annotations

from typing import Any

from incident_agent.graphs.state import IncidentState
from incident_agent.memory.memory_service import get_memory_service
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.node_runner import run_node


def recall_memory_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        service = get_memory_service()
        service.register_thread(state["session_id"], state["thread_id"], state["incident_id"])

        intent = state.get("intent")
        memory_context = service.recall(
            user_query=state["user_query"],
            category=intent.category if intent else None,
            session_id=state["session_id"],
        )

        updates: dict[str, Any] = {
            "memory": memory_context,
            "reasoning": [
                ReasoningStep(
                    node_name="recall_memory",
                    content=(
                        f"Recalled {len(memory_context.similar_past_incidents)} similar past incident(s), "
                        f"{len(memory_context.frequent_fixes)} frequent fix(es)."
                    ),
                )
            ],
        }
        summary = (
            f"{len(memory_context.similar_past_incidents)} similar incident(s), "
            f"{len(memory_context.frequent_fixes)} frequent fix(es) recalled"
        )
        return updates, summary

    return run_node("recall_memory", work)
