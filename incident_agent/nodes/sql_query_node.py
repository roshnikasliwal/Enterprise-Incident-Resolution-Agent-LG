"""SQL Query node -- one branch of the parallel evidence-gathering subgraph.

Calls the SQL Agent *twice*, matching its prompt design (see
`prompts/sql_agent.py`): once to generate a query against the schema
alone, then again -- after actually executing that query via the
`sql_query` tool -- to summarize the real results. This is deliberately
not a single LLM call: grounding the summary in the query's *actual*
output (rather than the model's guess about what it would return) is
exactly what makes this evidence trustworthy for Root Cause Analysis.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.sql_agent import SQLAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.models.tool_results import SQLQueryResult
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_sql_results
from incident_agent.nodes.node_runner import run_node
from incident_agent.nodes.tool_invocation import invoke_tool, tool_succeeded
from incident_agent.services.mock_database import get_schema_description
from incident_agent.tools.sql_query import sql_query


def sql_query_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        task = state.get("current_task")
        task_description = task.description if task else "General database health review."
        schema_description = get_schema_description()

        agent = get_agent(SQLAgent)
        drafted = agent.invoke(
            task_description=task_description,
            schema_description=schema_description,
            query_results="(query not yet executed)",
        )

        query_payload = invoke_tool(sql_query, query=drafted.generated_query)
        if tool_succeeded(query_payload):
            sql_result = SQLQueryResult.model_validate(query_payload["data"])
            results_text = format_sql_results([sql_result])
        else:
            sql_result = None
            results_text = f"Query failed: {query_payload.get('error_message')}"

        final = agent.invoke(
            task_description=task_description,
            schema_description=schema_description,
            query_results=results_text,
        )

        updates: dict[str, Any] = {
            "sql_results": [sql_result] if sql_result else [],
            "reasoning": [
                ReasoningStep(
                    node_name="sql_query",
                    content=(
                        f"{final.summary} | query={final.generated_query} | "
                        f"findings={final.key_findings} | confidence={final.confidence}"
                    ),
                )
            ],
        }
        return updates, final.summary

    return run_node("sql_query", work)
