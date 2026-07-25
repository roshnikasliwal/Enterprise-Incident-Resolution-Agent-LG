"""Metrics Analysis Agent prompt -- one branch of the parallel evidence fan-out."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

METRICS_ANALYSIS_PROMPT = build_agent_prompt(
    agent_name="Metrics Analysis Agent",
    responsibility=(
        "Analyze the collected metric samples for this incident. Identify which metrics "
        "breached their thresholds, the overall trend (improving/stable/degrading), and "
        "which specific series are anomalous relative to their own recent history."
    ),
    human_template=(
        "Current investigation task:\n{task_description}\n\n"
        "Collected metric samples (JSON lines):\n{raw_metrics}"
    ),
)
