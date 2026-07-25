"""Save Memory node -- runs after human approval + report generation.

Builds a complete `PastIncidentRecord` from this run's results and
persists it via `MemoryService`: into episodic memory (semantic recall
for future similar incidents), the frequent-fixes counter (if the
resolution was actually approved/applied), and the session's rolling
conversation summary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from incident_agent.graphs.state import IncidentState
from incident_agent.memory.memory_service import get_memory_service
from incident_agent.models.enums import ApprovalStatus, IncidentCategory
from incident_agent.models.memory import PastIncidentRecord
from incident_agent.nodes.node_runner import run_node

_APPLIED_STATUSES = (ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED, ApprovalStatus.MODIFIED)


def _build_record(state: IncidentState) -> PastIncidentRecord:
    root_cause = state.get("metadata", {}).get("root_cause_analysis") or {}
    incident_report = state.get("metadata", {}).get("incident_report") or {}
    draft_answer = state.get("draft_answer")
    intent = state.get("intent")

    return PastIncidentRecord(
        incident_id=state["incident_id"],
        title=incident_report.get("title") or state["user_query"][:80],
        category=intent.category if intent else IncidentCategory.UNKNOWN,
        root_cause=root_cause.get("root_cause", "(unknown)"),
        resolution_summary=incident_report.get("resolution_summary")
        or (draft_answer.summary if draft_answer else "(not resolved)"),
        resolved_at=datetime.now(timezone.utc),
    )


def save_memory_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        record = _build_record(state)
        service = get_memory_service()

        service.persist_incident(record)
        service.update_conversation(
            session_id=state["session_id"],
            incident_id=state["incident_id"],
            user_query=state["user_query"],
            resolution_summary=record.resolution_summary,
        )

        draft_answer = state.get("draft_answer")
        applied = state.get("approval_status") in _APPLIED_STATUSES
        if applied and draft_answer is not None:
            service.record_fix_usage(record.category, draft_answer.summary)

        updates: dict[str, Any] = {
            "metadata": {
                "memory_persisted": True,
                "episodic_incident_id": record.incident_id,
            }
        }
        return updates, f"persisted memory for {state['incident_id']} (episodic{', fix usage,' if applied else ','} conversation)"

    return run_node("save_memory", work)
