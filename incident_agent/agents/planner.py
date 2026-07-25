"""Planner Agent -- produces the execution plan the parallel fan-out runs."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.planner import PLANNER_PROMPT
from incident_agent.schemas.planning import ExecutionPlan


class PlannerAgent(BaseAgent[ExecutionPlan]):
    name = "planner"
    prompt = PLANNER_PROMPT
    output_schema = ExecutionPlan
