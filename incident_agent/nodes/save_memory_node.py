"""Save Memory node.

Builds a complete, correctly-shaped `PastIncidentRecord` from this run's
results -- real, finished logic, not a stub -- and stashes it in
`state["metadata"]["memory_record_pending_persist"]`. The one thing this
node does *not* yet do is the actual write to a persistent store, because
that store (`memory/`, Chroma- and SQLite-backed) doesn't exist until
Phase 6. Once it does, this node's `work()` gains one line calling the
memory service; the record-building logic here does not change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from incident_agent.graphs.state import IncidentState
from incident_agent.models.enums import IncidentCategory
from incident_agent.models.memory import PastIncidentRecord
from incident_agent.nodes.node_runner import run_node


def save_memory_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        root_cause = state.get("metadata", {}).get("root_cause_analysis") or {}
        incident_report = state.get("metadata", {}).get("incident_report") or {}
        draft_answer = state.get("draft_answer")
        intent = state.get("intent")

        record = PastIncidentRecord(
            incident_id=state["incident_id"],
            title=incident_report.get("title") or state["user_query"][:80],
            category=intent.category if intent else IncidentCategory.UNKNOWN,
            root_cause=root_cause.get("root_cause", "(unknown)"),
            resolution_summary=incident_report.get("resolution_summary")
            or (draft_answer.summary if draft_answer else "(not resolved)"),
            resolved_at=datetime.now(timezone.utc),
        )

        updates: dict[str, Any] = {"metadata": {"memory_record_pending_persist": record.model_dump(mode="json")}}
        return updates, f"prepared memory record for {state['incident_id']} (persistence lands in Phase 6)"

    return run_node("save_memory", work)
