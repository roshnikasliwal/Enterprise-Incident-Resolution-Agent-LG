"""Incident Resolution Agent -- turns a confirmed root cause into an actionable fix."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.incident_resolution import INCIDENT_RESOLUTION_PROMPT
from incident_agent.schemas.resolution import DraftAnswer


class IncidentResolutionAgent(BaseAgent[DraftAnswer]):
    name = "incident_resolution"
    prompt = INCIDENT_RESOLUTION_PROMPT
    output_schema = DraftAnswer
