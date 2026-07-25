"""Memory domain models.

Shapes shared between the memory layer's stores (`memory/`, built in
Phase 6) and the graph state: `MemoryContext` is what gets recalled and
injected into `IncidentState["memory"]` before planning starts, so the
Planner and Root Cause Analysis agents can reference prior art instead of
re-deriving it from scratch every time.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from incident_agent.models.enums import IncidentCategory


class PastIncidentRecord(BaseModel):
    """A previously resolved incident, recalled via semantic similarity
    search over episodic memory."""

    incident_id: str
    title: str
    category: IncidentCategory
    root_cause: str
    resolution_summary: str
    resolved_at: datetime
    similarity_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Set only when recalled via similarity search."
    )


class UserPreference(BaseModel):
    """A learned, durable fact about how a specific user wants to be
    supported (e.g. preferred rollback strategy, notification channel)."""

    key: str
    value: str
    learned_at: datetime


class FrequentFix(BaseModel):
    """A resolution pattern that has recurred often enough to surface
    proactively before a full root-cause investigation."""

    fix_id: str
    description: str
    category: IncidentCategory
    usage_count: int = Field(ge=0)
    last_used_at: datetime


class MemoryContext(BaseModel):
    """Everything recalled from long-term/episodic/semantic memory for one run."""

    similar_past_incidents: list[PastIncidentRecord] = Field(default_factory=list)
    user_preferences: list[UserPreference] = Field(default_factory=list)
    frequent_fixes: list[FrequentFix] = Field(default_factory=list)
    conversation_summary: str | None = Field(
        default=None, description="Rolling summary of prior turns in this session, if any."
    )
