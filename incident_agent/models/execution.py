"""Execution audit-trail models.

`ExecutionHistoryEntry` and `AgentError` accumulate in `IncidentState`
across the whole graph run (see `graphs.state`), giving the Report
Generator and the Streamlit UI a complete, replayable timeline of what
happened without needing to inspect checkpointer internals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from incident_agent.models.enums import TaskStatus
from incident_agent.utils.ids import generate_task_id


class ExecutionHistoryEntry(BaseModel):
    """One row in the incident's audit trail -- one per node execution."""

    entry_id: str = Field(default_factory=generate_task_id)
    node_name: str
    status: TaskStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0.0)
    summary: str = Field(description="One-line human-readable outcome, e.g. 'found 3 anomalous log clusters'.")
    details: dict[str, Any] = Field(default_factory=dict)


class ReasoningStep(BaseModel):
    """One entry in the running chain-of-thought trace surfaced to the UI.

    Deliberately separate from `ExecutionHistoryEntry` (which is an audit
    record of *what ran*): a `ReasoningStep` is *why* -- the agent's own
    stated justification, useful for node-level streaming (see the
    Streaming requirements) so a human watching the UI sees reasoning
    appear incrementally rather than only a final answer.
    """

    node_name: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentError(BaseModel):
    """A recoverable-or-not failure surfaced by a node/agent/tool.

    Distinct from raising a raw exception: nodes catch exceptions and
    convert them into an `AgentError` appended to state so a single tool
    failure degrades gracefully instead of aborting the whole graph run
    (see the error-handling requirements: retry, fallback, graceful
    errors).
    """

    error_id: str = Field(default_factory=generate_task_id)
    node_name: str
    error_type: str = Field(description="Exception class name or a domain error code.")
    message: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    retryable: bool = True
    retry_count: int = 0
