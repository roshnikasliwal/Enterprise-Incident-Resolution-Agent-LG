"""Structured outputs for the parallel evidence-gathering agents.

One class per agent (Log Analysis, Metrics Analysis, SQL, Knowledge
Graph, Web Search) -- these are each agent's *synthesis* over raw tool
output (`models.tool_results`), not the raw tool output itself. Every
one carries its own `confidence` because the Root Cause Analysis Agent
weighs evidence branches against each other; a branch that found nothing
should say so with low confidence rather than omitting fields.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LogAnalysisResult(BaseModel):
    summary: str
    error_patterns: list[str] = Field(
        default_factory=list, description="Recurring error signatures found across log entries."
    )
    affected_components: list[str] = Field(default_factory=list)
    anomaly_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)


class MetricsAnalysisResult(BaseModel):
    summary: str
    breached_thresholds: list[str] = Field(default_factory=list)
    anomalous_metrics: list[str] = Field(default_factory=list)
    trend: Literal["improving", "stable", "degrading"]
    confidence: float = Field(ge=0.0, le=1.0)


class SQLAgentOutput(BaseModel):
    summary: str
    generated_query: str = Field(description="The SQL query the agent chose to run.")
    key_findings: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class KnowledgeGraphResult(BaseModel):
    summary: str
    related_entities: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(
        default_factory=list,
        description="Human-readable relationship triples, e.g. 'checkout-service depends_on postgres-primary'.",
    )
    confidence: float = Field(ge=0.0, le=1.0)


class WebSearchResult(BaseModel):
    summary: str
    key_findings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list, description="URLs or source identifiers backing the findings.")
    confidence: float = Field(ge=0.0, le=1.0)
