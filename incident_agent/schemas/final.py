"""Final Response Agent structured output -- the last thing the graph produces."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FinalAnswer(BaseModel):
    answer: str = Field(description="The complete, user-facing resolution explanation.")
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list, description="citation_id values backing the answer.")
    incident_report_id: str | None = None
    follow_up_recommendations: list[str] = Field(default_factory=list)
