"""Merge Results node -- the fan-in point after the evidence-gathering
subgraph completes.

The actual *merging* of parallel branch output already happened via
`IncidentState`'s reducers (Phase 2) by the time this node runs -- what
this node adds is computing the combined evidence text *once* and caching
it in `state["metadata"]["evidence_bundle"]`, so Root Cause Analysis,
Validator, and Critic each read it rather than each re-deriving the same
text from raw logs/metrics/documents/sql results independently.
"""

from __future__ import annotations

from typing import Any

from incident_agent.graphs.state import IncidentState
from incident_agent.nodes.formatting import build_evidence_bundle
from incident_agent.nodes.node_runner import run_node


def merge_results_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        bundle = build_evidence_bundle(
            logs=state.get("logs", []),
            metrics=state.get("metrics", []),
            documents=state.get("retrieved_documents", []),
            sql_results=state.get("sql_results", []),
            reasoning=state.get("reasoning", []),
        )
        updates: dict[str, Any] = {"metadata": {"evidence_bundle": bundle}}
        counts = (
            f"{len(state.get('logs', []))} log(s), {len(state.get('metrics', []))} metric(s), "
            f"{len(state.get('retrieved_documents', []))} document(s), {len(state.get('sql_results', []))} "
            f"SQL result(s)"
        )
        return updates, f"consolidated evidence: {counts}"

    return run_node("merge_results", work)
