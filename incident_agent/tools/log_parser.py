"""Log Parser tool -- normalizes raw, unstructured log text into `LogEntry` objects.

Handles three formats, tried in order per line: JSON lines (structured
logging), a common `TIMESTAMP LEVEL message` prefix (syslog-like), and a
bare-text fallback (typical of `kubectl logs` on an app that doesn't log
structured JSON) where severity is inferred from keywords and the
timestamp defaults to "now" since none is present in the line itself.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from langchain_core.tools import tool

from incident_agent.models.enums import LogSeverity
from incident_agent.models.tool_results import LogEntry
from incident_agent.tools.base import run_structured

_PREFIXED_LINE = re.compile(
    r"^(?P<timestamp>\S+)\s+(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b[:\s\[\]]*(?P<message>.*)$",
    re.IGNORECASE,
)
_LEVEL_ALIASES = {
    "WARN": LogSeverity.WARNING,
    "WARNING": LogSeverity.WARNING,
    "FATAL": LogSeverity.CRITICAL,
    "CRITICAL": LogSeverity.CRITICAL,
    "ERROR": LogSeverity.ERROR,
    "INFO": LogSeverity.INFO,
    "DEBUG": LogSeverity.DEBUG,
}
_SEVERITY_KEYWORDS = (
    (re.compile(r"\b(panic|fatal|critical)\b", re.IGNORECASE), LogSeverity.CRITICAL),
    (re.compile(r"\b(error|exception|traceback|failed|refused)\b", re.IGNORECASE), LogSeverity.ERROR),
    (re.compile(r"\b(warn|warning|deprecated|retry(?:ing)?)\b", re.IGNORECASE), LogSeverity.WARNING),
    (re.compile(r"\bdebug\b", re.IGNORECASE), LogSeverity.DEBUG),
)


def _parse_timestamp(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _infer_severity(line: str) -> LogSeverity:
    for pattern, severity in _SEVERITY_KEYWORDS:
        if pattern.search(line):
            return severity
    return LogSeverity.INFO


def _parse_line(line: str, source: str) -> LogEntry | None:
    stripped = line.strip()
    if not stripped:
        return None

    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            level = str(payload.get("level") or payload.get("severity") or "info").upper()
            return LogEntry(
                timestamp=_parse_timestamp(str(payload.get("timestamp") or payload.get("ts") or "")),
                source=str(payload.get("source") or source),
                severity=_LEVEL_ALIASES.get(level, LogSeverity.INFO),
                message=str(payload.get("message") or payload.get("msg") or stripped),
                labels={k: str(v) for k, v in payload.items() if k not in {"level", "severity", "timestamp", "ts", "message", "msg", "source"}},
            )

    prefixed = _PREFIXED_LINE.match(stripped)
    if prefixed:
        return LogEntry(
            timestamp=_parse_timestamp(prefixed.group("timestamp")),
            source=source,
            severity=_LEVEL_ALIASES.get(prefixed.group("level").upper(), LogSeverity.INFO),
            message=prefixed.group("message").strip(),
        )

    return LogEntry(
        timestamp=datetime.now(timezone.utc),
        source=source,
        severity=_infer_severity(stripped),
        message=stripped,
    )


def _parse(raw_text: str, source: str) -> dict:
    entries = [entry for line in raw_text.splitlines() if (entry := _parse_line(line, source)) is not None]
    severity_counts: dict[str, int] = {}
    for entry in entries:
        severity_counts[entry.severity.value] = severity_counts.get(entry.severity.value, 0) + 1
    return {
        "entry_count": len(entries),
        "severity_counts": severity_counts,
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }


@tool
def log_parser(raw_text: str, source: str = "unknown") -> str:
    """Parse raw, unstructured log text (JSON lines, 'TIMESTAMP LEVEL message'
    lines, or bare text) into normalized, severity-tagged log entries.
    `source` labels every parsed entry (e.g. a pod or file name) when the
    log lines themselves don't carry that information.
    """
    return run_structured("log_parser", lambda: _parse(raw_text, source))
