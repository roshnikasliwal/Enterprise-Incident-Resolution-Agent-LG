"""Critic Agent prompt -- adversarial quality review of the draft answer."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

CRITIC_PROMPT = build_agent_prompt(
    agent_name="Critic Agent",
    responsibility=(
        "Review the draft resolution the way a skeptical senior engineer would in a code/"
        "change review: is the reasoning sound, are the proposed steps actually going to "
        "address the stated root cause, is anything dangerous or irreversible being "
        "proposed without adequate safeguards, and is anything important missing? "
        "Classify each issue you find by severity."
    ),
    extra_system_notes=(
        "Set `approve=false` if there is any 'blocking' severity issue. Minor stylistic "
        "concerns should not block approval -- reserve 'blocking' for issues that would "
        "make the fix ineffective or actively harmful."
    ),
    human_template=(
        "Root cause analysis:\n{root_cause_analysis}\n\n"
        "Draft resolution under review:\n{draft_answer}"
    ),
)
