"""`run_node()` -- the uniform timing/audit-trail/error-handling wrapper
every node function in this package is built on.

Mirrors `tools/base.run_structured()` one layer up: where that function
guarantees every *tool* call returns a structured result instead of a
bare exception, this one guarantees every *node* call contributes an
`ExecutionHistoryEntry` and never lets an exception escape to crash the
whole graph run. A single failed evidence-gathering branch (say, the SQL
Agent's LLM call fails after retries/fallbacks are exhausted) becomes an
`AgentError` appended to state instead of aborting Log Analysis, Metrics,
and every other branch that was running in parallel with it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from incident_agent.config.logging_config import get_logger
from incident_agent.models.enums import TaskStatus
from incident_agent.models.execution import AgentError, ExecutionHistoryEntry

logger = get_logger(__name__)

NodeWork = Callable[[], tuple[dict[str, Any], str]]
"""A node's core logic: takes no arguments (close over `state` in the caller),
returns `(state_updates, human_readable_summary)`."""


def run_node(node_name: str, work: NodeWork) -> dict[str, Any]:
    """Execute `work`, appending an `ExecutionHistoryEntry` on success and
    converting any exception into an `AgentError` + a FAILED history entry
    on failure -- in both cases returning a plain `dict` safe to hand back
    to LangGraph as the node's state update.
    """
    started_at = datetime.now(timezone.utc)
    logger.info("node_started", extra={"node_name": node_name})
    try:
        updates, summary = work()
    except Exception as exc:  # noqa: BLE001 -- the whole point: never let this escape the node
        completed_at = datetime.now(timezone.utc)
        logger.error(
            "node_failed",
            extra={
                "node_name": node_name,
                "error": str(exc),
                "duration_ms": round((completed_at - started_at).total_seconds() * 1000, 1),
            },
        )
        return {
            "errors": [AgentError(node_name=node_name, error_type=type(exc).__name__, message=str(exc))],
            "execution_history": [
                ExecutionHistoryEntry(
                    node_name=node_name,
                    status=TaskStatus.FAILED,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=(completed_at - started_at).total_seconds() * 1000,
                    summary=f"failed: {exc}",
                )
            ],
        }

    completed_at = datetime.now(timezone.utc)
    duration_ms = (completed_at - started_at).total_seconds() * 1000
    history_entry = ExecutionHistoryEntry(
        node_name=node_name,
        status=TaskStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        summary=summary,
    )
    logger.info(
        "node_completed",
        extra={"node_name": node_name, "duration_ms": round(duration_ms, 1), "summary": summary},
    )
    merged = dict(updates)
    merged["execution_history"] = [*merged.get("execution_history", []), history_entry]
    return merged
