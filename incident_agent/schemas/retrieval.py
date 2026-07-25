"""Retriever Agent structured output.

This is query *formulation* (multi-query expansion + self-query metadata
filters) -- the resulting `RetrievedDocument` objects (see
`models.documents`) come from actually executing these queries against
the vector search tool, which is a separate, non-LLM step.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievalQueryPlan(BaseModel):
    queries: list[str] = Field(
        min_length=1,
        description="Multiple differently-phrased search queries covering the same information need "
        "(multi-query retrieval), to maximize recall against the knowledge base.",
    )
    metadata_filters: dict[str, str] = Field(
        default_factory=dict,
        description="Self-query metadata filters, e.g. {'component': 'kafka'} or {'doc_type': 'runbook'}.",
    )
