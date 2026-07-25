"""Incident Resolution Agent structured output (the "draft answer")."""

from __future__ import annotations

from pydantic import BaseModel, Field

from incident_agent.models.enums import RiskLevel


class ResolutionStep(BaseModel):
    order: int = Field(ge=1)
    action: str
    command: str | None = Field(default=None, description="Concrete CLI/kubectl/SQL command, if applicable.")
    risk: RiskLevel = RiskLevel.LOW


class DraftAnswer(BaseModel):
    summary: str
    resolution_steps: list[ResolutionStep] = Field(min_length=1)
    rollback_plan: str | None = Field(default=None, description="How to undo these steps if they make things worse.")
    risk_level: RiskLevel
    estimated_impact: str = Field(description="Expected effect of applying this resolution, including any downtime.")
