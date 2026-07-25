"""State -> LLM-readable text formatters.

Several prompts (Root Cause Analysis, Validator, Critic, Report
Generator) all need substantially the same "here's the evidence we've
gathered" text. Centralizing that formatting here means the exact same
rendering logic backs every one of them -- avoiding the drift you'd get
if each node formatted `state["logs"]` slightly differently -- and means
`merge_results_node` (Phase 5) can compute it once and cache it in
`state["metadata"]["evidence_bundle"]` for every downstream node to reuse
instead of recomputing it three times per run.
"""

from __future__ import annotations

from incident_agent.models.documents import Citation, RetrievedDocument
from incident_agent.models.execution import ExecutionHistoryEntry, ReasoningStep
from incident_agent.models.memory import MemoryContext
from incident_agent.models.tool_results import LogEntry, MetricSample, SQLQueryResult
from incident_agent.schemas.critique import CriticFeedback, ValidationResult
from incident_agent.schemas.intent import IntentClassification
from incident_agent.schemas.planning import ExecutionPlan
from incident_agent.schemas.resolution import DraftAnswer

# The six node names that populate evidence during the parallel fan-out --
# used to filter `state["reasoning"]` down to evidence-branch syntheses
# specifically, since other nodes append reasoning steps too.
EVIDENCE_NODE_NAMES = frozenset(
    {"log_analysis", "metrics_analysis", "vector_search", "sql_query", "web_search", "knowledge_graph"}
)


def format_logs(logs: list[LogEntry], limit: int = 30) -> str:
    if not logs:
        return "(no log entries gathered)"
    lines = [f"[{e.timestamp.isoformat()}] {e.severity.value.upper()} {e.source}: {e.message}" for e in logs[-limit:]]
    return "\n".join(lines)


def format_metrics(metrics: list[MetricSample], limit: int = 30) -> str:
    if not metrics:
        return "(no metric samples gathered)"
    lines = [
        f"{m.timestamp.isoformat()} {m.metric_name}={m.value}{m.unit}"
        f"{' [ANOMALOUS, threshold=' + str(m.threshold) + ']' if m.is_anomalous else ''}"
        for m in metrics[-limit:]
    ]
    return "\n".join(lines)


def format_documents(documents: list[RetrievedDocument]) -> str:
    if not documents:
        return "(no documents retrieved)"
    lines = [f"[{d.document_id}] (score={d.score:.2f}) {d.title}: {d.content[:300]}" for d in documents]
    return "\n".join(lines)


def format_sql_results(results: list[SQLQueryResult]) -> str:
    if not results:
        return "(no SQL queries executed)"
    lines = []
    for r in results:
        lines.append(f"Query: {r.query}\nRows ({r.row_count}): {r.rows[:10]}")
    return "\n\n".join(lines)


def format_evidence_reasoning(reasoning: list[ReasoningStep]) -> str:
    """The evidence-gathering agents' own structured syntheses (log/metrics/
    vector/sql/web/knowledge-graph analysis results), rendered chronologically."""
    filtered = [r for r in reasoning if r.node_name in EVIDENCE_NODE_NAMES]
    if not filtered:
        return "(no evidence-branch findings recorded)"
    return "\n".join(f"[{r.node_name}] {r.content}" for r in filtered)


def format_citations(citations: list[Citation]) -> str:
    if not citations:
        return "(no citations available)"
    return "\n".join(f"[{c.citation_id}] ({c.source}) {c.locator}: {c.snippet}" for c in citations)


def format_execution_history(history: list[ExecutionHistoryEntry]) -> str:
    if not history:
        return "(no execution history recorded)"
    return "\n".join(f"{h.started_at.isoformat()} {h.node_name} [{h.status.value}]: {h.summary}" for h in history)


def format_intent(intent: IntentClassification | None) -> str:
    if intent is None:
        return "(intent not yet classified)"
    secondary = ", ".join(c.value for c in intent.secondary_categories) or "none"
    return (
        f"category={intent.category.value}, secondary=[{secondary}], urgency={intent.urgency.value}, "
        f"summary='{intent.summary}', keywords={intent.keywords}"
    )


def format_root_cause(root_cause: dict | None) -> str:
    """`root_cause` is the Root Cause Analysis Agent's structured output,
    stashed as a plain dict in `state["metadata"]["root_cause_analysis"]`
    by `root_cause_node` -- there is no dedicated `IncidentState` field for
    it, since only `final_answer`/`draft_answer`/`validated_answer` are in
    the spec's state schema.
    """
    if not root_cause:
        return "(root cause not yet determined)"
    return (
        f"Root cause: {root_cause['root_cause']}\n"
        f"Contributing factors: {root_cause.get('contributing_factors', [])}\n"
        f"Affected components: {root_cause.get('affected_components', [])}\n"
        f"Evidence summary: {root_cause.get('evidence_summary', '')}\n"
        f"Confidence: {root_cause.get('confidence')}"
    )


def format_draft_answer(draft: DraftAnswer | None) -> str:
    if draft is None:
        return "(no draft resolution yet)"
    steps = "\n".join(f"  {s.order}. [{s.risk.value}] {s.action}" + (f" `{s.command}`" if s.command else "") for s in draft.resolution_steps)
    return (
        f"Summary: {draft.summary}\nRisk level: {draft.risk_level.value}\n"
        f"Estimated impact: {draft.estimated_impact}\nSteps:\n{steps}\n"
        f"Rollback plan: {draft.rollback_plan or '(none specified)'}"
    )


def format_validation_result(validation: ValidationResult | None) -> str:
    if validation is None:
        return "(not yet validated)"
    checks = "\n".join(f"  - {c.check_name}: {'PASS' if c.passed else 'FAIL'} -- {c.detail}" for c in validation.checks)
    return f"is_valid={validation.is_valid}, confidence={validation.confidence_score}\n{checks}"


def format_critic_feedback(feedback: CriticFeedback | None) -> str:
    if feedback is None:
        return "(no critic feedback yet)"
    issues = "\n".join(f"  - [{i.severity}] {i.issue} -- suggestion: {i.suggestion}" for i in feedback.issues)
    return f"approve={feedback.approve}\n{feedback.overall_assessment}\n{issues}"


def format_plan(plan: ExecutionPlan | None) -> str:
    if plan is None:
        return "(no plan yet)"
    tasks = "\n".join(f"  - {t.task_type.value}: {t.description}" for t in plan.tasks)
    return f"{plan.incident_summary}\nRationale: {plan.rationale}\nTasks:\n{tasks}"


def format_memory_context(memory: MemoryContext | None) -> str:
    if memory is None:
        return "(no prior memory recalled for this session)"
    parts: list[str] = []
    if memory.similar_past_incidents:
        parts.append(
            "Similar past incidents:\n"
            + "\n".join(
                f"- [{i.incident_id}] {i.title}: root cause was '{i.root_cause}', resolved via "
                f"'{i.resolution_summary}'"
                for i in memory.similar_past_incidents
            )
        )
    if memory.frequent_fixes:
        parts.append(
            "Frequently used fixes for this category:\n"
            + "\n".join(f"- {f.description} (used {f.usage_count}x)" for f in memory.frequent_fixes)
        )
    if memory.user_preferences:
        parts.append(
            "User preferences:\n" + "\n".join(f"- {p.key}: {p.value}" for p in memory.user_preferences)
        )
    if memory.conversation_summary:
        parts.append(f"Prior conversation summary:\n{memory.conversation_summary}")
    return "\n\n".join(parts) if parts else "(no prior memory recalled for this session)"


def build_evidence_bundle(
    *,
    logs: list[LogEntry],
    metrics: list[MetricSample],
    documents: list[RetrievedDocument],
    sql_results: list[SQLQueryResult],
    reasoning: list[ReasoningStep],
) -> str:
    """The single consolidated evidence text fed to Root Cause Analysis,
    Validator, and Critic -- combining raw evidence with each evidence
    branch's own synthesis."""
    sections = [
        ("Evidence-branch findings", format_evidence_reasoning(reasoning)),
        ("Log entries", format_logs(logs)),
        ("Metric samples", format_metrics(metrics)),
        ("Retrieved documents", format_documents(documents)),
        ("SQL query results", format_sql_results(sql_results)),
    ]
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections)
