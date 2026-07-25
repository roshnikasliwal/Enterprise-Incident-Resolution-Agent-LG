"""Web Search Agent -- external/third-party evidence branch."""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.web_search import WEB_SEARCH_PROMPT
from incident_agent.schemas.analysis import WebSearchResult


class WebSearchAgent(BaseAgent[WebSearchResult]):
    name = "web_search"
    prompt = WEB_SEARCH_PROMPT
    output_schema = WebSearchResult
