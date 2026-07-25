"""ID generation helpers.

We favor short, prefixed, sortable-by-creation-time identifiers
(`INC-20260725-3f9a1c8e`) over raw UUIDs because they show up in logs,
LangSmith traces, and the Streamlit UI, where a human needs to eyeball
and correlate them. The prefix disambiguates ID *kind* at a glance
(incident vs. session vs. thread), which matters once all three appear
together in a support ticket.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _new_suffix() -> str:
    return uuid.uuid4().hex[:12]


def generate_incident_id(now: datetime | None = None) -> str:
    """`INC-YYYYMMDD-<12 hex chars>` -- one per user-reported incident."""
    now = now or datetime.now(timezone.utc)
    return f"INC-{now:%Y%m%d}-{_new_suffix()}"


def generate_session_id() -> str:
    """`SES-<12 hex chars>` -- one per user conversation session."""
    return f"SES-{_new_suffix()}"


def generate_thread_id() -> str:
    """`THR-<12 hex chars>` -- one per LangGraph checkpointer thread.

    Kept distinct from `session_id`: a single session can span multiple
    graph invocations/threads (e.g. a follow-up incident in the same
    chat), and a thread can outlive a session (resumed after interrupt).
    """
    return f"THR-{_new_suffix()}"


def generate_task_id() -> str:
    """`TSK-<8 hex chars>` -- one per plan task, kept short since these are
    referenced frequently within a single execution plan."""
    return f"TSK-{uuid.uuid4().hex[:8]}"
