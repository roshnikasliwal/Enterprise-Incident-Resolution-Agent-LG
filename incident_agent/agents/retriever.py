"""Retriever Agent -- formulates the RAG query plan (multi-query + self-query filters)."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.retriever import RETRIEVER_PROMPT
from incident_agent.schemas.retrieval import RetrievalQueryPlan


class RetrieverAgent(BaseAgent[RetrievalQueryPlan]):
    name = "retriever"
    prompt = RETRIEVER_PROMPT
    output_schema = RetrievalQueryPlan
