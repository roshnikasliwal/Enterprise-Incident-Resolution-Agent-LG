"""Retriever Agent prompt -- drives the RAG pipeline's query formulation.

The agent's job is query understanding (multi-query expansion / self-query
metadata filtering), not final synthesis -- the actual vector search runs
as a tool call the node issues using this agent's output.
"""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

RETRIEVER_PROMPT = build_agent_prompt(
    agent_name="Retriever Agent",
    responsibility=(
        "Formulate the search queries that will be run against the internal knowledge base "
        "(runbooks, past incident postmortems, architecture docs). Produce several "
        "differently-phrased queries (multi-query retrieval) to maximize recall, and "
        "identify any metadata filters (e.g. component name, document type) that should "
        "narrow the search."
    ),
    human_template=(
        "User-reported issue:\n{user_query}\n\n"
        "Intent classification:\n{intent}\n\n"
        "Current investigation task:\n{task_description}"
    ),
)
