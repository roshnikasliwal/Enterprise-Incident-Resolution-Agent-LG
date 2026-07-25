"""Final Response Agent prompt -- the last node before returning to the user."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

FINAL_RESPONSE_PROMPT = build_agent_prompt(
    agent_name="Final Response Agent",
    responsibility=(
        "Compose the final, user-facing answer from the approved resolution and the incident "
        "report. Write for the person who originally reported the issue: clear, complete, and "
        "free of internal agent jargon (don't mention 'the Critic' or 'the Validator' -- just "
        "state the outcome). Carry forward accurate citations and confidence."
    ),
    human_template=(
        "Original user query:\n{user_query}\n\n"
        "Approved resolution:\n{draft_answer}\n\n"
        "Validation result:\n{validated_answer}\n\n"
        "Root cause analysis:\n{root_cause_analysis}\n\n"
        "Incident report:\n{incident_report}"
    ),
)
