"""Final Response node -- the graph's last step before END.

Handles both outcomes of the human-approval gate: on rejection, there is
no incident report to summarize and no reason to spend an LLM call
explaining that (the rejection reason, if any, is already known from
`human_feedback.comments`), so that path is handled deterministically.
The approved/modified path calls the Final Response Agent normally.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.final_response import FinalResponseAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.enums import ApprovalStatus
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_draft_answer, format_root_cause, format_validation_result
from incident_agent.nodes.node_runner import run_node
from incident_agent.schemas.final import FinalAnswer


def _rejection_answer(state: IncidentState) -> FinalAnswer:
    feedback = state.get("human_feedback")
    comments = feedback.comments if feedback else None
    answer = (
        "The proposed resolution for this incident was reviewed by a human and was not approved."
        + (f" Reviewer comments: {comments}" if comments else "")
        + " No changes were applied. Please provide additional guidance or escalate this incident."
    )
    return FinalAnswer(answer=answer, confidence=state.get("confidence_score", 0.0), incident_report_id=None)


def final_response_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        if state.get("approval_status") == ApprovalStatus.REJECTED:
            result = _rejection_answer(state)
        else:
            agent = get_agent(FinalResponseAgent)
            incident_report = state.get("metadata", {}).get("incident_report") or {}
            result = agent.invoke(
                user_query=state["user_query"],
                draft_answer=format_draft_answer(state.get("draft_answer")),
                validated_answer=format_validation_result(state.get("validated_answer")),
                root_cause_analysis=format_root_cause(state.get("metadata", {}).get("root_cause_analysis")),
                incident_report=incident_report.get("executive_summary", "(no report generated)"),
            )
            if not result.incident_report_id:
                result = result.model_copy(update={"incident_report_id": state["incident_id"]})

        updates: dict[str, Any] = {"final_answer": result}
        return updates, "final answer produced"

    return run_node("final_response", work)
