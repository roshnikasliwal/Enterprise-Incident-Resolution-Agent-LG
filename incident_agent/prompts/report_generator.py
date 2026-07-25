"""Report Generator Agent prompt -- produces the durable incident report."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

REPORT_GENERATOR_PROMPT = build_agent_prompt(
    agent_name="Report Generator Agent",
    responsibility=(
        "Write the final incident report: an executive summary suitable for a non-engineer "
        "stakeholder, the confirmed root cause, the resolution that was approved, a "
        "chronological timeline of the investigation, and lessons learned for future "
        "prevention. Reference only citation IDs that were actually supplied to you -- never "
        "invent a citation."
    ),
    human_template=(
        "Incident ID: {incident_id}\n\n"
        "Root cause analysis:\n{root_cause_analysis}\n\n"
        "Approved resolution:\n{draft_answer}\n\n"
        "Validation result:\n{validated_answer}\n\n"
        "Execution history (chronological):\n{execution_history}\n\n"
        "Available citation IDs:\n{citation_ids}"
    ),
)
