"""Web Search node -- one branch of the parallel evidence-gathering subgraph.

No real web-search API is in scope for this project (only `rest_api_call`,
a generic HTTP tool, exists -- there's no dedicated search-engine tool to
call, and hitting a real search API would require a paid key). Results are
generated deterministically from the query, following the same
`utils.mock_data` pattern the Kubernetes/Kafka/Postgres/Redis tools use,
wrapped in a `ToolResult` for the same auditability those tools get.
"""

from __future__ import annotations

import time
from typing import Any

from incident_agent.agents.web_search import WebSearchAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.enums import ToolStatus
from incident_agent.models.execution import ReasoningStep
from incident_agent.models.tool_results import ToolResult
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.node_runner import run_node
from incident_agent.utils.mock_data import deterministic_rng, pick_scenario

_SCENARIOS = ("known_issue", "vendor_status_incident", "no_results")


def _mock_search(query: str) -> list[dict[str, str]]:
    scenario = pick_scenario(query, _SCENARIOS)
    rng = deterministic_rng(query)
    if scenario == "no_results":
        return []
    if scenario == "known_issue":
        return [
            {
                "title": "GitHub Issue: intermittent failures under connection pool pressure",
                "url": "https://github.com/example-org/example-lib/issues/4821",
                "snippet": (
                    "Multiple users report the same symptom after upgrading past v3.2.0 -- the "
                    "library's default pool size changed from 20 to 10 in that release."
                ),
            },
            {
                "title": "Changelog v3.2.0",
                "url": "https://example-lib.dev/changelog#3.2.0",
                "snippet": "BREAKING: default `pool_size` reduced from 20 to 10 to lower idle connection overhead.",
            },
        ]
    return [
        {
            "title": "Vendor Status Page -- Partial Outage",
            "url": "https://status.example-vendor.com/incidents/9f3a",
            "snippet": f"Investigating elevated error rates in the {rng.choice(['us-east', 'eu-west'])} region.",
        }
    ]


def web_search_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        task = state.get("current_task")
        query = task.description if task else state["user_query"]

        started = time.perf_counter()
        results = _mock_search(query)
        latency_ms = (time.perf_counter() - started) * 1000
        tool_result = ToolResult(
            tool_name="web_search_mock",
            status=ToolStatus.SUCCESS,
            data={"query": query, "results": results},
            latency_ms=latency_ms,
        )

        results_text = (
            "\n".join(f"- {r['title']} ({r['url']}): {r['snippet']}" for r in results)
            if results
            else "(no results found)"
        )

        agent = get_agent(WebSearchAgent)
        result = agent.invoke(task_description=query, search_results=results_text)

        updates: dict[str, Any] = {
            "tool_results": [tool_result],
            "reasoning": [
                ReasoningStep(
                    node_name="web_search",
                    content=f"{result.summary} | findings={result.key_findings} | confidence={result.confidence}",
                )
            ],
        }
        return updates, result.summary

    return run_node("web_search", work)
