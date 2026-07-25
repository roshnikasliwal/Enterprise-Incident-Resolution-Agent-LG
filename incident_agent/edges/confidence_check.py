"""Confidence-check conditional edge -- the retry cycle's entry gate.

Reads `confidence_score` (set by the Validator) and `critic_feedback.
approve` (set by the Critic) to decide whether the draft answer is good
enough to show a human, or needs another investigation pass via
`reflection_node`. `retry_count` bounds the cycle so a persistently
low-confidence incident still reaches a human decision eventually,
rather than looping forever.
"""

from __future__ import annotations

from typing import Literal

from incident_agent.config.settings import get_settings
from incident_agent.graphs.state import IncidentState


def route_after_confidence_check(state: IncidentState) -> Literal["reflection", "human_approval"]:
    settings = get_settings()
    confidence = state.get("confidence_score", 0.0)
    critic_feedback = state.get("critic_feedback")
    critic_approves = critic_feedback.approve if critic_feedback is not None else True
    retry_count = state.get("retry_count", 0)

    needs_another_pass = confidence < settings.confidence_threshold or not critic_approves
    if needs_another_pass and retry_count < settings.max_replan_attempts:
        return "reflection"
    return "human_approval"
