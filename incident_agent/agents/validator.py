"""Validator Agent -- checks the draft answer against evidence; produces the
confidence score that drives the graph's replan-vs-proceed routing decision.
"""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.validator import VALIDATOR_PROMPT
from incident_agent.schemas.critique import ValidationResult


class ValidatorAgent(BaseAgent[ValidationResult]):
    name = "validator"
    prompt = VALIDATOR_PROMPT
    output_schema = ValidationResult
