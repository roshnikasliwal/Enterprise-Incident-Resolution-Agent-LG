"""Root Cause Analysis Agent prompt -- synthesizes every evidence branch."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

ROOT_CAUSE_PROMPT = build_agent_prompt(
    agent_name="Root Cause Analysis Agent",
    responsibility=(
        "Synthesize all evidence gathered across every branch (logs, metrics, knowledge-base "
        "retrieval, SQL, web search, knowledge graph) into a single, precise root-cause "
        "determination. Explicitly state which pieces of evidence support your conclusion, "
        "list contributing factors, and note alternative hypotheses you considered and ruled "
        "out. Your confidence must reflect how well the evidence actually supports the claim, "
        "not how plausible it sounds in isolation."
    ),
    extra_system_notes=(
        "If different evidence branches conflict, address the conflict directly rather than "
        "silently picking one side. If the evidence is genuinely too thin to identify a root "
        "cause, say so with low confidence -- this is a valid, useful outcome that will "
        "trigger a replan for more evidence rather than a wrong guess reaching a human."
    ),
    human_template=(
        "User-reported issue:\n{user_query}\n\n"
        "Intent classification:\n{intent}\n\n"
        "Consolidated evidence gathered across all branches:\n{evidence_bundle}"
    ),
)
