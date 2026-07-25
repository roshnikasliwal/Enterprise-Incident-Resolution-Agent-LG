"""Agent registry -- name -> class, so Phase 5 nodes and Phase 11 tests can
look agents up generically (`get_agent_class("critic")`) instead of importing
all 17 agent modules by hand everywhere one is needed.
"""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.agents.critic import CriticAgent
from incident_agent.agents.final_response import FinalResponseAgent
from incident_agent.agents.human_approval import HumanApprovalAgent
from incident_agent.agents.incident_resolution import IncidentResolutionAgent
from incident_agent.agents.intent_detection import IntentDetectionAgent
from incident_agent.agents.knowledge_graph import KnowledgeGraphAgent
from incident_agent.agents.log_analysis import LogAnalysisAgent
from incident_agent.agents.metrics_analysis import MetricsAnalysisAgent
from incident_agent.agents.planner import PlannerAgent
from incident_agent.agents.reflection import ReflectionAgent
from incident_agent.agents.report_generator import ReportGeneratorAgent
from incident_agent.agents.retriever import RetrieverAgent
from incident_agent.agents.root_cause import RootCauseAnalysisAgent
from incident_agent.agents.sql_agent import SQLAgent
from incident_agent.agents.tool_selection import ToolSelectionAgent
from incident_agent.agents.validator import ValidatorAgent
from incident_agent.agents.web_search import WebSearchAgent

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    agent_cls.name: agent_cls
    for agent_cls in (
        IntentDetectionAgent,
        PlannerAgent,
        RetrieverAgent,
        LogAnalysisAgent,
        MetricsAnalysisAgent,
        SQLAgent,
        KnowledgeGraphAgent,
        WebSearchAgent,
        ToolSelectionAgent,
        RootCauseAnalysisAgent,
        IncidentResolutionAgent,
        CriticAgent,
        ValidatorAgent,
        ReportGeneratorAgent,
        HumanApprovalAgent,
        ReflectionAgent,
        FinalResponseAgent,
    )
}


def get_agent_class(name: str) -> type[BaseAgent]:
    try:
        return AGENT_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown agent '{name}'. Available agents: {sorted(AGENT_REGISTRY)}") from exc
