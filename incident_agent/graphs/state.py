"""The LangGraph working state: `IncidentState`.

Why `TypedDict` and not a Pydantic `BaseModel`
-----------------------------------------------
LangGraph supports both as a graph's state schema. We chose `TypedDict`
for three concrete reasons:

1. **Reducers.** Concurrent, per-key merge semantics (`Annotated[list[X],
   operator.add]`) are the documented, first-class way LangGraph resolves
   parallel writes from the fan-out evidence-gathering branch. Pydantic
   state support relies on the same `Annotated` mechanism, so there's no
   win there -- but...
2. **Per-step validation cost.** A Pydantic state re-validates the
   *entire* model on every node's partial update. With five parallel
   evidence-gathering nodes plus retry cycles, that's a lot of redundant
   validation of fields a given node never touched. `TypedDict` has zero
   runtime overhead; the actual validation work happens once, at the
   leaves, where every field is already a Pydantic model in its own
   right (`IntentClassification`, `ExecutionPlan`, `ToolResult`, ...).
3. **"Every LLM response uses Pydantic models" is satisfied at the field
   level**, not the container level -- each state value that comes from
   an LLM call *is* a validated Pydantic object. The container just
   needs to move those objects around efficiently.

Reducer summary
----------------
Fields that accumulate contributions across many node executions (most
notably the parallel evidence-gathering fan-out: Log Analysis, Metrics,
Vector Search, SQL, Web Search all writing in the same super-step) are
annotated with a reducer so later writes *add to* rather than *replace*
earlier ones. Every other field is a "current snapshot" -- exactly one
node sets it at a time -- and uses LangGraph's default last-write-wins
behavior.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from incident_agent.models.documents import Citation, RetrievedDocument
from incident_agent.models.enums import ApprovalStatus
from incident_agent.models.execution import AgentError, ExecutionHistoryEntry, ReasoningStep
from incident_agent.models.memory import MemoryContext
from incident_agent.models.tool_results import LogEntry, MetricSample, SQLQueryResult, ToolResult
from incident_agent.schemas.critique import CriticFeedback, ValidationResult
from incident_agent.schemas.final import FinalAnswer
from incident_agent.schemas.human import HumanFeedback
from incident_agent.schemas.intent import IntentClassification
from incident_agent.schemas.planning import ExecutionPlan, PlanTask
from incident_agent.schemas.resolution import DraftAnswer
from incident_agent.utils.ids import generate_incident_id, generate_session_id, generate_thread_id
from incident_agent.utils.reducers import merge_dicts


class IncidentState(TypedDict):
    # --- Identity -----------------------------------------------------
    thread_id: str
    """LangGraph checkpointer thread -- the unit of persistence/resumption."""
    session_id: str
    """Groups multiple threads belonging to one user conversation."""
    incident_id: str
    """Durable `Incident` record this run investigates."""

    # --- Input ----------------------------------------------------------
    user_query: str

    # --- Understanding & planning ---------------------------------------
    intent: IntentClassification | None
    plan: ExecutionPlan | None
    current_task: PlanTask | None
    """The task a given evidence-gathering node instance is executing -- set
    per-branch via the Send API, not shared across the parallel fan-out."""

    # --- Evidence (accumulates across the parallel fan-out) -------------
    retrieved_documents: Annotated[list[RetrievedDocument], operator.add]
    tool_results: Annotated[list[ToolResult], operator.add]
    logs: Annotated[list[LogEntry], operator.add]
    metrics: Annotated[list[MetricSample], operator.add]
    sql_results: Annotated[list[SQLQueryResult], operator.add]

    # --- Reasoning trace (streamed to the UI) ----------------------------
    reasoning: Annotated[list[ReasoningStep], operator.add]

    # --- Answer lifecycle -------------------------------------------------
    draft_answer: DraftAnswer | None
    validated_answer: ValidationResult | None
    critic_feedback: CriticFeedback | None
    human_feedback: HumanFeedback | None
    approval_status: ApprovalStatus

    # --- Audit trail & control flow ---------------------------------------
    execution_history: Annotated[list[ExecutionHistoryEntry], operator.add]
    retry_count: int
    confidence_score: float

    # --- Memory & citations -------------------------------------------------
    memory: MemoryContext | None
    citations: Annotated[list[Citation], operator.add]

    # --- Errors & free-form metadata -----------------------------------------
    errors: Annotated[list[AgentError], operator.add]
    metadata: Annotated[dict[str, Any], merge_dicts]

    # --- Output -----------------------------------------------------------
    final_answer: FinalAnswer | None


def create_initial_state(
    user_query: str,
    *,
    thread_id: str | None = None,
    session_id: str | None = None,
    incident_id: str | None = None,
) -> IncidentState:
    """Factory for a fresh `IncidentState` -- the only place default values
    for every field are decided, so a node can never accidentally observe a
    missing key (and controllers/tests never hand-roll a state dict).
    """
    return IncidentState(
        thread_id=thread_id or generate_thread_id(),
        session_id=session_id or generate_session_id(),
        incident_id=incident_id or generate_incident_id(),
        user_query=user_query,
        intent=None,
        plan=None,
        current_task=None,
        retrieved_documents=[],
        tool_results=[],
        logs=[],
        metrics=[],
        sql_results=[],
        reasoning=[],
        draft_answer=None,
        validated_answer=None,
        critic_feedback=None,
        human_feedback=None,
        approval_status=ApprovalStatus.PENDING,
        execution_history=[],
        retry_count=0,
        confidence_score=0.0,
        memory=None,
        citations=[],
        errors=[],
        metadata={},
        final_answer=None,
    )
