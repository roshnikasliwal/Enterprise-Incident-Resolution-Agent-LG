"""`IncidentController` -- the seam between transport (FastAPI/Streamlit,
Phase 9) and the compiled graph.

Owns no business logic of its own: every method is a thin, named wrapper
around a specific `graph.invoke`/`get_state`/`update_state` call, so
callers get a stable, documented API (`approve`, `reject`, `edit_plan_
and_retry`, ...) instead of needing to know LangGraph's `Command`/
`interrupt` mechanics directly. This is what lets `api/` stay a pure
HTTP-shape concern -- it calls `IncidentController.approve(thread_id,
...)`, not `graph.invoke(Command(resume=...), config)`.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, StateSnapshot

from incident_agent.graphs.state import create_initial_state
from incident_agent.models.enums import ApprovalStatus
from incident_agent.schemas.human import HumanFeedback
from incident_agent.schemas.planning import ExecutionPlan
from incident_agent.schemas.resolution import DraftAnswer


class IncidentNotFoundError(LookupError):
    """Raised when `thread_id` has no checkpointed state at all."""


class IncidentController:
    def __init__(self, graph: CompiledStateGraph) -> None:
        self._graph = graph

    # --- Starting a new investigation -------------------------------------

    def start_investigation(
        self,
        user_query: str,
        *,
        session_id: str | None = None,
        incident_id: str | None = None,
    ) -> dict[str, Any]:
        """Kick off a fresh graph run; returns the state at whatever point it
        first pauses (or completes, if nothing interrupts it)."""
        state = create_initial_state(user_query, session_id=session_id, incident_id=incident_id)
        return self._graph.invoke(state, self._config(state["thread_id"]))

    # --- Inspecting a run ----------------------------------------------------

    def get_status(self, thread_id: str) -> dict[str, Any]:
        snapshot = self.get_snapshot(thread_id)
        return dict(snapshot.values)

    def is_paused(self, thread_id: str) -> bool:
        """True if the run is currently interrupted (static or dynamic) and
        awaiting `resume()`/human input."""
        return len(self.get_snapshot(thread_id).next) > 0

    def get_snapshot(self, thread_id: str) -> StateSnapshot:
        """The full LangGraph state snapshot -- `.values` (state), `.next`
        (which node(s) will run next, empty if the run finished), and
        `.interrupts` (the dynamic `interrupt()` payload, if paused there).
        Exposed publicly for callers (the API layer) that need more than
        `get_status()`'s plain state dict.
        """
        snapshot = self._graph.get_state(self._config(thread_id))
        if not snapshot.values:
            raise IncidentNotFoundError(f"No checkpointed state found for thread_id '{thread_id}'.")
        return snapshot

    # --- Human-in-the-loop decisions (dynamic interrupt() gate) -----------

    def approve(self, thread_id: str, *, comments: str | None = None) -> dict[str, Any]:
        return self._resume_with_feedback(thread_id, HumanFeedback(decision=ApprovalStatus.APPROVED, comments=comments))

    def reject(self, thread_id: str, *, comments: str | None = None) -> dict[str, Any]:
        return self._resume_with_feedback(thread_id, HumanFeedback(decision=ApprovalStatus.REJECTED, comments=comments))

    def modify_draft_answer(
        self, thread_id: str, draft_answer: DraftAnswer, *, comments: str | None = None
    ) -> dict[str, Any]:
        """Modify State: substitute a human-edited resolution for the
        agent's draft, then proceed to report generation as if approved."""
        feedback = HumanFeedback(
            decision=ApprovalStatus.MODIFIED, modified_draft_answer=draft_answer, comments=comments
        )
        return self._resume_with_feedback(thread_id, feedback)

    def edit_plan_and_retry(
        self, thread_id: str, plan: ExecutionPlan, *, comments: str | None = None
    ) -> dict[str, Any]:
        """Edit Plan / Retry / Skip Tool: replace the plan and re-run evidence
        gathering with it. Removing a task from `plan.tasks` before calling
        this is how a human "skips" that task's tool(s) -- there is no
        separate skip-tool primitive because the Planner already decides
        tool usage at the task-type granularity."""
        feedback = HumanFeedback(decision=ApprovalStatus.MODIFIED, modified_plan=plan, comments=comments)
        return self._resume_with_feedback(thread_id, feedback)

    # --- Direct state mutation (LangGraph's update_state) ------------------

    def update_state(self, thread_id: str, values: dict[str, Any]) -> None:
        """Modify State via LangGraph's `update_state`, independent of
        whatever the currently-interrupted node expects as a resume value --
        e.g. adjusting `confidence_score` or `metadata` while paused at a
        static `interrupt_before`/`interrupt_after` point (see
        `graphs.main_graph.build_incident_graph`'s `interrupt_before`/
        `interrupt_after` parameters), which take no resume payload at all.
        """
        self.get_snapshot(thread_id)  # raises IncidentNotFoundError if unknown
        self._graph.update_state(self._config(thread_id), values)

    # --- Resuming a statically-interrupted run -----------------------------

    def resume(self, thread_id: str) -> dict[str, Any]:
        """Continue a run paused by a *static* `interrupt_before`/
        `interrupt_after` point. No payload is passed -- unlike the dynamic
        `interrupt()` gate in `human_approval_node`, static interrupts don't
        carry a value to resume with; whatever state exists (optionally
        edited via `update_state()` first) is simply used as-is.
        """
        self.get_snapshot(thread_id)
        return self._graph.invoke(None, self._config(thread_id))

    # --- Internal helpers ----------------------------------------------------

    def _resume_with_feedback(self, thread_id: str, feedback: HumanFeedback) -> dict[str, Any]:
        # LangGraph's Command(resume=...) against a thread_id with no
        # checkpoint doesn't fail cleanly -- it attempts to run the graph
        # from scratch with whatever the resume value happens to satisfy,
        # which surfaces as a confusing KeyError deep inside whichever node
        # runs first rather than a clear "no such incident." Check first.
        self.get_snapshot(thread_id)
        return self._graph.invoke(Command(resume=feedback.model_dump(mode="json")), self._config(thread_id))

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}
