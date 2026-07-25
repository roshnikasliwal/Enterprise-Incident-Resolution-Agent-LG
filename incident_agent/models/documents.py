"""Retrieval and citation domain models.

These represent data produced by *tools* (vector search, web search, SQL)
rather than by an LLM's own structured output, which is why they live in
models/ rather than schemas/. Agents consume and cite these; they don't
generate their shape from scratch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

RetrievalSource = Literal[
    "vector_store",
    "knowledge_base",
    "web_search",
    "sql_database",
    "knowledge_graph",
    "episodic_memory",
]


class RetrievedDocument(BaseModel):
    """A single chunk returned by any retrieval tool, normalized to one shape
    so downstream agents (Root Cause Analysis, Report Generator) don't need
    to special-case where a piece of evidence came from.
    """

    document_id: str
    source: RetrievalSource
    title: str
    content: str
    score: float = Field(ge=0.0, le=1.0, description="Normalized relevance score, 0-1.")
    metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Citation(BaseModel):
    """A pointer from a claim in the final answer back to supporting evidence.

    Kept deliberately thin (id + locator + snippet) -- the full document
    body stays in `retrieved_documents`; a citation is a reference, not a
    copy, so the final report doesn't duplicate large chunks of text.
    """

    citation_id: str
    document_id: str
    source: RetrievalSource
    locator: str = Field(description="e.g. a URL, a log file path, a SQL table name.")
    snippet: str = Field(max_length=500)
