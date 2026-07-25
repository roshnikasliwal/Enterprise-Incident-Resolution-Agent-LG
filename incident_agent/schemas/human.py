"""Human-in-the-loop decision schema.

Not LLM-produced -- populated by `controllers/` from a human reviewer's
API payload (`POST /approve`, `POST /reject`, `POST /resume`) -- but
standardized as a Pydantic schema for the same reason every other
decision point in this graph is: "no raw text parsing" applies to human
input as much as to LLM output, and the conditional edge after
`interrupt()` needs a typed `decision` field to route on.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from incident_agent.models.enums import ApprovalStatus
from incident_agent.schemas.planning import ExecutionPlan
from incident_agent.schemas.resolution import DraftAnswer


class ApprovalRequestSummary(BaseModel):
    """Human Approval Agent structured output.

    Unlike every other agent, this one does not advance the investigation --
    it prepares the *human-facing brief* shown at the `interrupt()` gate so
    a reviewer can decide in seconds rather than re-reading the full
    execution history themselves.
    """

    headline: str = Field(description="One sentence: what is being proposed and why.")
    key_points: list[str] = Field(default_factory=list, description="The 3-5 facts a reviewer most needs to know.")
    risk_callouts: list[str] = Field(
        default_factory=list, description="Anything irreversible, high-blast-radius, or unusually risky."
    )
    recommended_action: Literal["approve", "reject", "modify"] = Field(
        description="This agent's own recommendation -- the human is never bound by it."
    )


class HumanFeedback(BaseModel):
    decision: ApprovalStatus
    comments: str | None = None
    modified_plan: ExecutionPlan | None = Field(
        default=None, description="Set when decision == MODIFIED and the human edited the investigation plan."
    )
    modified_draft_answer: DraftAnswer | None = Field(
        default=None, description="Set when decision == MODIFIED and the human edited the proposed resolution."
    )
    reviewer: str | None = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
