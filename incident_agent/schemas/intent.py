"""Intent Detection Agent structured output."""

from __future__ import annotations

from pydantic import BaseModel, Field

from incident_agent.models.enums import IncidentCategory, IncidentUrgency


class IntentClassification(BaseModel):
    category: IncidentCategory = Field(description="Primary subsystem this incident concerns.")
    secondary_categories: list[IncidentCategory] = Field(
        default_factory=list, description="Other subsystems plausibly involved."
    )
    urgency: IncidentUrgency
    summary: str = Field(description="One or two sentence restatement of the user's problem in precise technical terms.")
    keywords: list[str] = Field(
        default_factory=list, description="Technical terms extracted for retrieval query expansion."
    )
    requires_human_review: bool = Field(
        default=False, description="True for ambiguous, high-blast-radius, or security-sensitive reports."
    )
    confidence: float = Field(ge=0.0, le=1.0)
