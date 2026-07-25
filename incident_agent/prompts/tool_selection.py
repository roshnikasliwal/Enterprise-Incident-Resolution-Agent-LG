"""Tool Selection Agent prompt -- chooses which concrete tools a task should invoke."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

TOOL_SELECTION_PROMPT = build_agent_prompt(
    agent_name="Tool Selection Agent",
    responsibility=(
        "Given an investigation task and the list of tools available to it, decide exactly "
        "which tool(s) should be invoked to accomplish it. Prefer the minimum set of tools "
        "that will produce sufficient evidence -- invoking every available tool for every "
        "task wastes latency and cost."
    ),
    human_template=(
        "Current investigation task:\n{task_description}\n\n"
        "Tools available for this task type (name: description):\n{available_tools}"
    ),
)
