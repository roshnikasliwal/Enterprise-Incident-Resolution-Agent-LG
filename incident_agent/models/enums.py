"""Shared enums.

Centralized here (rather than duplicated per-schema) because the same
concepts -- severity, task status, approval status -- are referenced by
both `models/` (tool output shapes) and `schemas/` (LLM structured
output shapes). `models/` is the lower layer: `schemas/` may import from
here, never the reverse.
"""

from __future__ import annotations

from enum import StrEnum


class LogSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ToolStatus(StrEnum):
    """Outcome of a single tool invocation -- every tool in `tools/` returns
    a payload carrying one of these, never a bare exception."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    PARTIAL = "partial"


class IncidentCategory(StrEnum):
    """Coarse subsystem classification produced by the Intent Detection Agent;
    drives which evidence-gathering branches the Planner fans out to."""

    KUBERNETES = "kubernetes"
    KAFKA = "kafka"
    DATABASE = "database"
    CACHE = "cache"
    NETWORKING = "networking"
    APPLICATION = "application"
    UNKNOWN = "unknown"


class IncidentUrgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskType(StrEnum):
    """Identifies which evidence-gathering agent/branch a `PlanTask` targets."""

    LOG_ANALYSIS = "log_analysis"
    METRICS_ANALYSIS = "metrics_analysis"
    VECTOR_SEARCH = "vector_search"
    SQL_QUERY = "sql_query"
    WEB_SEARCH = "web_search"
    KNOWLEDGE_GRAPH = "knowledge_graph"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApprovalStatus(StrEnum):
    """Drives the Human-in-the-Loop conditional edge after `interrupt()`."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    AUTO_APPROVED = "auto_approved"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
