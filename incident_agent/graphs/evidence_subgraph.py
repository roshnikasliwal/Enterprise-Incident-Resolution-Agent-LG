"""The evidence-gathering subgraph -- a self-contained, independently
compiled and testable `StateGraph` invoked from a single node in the main
graph (`graphs/main_graph.py`).

Why a subgraph here specifically: "gather evidence in parallel" is a
coherent unit of work with its own internal fan-out/fan-in (via the Send
API, see `edges/evidence_routing.py`) that has nothing to do with the
surrounding plan/replan/approve orchestration. Compiling it separately
means it can be built, visualized, and tested (`tests/test_phase5_graph.py`)
in complete isolation from the rest of the workflow.

Why `invoke_evidence_subgraph()` exists instead of embedding
`EVIDENCE_SUBGRAPH` directly via `parent_builder.add_node("evidence_gathering",
EVIDENCE_SUBGRAPH)`
-------------------------------------------------------------------------
LangGraph's "subgraph shares the parent's exact schema" shortcut passes
the subgraph the *full current parent state* as input and treats its
*full final state* as that node's return value, which the parent then
merges through its own reducers -- on top of a state that already
contains what the subgraph received. For any accumulating field
(`Annotated[list, operator.add]`, e.g. `execution_history`, `reasoning`)
that already has entries before the subgraph runs, this double-counts
those pre-existing entries once the subgraph's output flows back through
the parent's reducer. This is a documented LangGraph behavior, not a bug
in this codebase -- see langchain-ai/langgraph#6290 -- confirmed here by
instrumenting a node to prove it executes exactly once even though its
write ends up applied twice.

`invoke_evidence_subgraph()` sidesteps it by handing the subgraph a copy
of state with every accumulating field reset to empty, invoking it
directly (bypassing the parent's own reducer for that call), and
returning *only* what the subgraph itself produced -- which the parent's
reducer then correctly appends to (not duplicates against) its own
existing values.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from incident_agent.edges.evidence_routing import NODE_NAME_BY_TASK_TYPE, route_to_evidence_tasks
from incident_agent.graphs.state import IncidentState
from incident_agent.nodes.knowledge_graph_node import knowledge_graph_node
from incident_agent.nodes.log_analysis_node import log_analysis_node
from incident_agent.nodes.metrics_analysis_node import metrics_analysis_node
from incident_agent.nodes.sql_query_node import sql_query_node
from incident_agent.nodes.vector_search_node import vector_search_node
from incident_agent.nodes.web_search_node import web_search_node

# Every field the evidence-gathering nodes can possibly write to -- all of
# them are `Annotated[list, operator.add]` accumulators in `IncidentState`.
# Kept as an explicit list (not derived reflectively) so it's obvious at a
# glance exactly what this workaround resets/extracts.
_ACCUMULATOR_FIELDS: tuple[str, ...] = (
    "retrieved_documents",
    "tool_results",
    "logs",
    "metrics",
    "sql_results",
    "reasoning",
    "execution_history",
    "citations",
    "errors",
)

_EVIDENCE_NODE_FUNCTIONS = {
    "log_analysis": log_analysis_node,
    "metrics_analysis": metrics_analysis_node,
    "vector_search": vector_search_node,
    "sql_query": sql_query_node,
    "web_search": web_search_node,
    "knowledge_graph": knowledge_graph_node,
}


def build_evidence_subgraph() -> CompiledStateGraph:
    """Build and compile the evidence-gathering subgraph.

    Exposed as a function (not only the `EVIDENCE_SUBGRAPH` singleton below)
    so tests can build a fresh, independent instance when isolation matters.
    """
    assert set(_EVIDENCE_NODE_FUNCTIONS) == set(NODE_NAME_BY_TASK_TYPE.values())

    builder = StateGraph(IncidentState)
    for name, node_fn in _EVIDENCE_NODE_FUNCTIONS.items():
        builder.add_node(name, node_fn)
        builder.add_edge(name, END)
    builder.add_conditional_edges(START, route_to_evidence_tasks, list(_EVIDENCE_NODE_FUNCTIONS))
    return builder.compile()


EVIDENCE_SUBGRAPH: CompiledStateGraph = build_evidence_subgraph()


def invoke_evidence_subgraph(state: IncidentState) -> dict[str, Any]:
    """Parent-graph node function that safely invokes `EVIDENCE_SUBGRAPH`.

    See the module docstring for why this wrapper exists rather than
    embedding `EVIDENCE_SUBGRAPH` directly as a node.
    """
    subgraph_input: dict[str, Any] = {**state, **{field: [] for field in _ACCUMULATOR_FIELDS}}
    result = EVIDENCE_SUBGRAPH.invoke(subgraph_input)  # type: ignore[arg-type]
    return {field: result[field] for field in _ACCUMULATOR_FIELDS if result.get(field)}
