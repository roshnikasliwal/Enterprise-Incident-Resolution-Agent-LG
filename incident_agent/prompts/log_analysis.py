"""Log Analysis Agent prompt -- one branch of the parallel evidence fan-out."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

LOG_ANALYSIS_PROMPT = build_agent_prompt(
    agent_name="Log Analysis Agent",
    responsibility=(
        "Analyze the raw log entries collected for this incident. Identify recurring error "
        "signatures (group similar messages, don't just list every line), the components "
        "they implicate, and the overall severity of what the logs show."
    ),
    extra_system_notes=(
        "If the logs show nothing anomalous, say so explicitly with a low anomaly_count and "
        "confidence rather than manufacturing a pattern -- a clean bill of health is a valid "
        "and useful finding for the Root Cause Analysis Agent."
    ),
    human_template=(
        "Current investigation task:\n{task_description}\n\n"
        "Collected log entries (JSON lines, newest last):\n{raw_logs}"
    ),
)
