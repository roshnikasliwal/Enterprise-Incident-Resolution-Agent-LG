"""Closes a real gap left after Phase 5: the evidence-gathering subgraph's
tests only ever exercised `log_analysis`/`metrics_analysis` branches (the
`_graph_fakes.install_fake_agents` default). `sql_query`, `vector_search`,
`web_search`, and `knowledge_graph` had never actually been run through
the graph in any test -- only indirectly type-checked by Phase 4's
per-agent fake-LLM test. This runs each of the remaining four branches
for real, through the compiled evidence subgraph, against the real tools
(mock infra / seeded knowledge base / mock database) they call.
"""

from __future__ import annotations

import logging

import pytest

from incident_agent.graphs.evidence_subgraph import build_evidence_subgraph
from incident_agent.graphs.state import create_initial_state
from incident_agent.schemas.intent import IntentClassification
from incident_agent.schemas.planning import ExecutionPlan, PlanTask

from ._graph_fakes import install_fake_agents

logging.getLogger("langgraph.checkpoint.serde.jsonplus").setLevel(logging.ERROR)


def _run_single_task_subgraph(task_type: str, *, category: str = "kubernetes") -> dict:
    with install_fake_agents(plan_task_types=[task_type]):
        subgraph = build_evidence_subgraph()
        state = create_initial_state("checkout-api pods keep restarting")
        state["intent"] = IntentClassification(category=category, urgency="high", summary="s", confidence=0.9)
        state["plan"] = ExecutionPlan(
            incident_summary="s", rationale="r", tasks=[PlanTask(task_type=task_type, description="investigate")]
        )
        return subgraph.invoke(state)


@pytest.mark.graph
class TestSqlQueryBranch:
    def test_runs_the_sql_agent_twice_and_populates_sql_results(self) -> None:
        result = _run_single_task_subgraph("sql_query", category="database")
        assert result["sql_results"], "expected the sql_query tool's result to be captured"
        assert any(r.node_name == "sql_query" for r in result["reasoning"])
        history = [e for e in result["execution_history"] if e.node_name == "sql_query"]
        assert history and history[0].status.value == "completed"


@pytest.mark.graph
class TestVectorSearchBranch:
    def test_runs_the_retriever_and_populates_documents_and_citations(self) -> None:
        result = _run_single_task_subgraph("vector_search")
        assert result["retrieved_documents"]
        assert result["citations"]
        assert any(r.node_name == "vector_search" for r in result["reasoning"])
        # The seeded knowledge base has a crash-loop runbook -- a query
        # this close to it should surface it.
        assert any(d.document_id == "kb-k8s-crashloop" for d in result["retrieved_documents"])


@pytest.mark.graph
class TestWebSearchBranch:
    def test_runs_the_mock_search_and_web_search_agent(self) -> None:
        result = _run_single_task_subgraph("web_search")
        assert any(r.node_name == "web_search" for r in result["reasoning"])
        web_search_tool_results = [t for t in result["tool_results"] if t.tool_name == "web_search_mock"]
        assert web_search_tool_results


@pytest.mark.graph
class TestSendPayloadCarriesSharedContext:
    """Regression test for the Send-payload-is-the-entire-state gotcha
    documented in edges/evidence_routing.py: `intent` must reach a
    dispatched evidence node so `infer_target_name()` can use
    `intent.keywords` instead of silently falling back to the default
    target on every single run.
    """

    def test_intent_keywords_reach_log_analysis_via_target_inference(self) -> None:
        with install_fake_agents(plan_task_types=["log_analysis"]):
            subgraph = build_evidence_subgraph()
            state = create_initial_state("q")
            state["intent"] = IntentClassification(
                category="kubernetes", urgency="high", summary="s", keywords=["payments-worker"], confidence=0.9
            )
            state["plan"] = ExecutionPlan(
                incident_summary="s", rationale="r", tasks=[PlanTask(task_type="log_analysis", description="d")]
            )
            result = subgraph.invoke(state)

            log_entries = result["logs"]
            assert log_entries, "expected the log_analysis branch to have run and produced log entries"
            assert all(entry.source == "payments-worker" for entry in log_entries)


@pytest.mark.graph
class TestKnowledgeGraphBranch:
    def test_runs_the_dependency_graph_lookup_and_agent(self) -> None:
        result = _run_single_task_subgraph("knowledge_graph")
        assert any(r.node_name == "knowledge_graph" for r in result["reasoning"])
        # No dedicated state field for this branch's output -- unlike the
        # others, its only observable trace is the reasoning entry itself
        # (see nodes/knowledge_graph_node.py).
        entry = next(r for r in result["reasoning"] if r.node_name == "knowledge_graph")
        assert "confidence=" in entry.content
