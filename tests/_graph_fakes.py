"""Fake-agent wiring shared by the Phase 5 graph tests.

Not a test module itself (no `test_` prefix, so pytest won't collect it).
Registers a `RunnableLambda`-backed fake for every one of the 17 agents
via `nodes.agent_cache.override_agent` -- the same dependency-injection
seam `BaseAgent` and `agent_cache.get_agent()` were built around -- so the
*entire compiled graph* can run end-to-end with zero API credentials.
`ValidatorAgent`/`CriticAgent` accept a sequence of outcomes so a test can
simulate "low confidence, then high confidence on the next attempt" to
exercise the retry cycle for real rather than only unit-testing the
routing function in isolation.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from itertools import count
from typing import Iterator

from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from incident_agent.agents.base import BaseAgent
from incident_agent.agents.critic import CriticAgent
from incident_agent.agents.final_response import FinalResponseAgent
from incident_agent.agents.human_approval import HumanApprovalAgent
from incident_agent.agents.incident_resolution import IncidentResolutionAgent
from incident_agent.agents.intent_detection import IntentDetectionAgent
from incident_agent.agents.knowledge_graph import KnowledgeGraphAgent
from incident_agent.agents.log_analysis import LogAnalysisAgent
from incident_agent.agents.metrics_analysis import MetricsAnalysisAgent
from incident_agent.agents.planner import PlannerAgent
from incident_agent.agents.reflection import ReflectionAgent
from incident_agent.agents.report_generator import ReportGeneratorAgent
from incident_agent.agents.retriever import RetrieverAgent
from incident_agent.agents.root_cause import RootCauseAnalysisAgent
from incident_agent.agents.sql_agent import SQLAgent
from incident_agent.agents.tool_selection import ToolSelectionAgent
from incident_agent.agents.validator import ValidatorAgent
from incident_agent.agents.web_search import WebSearchAgent
from incident_agent.nodes import agent_cache
from incident_agent.schemas.analysis import (
    KnowledgeGraphResult,
    LogAnalysisResult,
    MetricsAnalysisResult,
    SQLAgentOutput,
    WebSearchResult,
)
from incident_agent.schemas.critique import CriticFeedback, ValidationResult
from incident_agent.schemas.final import FinalAnswer
from incident_agent.schemas.human import ApprovalRequestSummary
from incident_agent.schemas.intent import IntentClassification
from incident_agent.schemas.planning import ExecutionPlan, PlanTask
from incident_agent.schemas.reflection import ReflectionOutput
from incident_agent.schemas.report import IncidentReport
from incident_agent.schemas.resolution import DraftAnswer, ResolutionStep
from incident_agent.schemas.retrieval import RetrievalQueryPlan
from incident_agent.schemas.root_cause import RootCauseAnalysis
from incident_agent.schemas.tool_selection import ToolSelectionDecision


def _register(agent_cls: type[BaseAgent], factory: Callable[[dict], BaseModel]) -> None:
    agent_cache.override_agent(agent_cls, agent_cls(structured_llm=RunnableLambda(factory)))


def _sequence_factory(outcomes: Sequence[BaseModel]) -> Callable[[dict], BaseModel]:
    counter = count()

    def factory(_: dict) -> BaseModel:
        idx = min(next(counter), len(outcomes) - 1)
        return outcomes[idx]

    return factory


@contextmanager
def install_fake_agents(
    *,
    validator_confidences: Sequence[float] = (0.9,),
    critic_approvals: Sequence[bool] = (True,),
    plan_task_types: Sequence[str] = ("log_analysis", "metrics_analysis"),
) -> Iterator[None]:
    """Install fakes for all 17 agents; restores real wiring on exit.

    `validator_confidences`/`critic_approvals` are consumed one-per-call in
    order (repeating the last value once exhausted), letting a test drive
    the retry cycle through a low-confidence attempt followed by a
    high-confidence one within a single graph run.
    """
    _register(
        IntentDetectionAgent,
        lambda _: IntentClassification(
            category="kubernetes",
            urgency="high",
            summary="checkout-api pods are crash looping",
            keywords=["checkout-api"],
            confidence=0.9,
        ),
    )
    _register(
        PlannerAgent,
        lambda _: ExecutionPlan(
            incident_summary="checkout-api pods crash looping, suspected OOM",
            tasks=[PlanTask(task_type=t, description=f"investigate via {t}") for t in plan_task_types],
            rationale="logs and metrics are the fastest signal for a crash-loop symptom",
        ),
    )
    _register(RetrieverAgent, lambda _: RetrievalQueryPlan(queries=["kubernetes pod crash loop oom"]))
    _register(
        LogAnalysisAgent,
        lambda _: LogAnalysisResult(
            summary="OOMKilled events found in pod logs", anomaly_count=2, confidence=0.85,
            error_patterns=["OOMKilled"], affected_components=["checkout-api"],
        ),
    )
    _register(
        MetricsAnalysisAgent,
        lambda _: MetricsAnalysisResult(
            summary="memory usage climbing toward threshold", trend="degrading", confidence=0.85,
            breached_thresholds=["memory_usage_percent"],
        ),
    )
    _register(
        SQLAgent,
        lambda _: SQLAgentOutput(summary="no anomalies found", generated_query="SELECT 1", confidence=0.6),
    )
    _register(KnowledgeGraphAgent, lambda _: KnowledgeGraphResult(summary="checkout-frontend depends on checkout-api", confidence=0.6))
    _register(WebSearchAgent, lambda _: WebSearchResult(summary="no related external issues found", confidence=0.5))
    _register(
        ToolSelectionAgent,
        lambda _: ToolSelectionDecision(selected_tools=["metrics_collector", "k8s_get_pod_status"], rationale="both relevant"),
    )
    _register(
        RootCauseAnalysisAgent,
        lambda _: RootCauseAnalysis(
            root_cause="checkout-api container memory limit is too low for its actual usage pattern",
            evidence_summary="logs show OOMKilled; metrics show memory approaching/exceeding threshold",
            confidence=0.9,
        ),
    )
    _register(
        IncidentResolutionAgent,
        lambda _: DraftAnswer(
            summary="raise the checkout-api memory limit",
            resolution_steps=[ResolutionStep(order=1, action="raise memory limit to 1Gi", command="kubectl set resources deployment/checkout-api --limits=memory=1Gi")],
            risk_level="low",
            estimated_impact="brief rolling restart, no downtime",
        ),
    )
    _register(CriticAgent, _sequence_factory([CriticFeedback(overall_assessment="sound", approve=a) for a in critic_approvals]))
    _register(
        ValidatorAgent,
        _sequence_factory([ValidationResult(is_valid=c >= 0.75, confidence_score=c) for c in validator_confidences]),
    )
    _register(
        ReflectionAgent,
        lambda _: ReflectionOutput(
            what_went_wrong="evidence was thin on the first pass",
            should_replan=True,
            guidance_for_replanner="also gather SQL evidence on connection pool state",
        ),
    )
    _register(
        HumanApprovalAgent,
        lambda _: ApprovalRequestSummary(headline="Approve memory limit increase for checkout-api?", recommended_action="approve"),
    )
    _register(
        ReportGeneratorAgent,
        lambda _: IncidentReport(
            title="checkout-api OOM crash loop",
            executive_summary="checkout-api was crash looping due to an undersized memory limit.",
            root_cause="memory limit too low for actual usage",
            resolution_summary="raised memory limit to 1Gi",
        ),
    )
    _register(
        FinalResponseAgent,
        lambda _: FinalAnswer(answer="Resolved: raised checkout-api's memory limit to 1Gi.", confidence=0.9),
    )

    try:
        yield
    finally:
        agent_cache.clear_overrides()
