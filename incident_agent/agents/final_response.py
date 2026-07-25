"""Final Response Agent -- the last node before returning to the user."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.final_response import FINAL_RESPONSE_PROMPT
from incident_agent.schemas.final import FinalAnswer


class FinalResponseAgent(BaseAgent[FinalAnswer]):
    name = "final_response"
    prompt = FINAL_RESPONSE_PROMPT
    output_schema = FinalAnswer
