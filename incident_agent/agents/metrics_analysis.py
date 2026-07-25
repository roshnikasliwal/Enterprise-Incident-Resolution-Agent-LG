"""Metrics Analysis Agent -- one branch of the parallel evidence fan-out."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.metrics_analysis import METRICS_ANALYSIS_PROMPT
from incident_agent.schemas.analysis import MetricsAnalysisResult


class MetricsAnalysisAgent(BaseAgent[MetricsAnalysisResult]):
    name = "metrics_analysis"
    prompt = METRICS_ANALYSIS_PROMPT
    output_schema = MetricsAnalysisResult
