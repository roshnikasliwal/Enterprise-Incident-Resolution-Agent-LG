"""Validator Agent prompt -- checks the draft answer against evidence, not style."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

VALIDATOR_PROMPT = build_agent_prompt(
    agent_name="Validator Agent",
    responsibility=(
        "Check every factual claim in the draft resolution against the evidence actually "
        "gathered during this investigation. For each distinct claim, run one named check: "
        "does the evidence bundle support it, contradict it, or say nothing about it? "
        "Produce an overall confidence score reflecting how well-grounded the draft is -- "
        "this score directly controls whether the graph proceeds to human approval or loops "
        "back to gather more evidence, so be strict rather than generous."
    ),
    human_template=(
        "Draft resolution to validate:\n{draft_answer}\n\n"
        "Root cause analysis it is based on:\n{root_cause_analysis}\n\n"
        "Consolidated evidence gathered during this investigation:\n{evidence_bundle}"
    ),
)
