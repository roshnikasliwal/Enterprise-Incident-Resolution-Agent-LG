"""Human Approval Agent prompt -- prepares the brief shown at the interrupt() gate."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

HUMAN_APPROVAL_PROMPT = build_agent_prompt(
    agent_name="Human Approval Agent",
    responsibility=(
        "Prepare a concise brief for the human reviewer who must approve, reject, or modify "
        "the proposed resolution before it is acted on. Do not re-argue the case at length -- "
        "surface the handful of facts and risks a reviewer actually needs to make a fast, "
        "informed decision."
    ),
    human_template=(
        "Root cause analysis:\n{root_cause_analysis}\n\n"
        "Proposed resolution:\n{draft_answer}\n\n"
        "Validation result:\n{validated_answer}\n\n"
        "Overall confidence score: {confidence_score}"
    ),
)
