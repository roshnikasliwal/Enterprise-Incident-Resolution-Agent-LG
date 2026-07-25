"""Root Cause Analysis Agent -- synthesizes every evidence branch into one causal claim."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.root_cause import ROOT_CAUSE_PROMPT
from incident_agent.schemas.root_cause import RootCauseAnalysis


class RootCauseAnalysisAgent(BaseAgent[RootCauseAnalysis]):
    name = "root_cause_analysis"
    prompt = ROOT_CAUSE_PROMPT
    output_schema = RootCauseAnalysis
