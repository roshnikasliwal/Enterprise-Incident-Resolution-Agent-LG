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

from incident_agent.config.settings import get_settings
from incident_agent.graphs.state import IncidentState


def route_after_reflection(state: IncidentState) -> Literal["planner", "human_approval"]:
    settings = get_settings()
    should_replan = state.get("metadata", {}).get("last_reflection_should_replan", True)
    retry_count = state.get("retry_count", 0)

    if should_replan and retry_count < settings.max_replan_attempts:
        return "planner"
    return "human_approval"
