"""Web Search Agent prompt -- external/third-party evidence."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

WEB_SEARCH_PROMPT = build_agent_prompt(
    agent_name="Web Search Agent",
    responsibility=(
        "Summarize what the provided web search results say that is relevant to this "
        "incident -- e.g. a known bug in a third-party library, an upstream vendor status "
        "incident, or a published CVE. Only use information present in the results; do not "
        "supplement with prior knowledge that isn't reflected in them."
    ),
    human_template=(
        "Current investigation task:\n{task_description}\n\n"
        "Web search results (title, url, snippet per result):\n{search_results}"
    ),
)
