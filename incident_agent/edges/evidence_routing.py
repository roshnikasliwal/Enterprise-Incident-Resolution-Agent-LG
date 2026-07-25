"""Dynamic parallel dispatch for the evidence-gathering subgraph -- the
Send API in action.

A *static* parallel fan-out (`add_edge(START, [nodeA, nodeB, ...])`) can't
express "run only the branches the Planner actually decided are relevant"
-- the set of branches varies per incident. `Send` lets a single
conditional-edge function emit a *list* of dynamically-targeted tasks,
one per plan task, each carrying its own `current_task` payload. LangGraph
runs all of them in the same parallel super-step and waits for every one
to finish before the subgraph's downstream nodes see merged state.

Critical detail a `Send(node, payload)` payload is the **entire** input
state that node invocation receives -- it is not merged with whatever
else is in the graph's current state. A dispatched evidence node sees
only the keys explicitly included in its `Send` payload, nothing else.
This is why `_SHARED_CONTEXT` below forwards `user_query`/`intent`
alongside `current_task`: without it, `vector_search_node`'s
unconditional `state["user_query"]` access raises `KeyError` (caught,
verified with a Send-based repro), and `log_analysis_node`/
`metrics_analysis_node`/`knowledge_graph_node`'s `infer_target_name()`
silently degrades to always falling back to the default target instead
of using `intent.keywords`, since their `state.get("intent")` calls
would otherwise always return `None`.
"""

from __future__ import annotations

from typing import Any

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
    shared_context: dict[str, Any] = {"user_query": state["user_query"], "intent": state.get("intent")}

    plan = state.get("plan")
    if plan is None or not plan.tasks:
        # Defensive fallback: an empty/missing plan (Planner failure, or a
        # plan the Reflection guidance somehow emptied) must not dead-end
        # the graph with zero evidence -- log analysis is relevant to
        # almost every incident category, so run it rather than proceeding
        # straight to Root Cause Analysis with nothing to reason over.
        return [Send("log_analysis", {**shared_context, "current_task": None})]
    return [
        Send(NODE_NAME_BY_TASK_TYPE[task.task_type], {**shared_context, "current_task": task}) for task in plan.tasks
    ]
