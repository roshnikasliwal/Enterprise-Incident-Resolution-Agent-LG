"""Structured logging setup.

We deliberately avoid a third-party logging library: stdlib `logging`
already gives us handlers, levels, and propagation, and adding a
dependency (structlog, loguru) buys little for the amount of structured
data this project needs. Instead we plug a small JSON `Formatter` into
stdlib logging when `settings.log_json` is True (staging/production),
and a readable formatter otherwise (local dev).

`get_logger(__name__)` is the one function the rest of the codebase
should call -- it guarantees `configure_logging()` has run exactly once
per process before any logger is used.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from incident_agent.config.settings import Settings, get_settings

_configured_lock = threading.Lock()
_configured = False

# Attributes present on every stdlib LogRecord; anything else on a record
# was attached via `logger.info(..., extra={...})` and should be surfaced
# as structured fields in the JSON output.
_STANDARD_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__.keys())


class _JSONFormatter(logging.Formatter):
    """Renders each `LogRecord` as a single-line JSON object.

    Designed to be ingested by log aggregators (Datadog, CloudWatch,
    ELK) that expect one JSON document per line rather than
    multi-line/plaintext tracebacks.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_")
        }
        if extras:
            payload.update(extras)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _ConsoleFormatter(logging.Formatter):
    """Human-readable formatter used for local development."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def configure_logging(settings: Settings | None = None) -> None:
    """Idempotently attach a single stdout handler to the root logger.

    Safe to call multiple times (e.g. once from `api/app.py`, once from
    a Streamlit entrypoint, once in test fixtures) -- only the first call
    takes effect.
    """
    global _configured
    with _configured_lock:
        if _configured:
            return
        settings = settings or get_settings()

        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(_JSONFormatter() if settings.log_json else _ConsoleFormatter())

        root = logging.getLogger()
        root.setLevel(settings.log_level.upper())
        root.handlers.clear()
        root.addHandler(handler)

        # Noisy third-party loggers we don't want drowning out our own.
        for noisy_logger in ("httpx", "httpcore", "chromadb", "urllib3"):
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)

        _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger. Triggers `configure_logging()` on first use."""
    configure_logging()
    return logging.getLogger(name)
