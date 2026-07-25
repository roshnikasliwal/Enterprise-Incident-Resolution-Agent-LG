"""The top-level incident-resolution `StateGraph`.

Wires together every node/subgraph/edge built across Phases 5-6 into the
workflow from `requirements.md`:

    recall_memory -> intent_detection -> planner
        -> evidence_gathering (subgraph, Send fan-out)
        -> merge_results -> root_cause_analysis -> incident_resolution
        -> validator -> critic
        -> [confidence_check] -> reflection -> planner   (retry cycle)
                               -> human_approval (interrupt + Command)
                                   -> report_generator -> save_memory -> final_response
                                   -> final_response                      (rejected path)

A graph itself contains no business logic -- every node/edge referenced
here was built and independently tested in isolation earlier in this
phase; this module only composes them.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from incident_agent.edges.confidence_check import route_after_confidence_check
from incident_agent.edges.reflection_routing import route_after_reflection
from incident_agent.graphs.evidence_subgraph import invoke_evidence_subgraph
from incident_agent.graphs.state import IncidentState
from incident_agent.nodes.critic_node import critic_node
from incident_agent.nodes.final_response_node import final_response_node
from incident_agent.nodes.human_approval_node import human_approval_node
from incident_agent.nodes.incident_resolution_node import incident_resolution_node
from incident_agent.nodes.intent_detection_node import intent_detection_node
from incident_agent.nodes.merge_results_node import merge_results_node
from incident_agent.nodes.planner_node import planner_node
from incident_agent.nodes.recall_memory_node import recall_memory_node
from incident_agent.nodes.reflection_node import reflection_node
from incident_agent.nodes.report_generator_node import report_generator_node
from incident_agent.nodes.root_cause_node import root_cause_node
from incident_agent.nodes.save_memory_node import save_memory_node
from incident_agent.nodes.validator_node import validator_node


def build_incident_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """Build and compile the main incident-resolution graph.

    `checkpointer` defaults to an in-memory saver so the graph is fully
    runnable (including `interrupt()`/resume) with zero setup -- this is
    what every test in this project uses. Production callers pass
    `checkpointer=services.checkpointer.get_checkpointer()` for durable
    SQLite-backed persistence across process restarts (see
    `tests/test_phase7_checkpointing.py`); the graph topology itself
    never changes based on which checkpointer is supplied.
    """
    builder = StateGraph(IncidentState)

    builder.add_node("recall_memory", recall_memory_node)
    builder.add_node("intent_detection", intent_detection_node)
    builder.add_node("planner", planner_node)
    builder.add_node("evidence_gathering", invoke_evidence_subgraph)
    builder.add_node("merge_results", merge_results_node)
    builder.add_node("root_cause_analysis", root_cause_node)
    builder.add_node("incident_resolution", incident_resolution_node)
    builder.add_node("validator", validator_node)
    builder.add_node("critic", critic_node)
    builder.add_node("reflection", reflection_node)
    builder.add_node("human_approval", human_approval_node, destinations=("report_generator", "final_response"))
    builder.add_node("report_generator", report_generator_node)
    builder.add_node("save_memory", save_memory_node)
    builder.add_node("final_response", final_response_node)

    builder.add_edge(START, "recall_memory")
    builder.add_edge("recall_memory", "intent_detection")
    builder.add_edge("intent_detection", "planner")
    builder.add_edge("planner", "evidence_gathering")
    builder.add_edge("evidence_gathering", "merge_results")
    builder.add_edge("merge_results", "root_cause_analysis")
    builder.add_edge("root_cause_analysis", "incident_resolution")
    builder.add_edge("incident_resolution", "validator")
    builder.add_edge("validator", "critic")

    # The retry cycle: confidence too low / critic rejects -> reflection ->
    # (loop back to planner, or give up and ask a human) -> ... -> critic again.
    builder.add_conditional_edges("critic", route_after_confidence_check, ["reflection", "human_approval"])
    builder.add_conditional_edges("reflection", route_after_reflection, ["planner", "human_approval"])

    # human_approval routes to "report_generator" or "final_response" dynamically
    # via Command(goto=...) after interrupt() resumes -- no static edge here.
    builder.add_edge("report_generator", "save_memory")
    builder.add_edge("save_memory", "final_response")
    builder.add_edge("final_response", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())
