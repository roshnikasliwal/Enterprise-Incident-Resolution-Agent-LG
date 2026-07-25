"""Intent Detection Agent -- classifies the incoming incident report."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.intent_detection import INTENT_DETECTION_PROMPT
from incident_agent.schemas.intent import IntentClassification


class IntentDetectionAgent(BaseAgent[IntentClassification]):
    name = "intent_detection"
    prompt = INTENT_DETECTION_PROMPT
    output_schema = IntentClassification
