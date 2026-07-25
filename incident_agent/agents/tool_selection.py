"""Tool Selection Agent -- chooses which concrete tools a task should invoke."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.tool_selection import TOOL_SELECTION_PROMPT
from incident_agent.schemas.tool_selection import ToolSelectionDecision


class ToolSelectionAgent(BaseAgent[ToolSelectionDecision]):
    name = "tool_selection"
    prompt = TOOL_SELECTION_PROMPT
    output_schema = ToolSelectionDecision
