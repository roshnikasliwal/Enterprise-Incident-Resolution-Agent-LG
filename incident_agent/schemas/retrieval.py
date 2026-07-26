"""Retriever Agent structured output.

This is query *formulation* (multi-query expansion + self-query metadata
filters) -- the resulting `RetrievedDocument` objects (see
`models.documents`) come from actually executing these queries against
the vector search tool, which is a separate, non-LLM step.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RetrievalQueryPlan(BaseModel):
    queries: list[str] = Field(
        min_length=1,
        description="Multiple differently-phrased search queries covering the same information need "
        "(multi-query retrieval), to maximize recall against the knowledge base.",
    )
    doc_type: Literal["runbook", "postmortem"] | None = Field(
        default=None,
        description="Self-query metadata filter: restrict results to this single document type if the "
        "query clearly calls for step-by-step remediation ('runbook') or a past-incident writeup "
        "('postmortem'). Omit (null) if either type could be relevant -- do not guess.",
    )
