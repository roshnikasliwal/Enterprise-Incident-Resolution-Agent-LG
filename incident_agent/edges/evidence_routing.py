"""Dynamic parallel dispatch for the evidence-gathering subgraph -- the
Send API in action.

A *static* parallel fan-out (`add_edge(START, [nodeA, nodeB, ...])`) can't
express "run only the branches the Planner actually decided are relevant"
-- the set of branches varies per incident. `Send` lets a single
conditional-edge function emit a *list* of dynamically-targeted tasks,
one per plan task, each carrying its own `current_task` payload. LangGraph
runs all of them in the same parallel super-step and waits for every one
to finish before the subgraph's downstream nodes see merged state.
"""

from __future__ import annotations

from langgraph.types import Send

from incident_agent.graphs.state import IncidentState
from incident_agent.models.enums import TaskType

NODE_NAME_BY_TASK_TYPE: dict[TaskType, str] = {
    TaskType.LOG_ANALYSIS: "log_analysis",
    TaskType.METRICS_ANALYSIS: "metrics_analysis",
    TaskType.VECTOR_SEARCH: "vector_search",
    TaskType.SQL_QUERY: "sql_query",
    TaskType.WEB_SEARCH: "web_search",
    TaskType.KNOWLEDGE_GRAPH: "knowledge_graph",
}


def route_to_evidence_tasks(state: IncidentState) -> list[Send]:
    plan = state.get("plan")
    if plan is None or not plan.tasks:
        # Defensive fallback: an empty/missing plan (Planner failure, or a
        # plan the Reflection guidance somehow emptied) must not dead-end
        # the graph with zero evidence -- log analysis is relevant to
        # almost every incident category, so run it rather than proceeding
        # straight to Root Cause Analysis with nothing to reason over.
        return [Send("log_analysis", {"current_task": None})]
    return [Send(NODE_NAME_BY_TASK_TYPE[task.task_type], {"current_task": task}) for task in plan.tasks]
