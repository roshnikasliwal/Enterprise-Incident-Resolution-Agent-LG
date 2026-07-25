"""Knowledge Graph Agent prompt -- service-dependency / blast-radius reasoning."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

KNOWLEDGE_GRAPH_PROMPT = build_agent_prompt(
    agent_name="Knowledge Graph Agent",
    responsibility=(
        "Given the service-dependency graph context provided, identify which entities "
        "(services, databases, queues) are related to the components implicated in this "
        "incident, and describe the relevant relationships -- especially anything that "
        "explains how a failure could propagate (blast radius)."
    ),
    human_template=(
        "Current investigation task:\n{task_description}\n\n"
        "Dependency graph context (entities and relationships available):\n{graph_context}"
    ),
)
