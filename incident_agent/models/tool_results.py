"""Tool output domain models.

`ToolResult` is the single envelope every tool in `tools/` must return
(see `tools/base.py` in Phase 3) -- this is what "each tool returns
structured JSON" means concretely: never a raw string, never a bare
exception bubbling out of a node. `LogEntry`, `MetricSample`, and
`SQLQueryResult` are the normalized payload shapes for the three tool
families whose raw output benefits from a typed structure (as opposed to
e.g. the Kubernetes/Kafka/Redis mock tools, whose payloads are
tool-specific dicts carried in `ToolResult.data`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from incident_agent.models.enums import LogSeverity, ToolStatus


class ToolResult(BaseModel):
    """Uniform envelope returned by every LangChain tool in this project."""

    tool_name: str
    status: ToolStatus
    data: Any = Field(default=None, description="Tool-specific structured payload.")
    error_message: str | None = None
    latency_ms: float = Field(ge=0.0)
    invoked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status in (ToolStatus.SUCCESS, ToolStatus.PARTIAL)


class LogEntry(BaseModel):
    """One normalized log line, regardless of which system emitted it."""

    timestamp: datetime
    source: str = Field(description="Emitting pod/service/container name.")
    severity: LogSeverity
    message: str
    labels: dict[str, str] = Field(default_factory=dict)


class MetricSample(BaseModel):
    """One normalized metric observation (CPU, memory, latency, consumer lag, ...)."""

    metric_name: str
    value: float
    unit: str
    timestamp: datetime
    labels: dict[str, str] = Field(default_factory=dict)
    is_anomalous: bool = False
    threshold: float | None = None


class SQLQueryResult(BaseModel):
    """Normalized result of a single SQL query execution."""

    query: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    execution_time_ms: float = Field(ge=0.0)
    truncated: bool = False
