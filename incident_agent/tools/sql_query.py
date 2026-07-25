"""SQL Query tool -- runs a read-only query against the mock database.

Defense in depth against the SQL Agent (or any caller) issuing a
destructive statement: even though the agent's own prompt instructs
SELECT-only, we don't rely on prompt compliance -- a lightweight
statement-type check rejects anything that isn't a single SELECT before
it ever reaches `sqlite3`.
"""

from __future__ import annotations

import re
import time

from langchain_core.tools import tool

from incident_agent.models.tool_results import SQLQueryResult
from incident_agent.services.mock_database import get_connection, get_schema_description
from incident_agent.tools.base import run_structured

_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_MAX_ROWS = 200


class NonSelectQueryError(ValueError):
    """Raised when a caller attempts a non-SELECT statement through this tool."""


def _execute(query: str) -> SQLQueryResult:
    if ";" in query.strip().rstrip(";"):
        raise NonSelectQueryError("Multiple statements are not permitted; issue one SELECT at a time.")
    if not _SELECT_ONLY.match(query):
        raise NonSelectQueryError("Only SELECT statements are permitted through this tool.")

    conn = get_connection()
    started = time.perf_counter()
    cursor = conn.execute(query)
    rows = cursor.fetchmany(_MAX_ROWS + 1)
    execution_time_ms = (time.perf_counter() - started) * 1000

    truncated = len(rows) > _MAX_ROWS
    rows = rows[:_MAX_ROWS]
    columns = [description[0] for description in cursor.description] if cursor.description else []
    return SQLQueryResult(
        query=query,
        columns=columns,
        rows=[dict(row) for row in rows],
        row_count=len(rows),
        execution_time_ms=execution_time_ms,
        truncated=truncated,
    )


@tool
def sql_query(query: str) -> str:
    """Run a read-only SQL SELECT query against the incident database.

    The schema available is:
    {schema}

    Only SELECT statements are accepted -- any INSERT/UPDATE/DELETE/DDL or
    multi-statement input is rejected. Results are capped at 200 rows.
    """
    return run_structured("sql_query", lambda: _execute(query))


sql_query.description = (sql_query.description or "").format(schema=get_schema_description())
