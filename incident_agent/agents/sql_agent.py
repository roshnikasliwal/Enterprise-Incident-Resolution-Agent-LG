"""SQL Agent -- text-to-SQL over the mock database, one branch of the fan-out.

Called twice by its node in practice (see Phase 5): once with empty
`query_results` to obtain `generated_query`, then again after the node
has actually executed that query via the `sql_query` tool, so the
agent's final `summary`/`key_findings` are grounded in real results
rather than a guess about what the query would return.
"""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent
from incident_agent.prompts.sql_agent import SQL_AGENT_PROMPT
from incident_agent.schemas.analysis import SQLAgentOutput


class SQLAgent(BaseAgent[SQLAgentOutput]):
    name = "sql_agent"
    prompt = SQL_AGENT_PROMPT
    output_schema = SQLAgentOutput
