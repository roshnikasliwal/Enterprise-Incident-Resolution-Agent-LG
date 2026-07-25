"""Critic Agent -- adversarial quality review of the draft answer."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.critic import CRITIC_PROMPT
from incident_agent.schemas.critique import CriticFeedback


class CriticAgent(BaseAgent[CriticFeedback]):
    name = "critic"
    prompt = CRITIC_PROMPT
    output_schema = CriticFeedback
