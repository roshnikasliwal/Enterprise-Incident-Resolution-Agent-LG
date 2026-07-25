"""SQL Agent prompt -- text-to-SQL over the (mocked) Postgres schema."""

from __future__ import annotations

from incident_agent.prompts.common import build_agent_prompt

SQL_AGENT_PROMPT = build_agent_prompt(
    agent_name="SQL Agent",
    responsibility=(
        "Given a database schema and an investigation question, write a single read-only SQL "
        "query that would surface the relevant evidence, then summarize what the results show. "
        "You will be shown the query's actual results before finalizing your summary."
    ),
    extra_system_notes=(
        "Only ever write SELECT statements. Never write INSERT/UPDATE/DELETE/DDL -- this tool "
        "is for investigation, not remediation. Keep queries narrow (use WHERE/LIMIT) rather "
        "than dumping entire tables."
    ),
    human_template=(
        "Current investigation task:\n{task_description}\n\n"
        "Database schema:\n{schema_description}\n\n"
        "Query results (if the query has already been executed; empty if you are producing "
        "the query for the first time):\n{query_results}"
    ),
)
