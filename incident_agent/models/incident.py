"""The top-level `Incident` domain entity.

Distinct from `IncidentState` (the LangGraph working state, which is
transient/per-run): `Incident` is the durable record persisted to the
memory store and surfaced through `GET /history`, independent of
whichever graph run(s) investigated it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from incident_agent.models.enums import IncidentCategory, IncidentUrgency
from incident_agent.utils.ids import generate_incident_id

IncidentStatus = Literal["open", "investigating", "awaiting_approval", "resolved", "closed"]


class Incident(BaseModel):
    incident_id: str = Field(default_factory=generate_incident_id)
    thread_id: str
    session_id: str
    title: str
    description: str
    category: IncidentCategory = IncidentCategory.UNKNOWN
    urgency: IncidentUrgency = IncidentUrgency.MEDIUM
    status: IncidentStatus = "open"
    reported_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
