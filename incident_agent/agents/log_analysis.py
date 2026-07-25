"""Log Analysis Agent -- one branch of the parallel evidence fan-out."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.log_analysis import LOG_ANALYSIS_PROMPT
from incident_agent.schemas.analysis import LogAnalysisResult


class LogAnalysisAgent(BaseAgent[LogAnalysisResult]):
    name = "log_analysis"
    prompt = LOG_ANALYSIS_PROMPT
    output_schema = LogAnalysisResult
