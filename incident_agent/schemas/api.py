"""FastAPI request/response contracts.

Kept separate from the LLM structured-output schemas (`schemas/intent.py`
etc.) even though both live under `schemas/` -- these describe HTTP
payload shapes, not what an agent's `with_structured_output` call
produces. `IncidentStatusResponse` is deliberately a flattened, API-
friendly projection of `IncidentState`, not the raw state dict: clients
shouldn't need to know about `metadata["root_cause_analysis"]` living
there because `IncidentState` has no dedicated field for it (see
`nodes/formatting.py`'s comments) -- that's an internal implementation
detail this layer hides.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from incident_agent.models.enums import ApprovalStatus
from incident_agent.schemas.final import FinalAnswer
from incident_agent.schemas.planning import ExecutionPlan
from incident_agent.schemas.resolution import DraftAnswer


class IncidentRequest(BaseModel):
    user_query: str = Field(min_length=1, description="The user's description of the problem.")
    session_id: str | None = Field(default=None, description="Groups multiple incidents under one user session.")


class ApproveRequest(BaseModel):
    comments: str | None = None
    modified_draft_answer: DraftAnswer | None = Field(
        default=None, description="Modify State: substitute this for the agent's draft before proceeding."
    )
    modified_plan: ExecutionPlan | None = Field(
        default=None, description="Edit Plan / Retry / Skip Tool: re-run evidence gathering with this plan instead."
    )


class RejectRequest(BaseModel):
    comments: str | None = None


class ResumeRequest(BaseModel):
    """No fields today -- resuming a *static* interrupt_before/after pause
    takes no payload (see `IncidentController.resume`). Kept as a model
    (not an empty POST) so the endpoint can grow fields without a
    breaking change."""


class IncidentStatusResponse(BaseModel):
    thread_id: str
    session_id: str
    incident_id: str
    user_query: str
    approval_status: ApprovalStatus
    is_paused: bool
    awaiting_node: str | None = Field(default=None, description="The node the graph is currently paused before/at, if any.")
    confidence_score: float
    retry_count: int
    error_count: int
    final_answer: FinalAnswer | None = None
    interrupt_payload: dict[str, Any] | None = Field(
        default=None, description="The payload from human_approval_node's interrupt(), when paused there."
    )


class HistoryItem(BaseModel):
    thread_id: str
    incident_id: str
    created_at: datetime
    approval_status: ApprovalStatus | None = None
    user_query: str | None = None


class HistoryResponse(BaseModel):
    session_id: str
    incidents: list[HistoryItem]


class ErrorResponse(BaseModel):
    detail: str
