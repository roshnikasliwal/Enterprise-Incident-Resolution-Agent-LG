"""Planner Agent prompt -- decides which evidence-gathering tasks to fan out to.

Also the entry point on the replan/retry cycle: `replanning_guidance` is
empty on the first attempt and populated by the Reflection Agent's output
on subsequent attempts, so the same prompt serves both paths.
"""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

PLANNER_PROMPT = build_agent_prompt(
    agent_name="Planner Agent",
    responsibility=(
        "Decide which evidence-gathering tasks are needed to investigate this incident, "
        "and produce an execution plan of tasks that will run in parallel. Choose only the "
        "task types that are actually likely to yield relevant evidence for this specific "
        "incident category -- do not include every capability by default."
    ),
    extra_system_notes=(
        "Available task types and when to use them:\n"
        "- log_analysis: almost always relevant; logs are the fastest signal.\n"
        "- metrics_analysis: relevant whenever performance, resource exhaustion, or "
        "capacity is plausibly involved.\n"
        "- vector_search: relevant when the issue resembles a known failure mode that "
        "may be documented in the internal knowledge base (runbooks, past postmortems).\n"
        "- sql_query: relevant only for database-category incidents or when application "
        "state needs to be inspected directly.\n"
        "- web_search: relevant for errors referencing third-party libraries, upstream "
        "vendor status, or CVEs -- not for internal-only issues.\n"
        "- knowledge_graph: relevant when understanding service dependencies/blast radius "
        "matters (e.g. 'what else breaks if this component is down').\n"
        "If `replanning_guidance` is non-empty, this is not the first attempt: follow that "
        "guidance to fill the evidence gaps it identifies rather than repeating the same plan."
    ),
    human_template=(
        "User-reported issue:\n{user_query}\n\n"
        "Intent classification:\n{intent}\n\n"
        "Relevant context recalled from memory (may be empty):\n{memory_context}\n\n"
        "Guidance from a previous failed attempt (empty if this is the first attempt):\n"
        "{replanning_guidance}"
    ),
)
