"""Human Approval node -- the interrupt() gate, combined with the Command
API to route dynamically on the human's decision.

Deliberately does **not** use `nodes/node_runner.run_node()`. `interrupt()`
pauses the graph by raising `GraphInterrupt`, a subclass of `Exception`
that LangGraph's own executor must catch to implement the pause; wrapping
this node in `run_node()`'s blanket `except Exception` would swallow that
exception and silently break human-in-the-loop entirely instead of
pausing. Only the agent call preceding `interrupt()` gets narrow,
specific error handling -- a failure there degrades to a plain-text brief
rather than blocking the approval gate from being reached at all.

On resume, `Command(goto=..., update=...)` both applies the human's
decision to state *and* dynamically routes to the next node in one
return value -- the routing target genuinely depends on data only
available inside this node (the just-resumed `HumanFeedback`), which is
exactly the case `Command` exists for over a separate conditional edge.

Three distinct human decisions route three different ways, covering
Approve/Reject/Modify-State/Retry/Skip-Tool/Edit-Plan from requirements.md:

- `APPROVED`/`AUTO_APPROVED` -> `report_generator` (proceed as drafted).
- `MODIFIED` + `modified_draft_answer` -> `report_generator`, but with the
  human's edited resolution substituted for the agent's draft first
  ("Modify State").
- `MODIFIED` + `modified_plan` -> `evidence_gathering` directly (bypassing
  the Planner LLM call entirely, since the human's plan replaces it),
  with `retry_count` incremented. This is "Edit Plan" and "Retry" at
  once, and "Skip Tool" is just a special case of it: removing a task
  from the plan means its tool(s) never run.
- `REJECTED` -> `final_response` (a deterministic rejection message, no
  report generated).
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.types import Command, interrupt

from incident_agent.agents.base import AgentExecutionError
from incident_agent.agents.human_approval import HumanApprovalAgent
from incident_agent.config.logging_config import get_logger
from incident_agent.graphs.state import IncidentState
from incident_agent.models.enums import ApprovalStatus
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_draft_answer, format_root_cause, format_validation_result
from incident_agent.schemas.human import ApprovalRequestSummary, HumanFeedback

logger = get_logger(__name__)


def _build_approval_brief(state: IncidentState) -> ApprovalRequestSummary:
    try:
        agent = get_agent(HumanApprovalAgent)
        return agent.invoke(
            root_cause_analysis=format_root_cause(state.get("metadata", {}).get("root_cause_analysis")),
            draft_answer=format_draft_answer(state.get("draft_answer")),
            validated_answer=format_validation_result(state.get("validated_answer")),
            confidence_score=str(state.get("confidence_score", 0.0)),
        )
    except AgentExecutionError as exc:
        logger.warning("approval_brief_generation_failed", extra={"error": str(exc)})
        draft = state.get("draft_answer")
        return ApprovalRequestSummary(
            headline=f"Review required for incident {state['incident_id']} (brief generation failed)",
            key_points=[draft.summary] if draft else ["No draft resolution was produced."],
            risk_callouts=["Approval brief could not be generated automatically -- review raw state."],
            recommended_action="modify",
        )


def human_approval_node(
    state: IncidentState,
) -> Command[Literal["report_generator", "final_response", "evidence_gathering"]]:
    brief = _build_approval_brief(state)

    logger.info("human_approval_paused", extra={"incident_id": state["incident_id"]})
    raw_response = interrupt(
        {
            "kind": "approval_request",
            "incident_id": state["incident_id"],
            "brief": brief.model_dump(mode="json"),
        }
    )
    feedback = (
        raw_response if isinstance(raw_response, HumanFeedback) else HumanFeedback.model_validate(raw_response)
    )
    logger.info(
        "human_decision_received",
        extra={"incident_id": state["incident_id"], "decision": feedback.decision.value},
    )

    updates: dict[str, Any] = {
        "human_feedback": feedback,
        "approval_status": feedback.decision,
        "reasoning": [
            ReasoningStep(node_name="human_approval", content=f"Human decision: {feedback.decision.value}")
        ],
    }

    if feedback.decision == ApprovalStatus.MODIFIED and feedback.modified_plan is not None:
        # Edit Plan / Retry / Skip Tool: re-enter evidence gathering with the
        # human's plan, bypassing the Planner LLM call -- their plan *is*
        # the new plan, not a suggestion to re-derive one from.
        updates["plan"] = feedback.modified_plan
        updates["retry_count"] = state.get("retry_count", 0) + 1
        return Command(goto="evidence_gathering", update=updates)

    if feedback.decision == ApprovalStatus.MODIFIED and feedback.modified_draft_answer is not None:
        updates["draft_answer"] = feedback.modified_draft_answer

    proceeds_to_report = feedback.decision in (
        ApprovalStatus.APPROVED,
        ApprovalStatus.AUTO_APPROVED,
        ApprovalStatus.MODIFIED,
    )
    return Command(goto="report_generator" if proceeds_to_report else "final_response", update=updates)
