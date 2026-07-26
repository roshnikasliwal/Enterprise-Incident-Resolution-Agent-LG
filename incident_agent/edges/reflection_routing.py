"""Post-reflection conditional edge.

The Reflection Agent itself can decide more evidence gathering won't
help (`should_replan=False` -- e.g. the evidence is simply inconclusive,
not incomplete); in that case looping back to the Planner again would
waste a retry attempt on a re-run unlikely to change the outcome, so we
route straight to human approval instead and let the (already low)
confidence score speak for itself in the approval brief.
"""

from __future__ import annotations

from typing import Literal

from incident_agent.config.logging_config import get_logger
from incident_agent.config.settings import get_settings
from incident_agent.graphs.state import IncidentState

logger = get_logger(__name__)


def route_after_reflection(state: IncidentState) -> Literal["planner", "human_approval"]:
    settings = get_settings()
    should_replan = state.get("metadata", {}).get("last_reflection_should_replan", True)
    retry_count = state.get("retry_count", 0)

    decision: Literal["planner", "human_approval"] = (
        "planner" if should_replan and retry_count < settings.max_replan_attempts else "human_approval"
    )
    logger.info(
        "reflection_routing",
        extra={"should_replan": should_replan, "retry_count": retry_count, "decision": decision},
    )
    return decision
