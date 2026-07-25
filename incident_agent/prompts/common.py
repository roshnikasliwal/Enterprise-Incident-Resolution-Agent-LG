"""Shared prompt scaffolding.

`build_agent_prompt` is a small Factory: every one of the 17 agent
prompt modules calls it instead of hand-assembling a `ChatPromptTemplate`,
so the shared persona/formatting rules live in exactly one place. Without
this, a change to (say) the citation-formatting instruction would need
editing in 17 files instead of one.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

SYSTEM_PERSONA_PREAMBLE = """\
You are one specialist agent inside the Enterprise Incident Resolution Agent
system: a multi-agent AI Site Reliability Engineering team that investigates
and resolves production incidents across Kubernetes, Kafka, PostgreSQL,
Redis, and application/HTTP layers.

Ground rules that apply to every agent in this system:
- Reason only from the evidence you are given in this prompt. Never invent
  log lines, metric values, hostnames, or citation IDs that were not
  provided to you.
- If the evidence is insufficient to be confident, say so explicitly
  (low confidence, missing_evidence, etc.) rather than guessing.
- Be precise and technical. This output is read by senior engineers and by
  other AI agents downstream -- vague language wastes both.
- You always respond via the structured output format requested; never
  respond with unstructured prose."""


def build_agent_prompt(
    *,
    agent_name: str,
    responsibility: str,
    human_template: str,
    extra_system_notes: str = "",
) -> ChatPromptTemplate:
    """Compose one agent's `ChatPromptTemplate` from the shared persona plus
    its specific responsibility and input template.

    Args:
        agent_name: Short display name, e.g. "Root Cause Analysis Agent".
        responsibility: What this agent alone is responsible for deciding.
        human_template: The `HumanMessage` template string; its `{vars}`
            become this prompt's `input_variables`.
        extra_system_notes: Agent-specific system-level guidance appended
            after the shared ground rules (e.g. domain-specific heuristics).
    """
    system_message = "\n\n".join(
        part
        for part in (
            SYSTEM_PERSONA_PREAMBLE,
            f"Your specific role in this system: {agent_name}.\n{responsibility}",
            extra_system_notes.strip() or None,
        )
        if part
    )
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_message),
            ("human", human_template),
        ]
    )
