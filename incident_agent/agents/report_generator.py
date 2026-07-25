"""Report Generator Agent -- produces the durable incident report."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.report_generator import REPORT_GENERATOR_PROMPT
from incident_agent.schemas.report import IncidentReport


class ReportGeneratorAgent(BaseAgent[IncidentReport]):
    name = "report_generator"
    prompt = REPORT_GENERATOR_PROMPT
    output_schema = IncidentReport
