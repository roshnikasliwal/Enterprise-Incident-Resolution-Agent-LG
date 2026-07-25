"""Reflection Agent prompt -- diagnoses a failed attempt before replanning."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

REFLECTION_PROMPT = build_agent_prompt(
    agent_name="Reflection Agent",
    responsibility=(
        "Diagnose why the current attempt fell short -- either confidence was below the "
        "required threshold, or the Critic rejected the draft. Identify specifically what "
        "evidence is missing or what reasoning went wrong, and give the Planner concrete, "
        "actionable guidance for the next attempt. Vague guidance like 'try harder' is "
        "useless -- name the specific gap."
    ),
    human_template=(
        "Current execution plan:\n{plan}\n\n"
        "Draft answer produced:\n{draft_answer}\n\n"
        "Critic feedback (if any):\n{critic_feedback}\n\n"
        "Validation result (if any):\n{validated_answer}\n\n"
        "Confidence score achieved: {confidence_score}"
    ),
)
