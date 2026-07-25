"""Reflection Agent -- diagnoses a failed attempt before the Planner replans."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.reflection import REFLECTION_PROMPT
from incident_agent.schemas.reflection import ReflectionOutput


class ReflectionAgent(BaseAgent[ReflectionOutput]):
    name = "reflection"
    prompt = REFLECTION_PROMPT
    output_schema = ReflectionOutput
