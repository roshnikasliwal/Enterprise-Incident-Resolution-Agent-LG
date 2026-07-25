"""Report Generator Agent structured output.

`citations` deliberately holds `citation_id` strings, not full `Citation`
objects: the citations already exist in `IncidentState["citations"]` by
the time this agent runs (produced by retrieval/root-cause), so asking
the LLM to re-emit citation content would only invite it to paraphrase
or hallucinate snippets instead of pointing at the real evidence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IncidentReport(BaseModel):
    title: str
    executive_summary: str
    root_cause: str
    resolution_summary: str
    timeline: list[str] = Field(
        default_factory=list, description="Chronological, human-readable narrative of the investigation."
    )
    citations: list[str] = Field(
        default_factory=list, description="citation_id values (from IncidentState.citations) referenced above."
    )
    lessons_learned: list[str] = Field(default_factory=list)
