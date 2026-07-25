"""Shared tool execution helper.

Every tool in this package funnels its real work through
`run_structured()` instead of hand-rolling try/except/timing in each of
the 13 tool files. This is what makes "every tool returns structured
JSON" and "tool failure recovery" true *uniformly*: a tool's inner
implementation function can raise freely (a bad pod name, an
unreachable host, a malformed SQL query) and the exception is caught
here, converted into a `ToolResult(status=ERROR, ...)`, and serialized --
never a bare traceback surfacing to the agent loop.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from incident_agent.config.logging_config import get_logger
from incident_agent.models.enums import ToolStatus
from incident_agent.models.tool_results import ToolResult

logger = get_logger(__name__)

T = TypeVar("T")


def run_structured(
    tool_name: str,
    implementation: Callable[[], T],
    *,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Execute `implementation`, time it, and return a `ToolResult` as JSON.

    Args:
        tool_name: Recorded on the result -- matches the LangChain tool's
            `.name`, so downstream nodes can attribute results correctly.
        implementation: A zero-argument callable (typically a lambda closing
            over the tool's actual arguments) doing the real work and
            returning a JSON-serializable payload, or a Pydantic model.
        metadata: Extra structured context to attach (e.g. request params),
            useful for LangSmith traces and debugging without polluting `data`.
    """
    started = time.perf_counter()
    data: Any = None
    status = ToolStatus.SUCCESS
    error_message: str | None = None
    try:
        result = implementation()
        data = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    except Exception as exc:  # noqa: BLE001 -- intentional: tools must never raise past this boundary
        status = ToolStatus.ERROR
        error_message = f"{type(exc).__name__}: {exc}"
        logger.warning("tool_execution_failed", extra={"tool_name": tool_name, "error": error_message})

    latency_ms = (time.perf_counter() - started) * 1000
    envelope = ToolResult(
        tool_name=tool_name,
        status=status,
        data=data,
        error_message=error_message,
        latency_ms=latency_ms,
        metadata=metadata or {},
    )
    return envelope.model_dump_json()
