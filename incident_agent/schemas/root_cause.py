"""Root Cause Analysis Agent structured output.

This is the pivot point of the whole graph: it synthesizes every
evidence branch (`retrieved_documents`, `tool_results`, `logs`,
`metrics`, `sql_results`) into a single causal claim, which the
Validator and Critic then interrogate before anything reaches a human.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RootCauseAnalysis(BaseModel):
    root_cause: str = Field(description="The single most likely root cause, stated precisely.")
    contributing_factors: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    evidence_summary: str = Field(
        description="How the gathered evidence (logs/metrics/docs/sql) supports this conclusion."
    )
    alternative_hypotheses: list[str] = Field(
        default_factory=list,
        description="Other plausible causes considered and why they were ruled out or ranked lower.",
    )
    confidence: float = Field(ge=0.0, le=1.0)
