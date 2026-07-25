"""Knowledge Graph Agent -- service-dependency / blast-radius reasoning branch."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.knowledge_graph import KNOWLEDGE_GRAPH_PROMPT
from incident_agent.schemas.analysis import KnowledgeGraphResult


class KnowledgeGraphAgent(BaseAgent[KnowledgeGraphResult]):
    name = "knowledge_graph"
    prompt = KNOWLEDGE_GRAPH_PROMPT
    output_schema = KnowledgeGraphResult
