"""Phase 5 tests: the compiled LangGraph graph, end to end.

Every test here runs the *real* compiled graph (`build_incident_graph()`)
with fake agents installed via `tests/_graph_fakes.py` -- no network calls,
no API credentials required, but real `StateGraph`/`Send`/`Command`/
`interrupt()`/reducer/checkpointer mechanics from LangGraph itself. This
is deliberately heavier than a unit test: the whole point of Phase 5 is
the *wiring*, which a mocked-graph test wouldn't actually exercise.
"""

from __future__ import annotations

import logging

import pytest
from langgraph.types import Command, Send

from incident_agent.edges.confidence_check import route_after_confidence_check
from incident_agent.edges.evidence_routing import route_to_evidence_tasks
from incident_agent.edges.reflection_routing import route_after_reflection
from incident_agent.graphs.evidence_subgraph import build_evidence_subgraph
from incident_agent.graphs.main_graph import build_incident_graph
from incident_agent.graphs.state import create_initial_state
from incident_agent.models.enums import ApprovalStatus
from incident_agent.schemas.critique import CriticFeedback, ValidationResult
from incident_agent.schemas.human import HumanFeedback
from incident_agent.schemas.planning import ExecutionPlan, PlanTask

from ._graph_fakes import install_fake_agents

# LangGraph logs a (harmless, expected) deprecation-style warning about
# unregistered types when the in-memory checkpointer serializes our
# Pydantic-model state values; it's noise for this test suite.
logging.getLogger("langgraph.checkpoint.serde.jsonplus").setLevel(logging.ERROR)


def _thread_config(state: dict) -> dict:
    return {"configurable": {"thread_id": state["thread_id"]}}


@pytest.mark.unit
class TestEvidenceRoutingEdge:
    def test_dispatches_one_send_per_plan_task(self) -> None:
        state = create_initial_state("q")
        state["plan"] = ExecutionPlan(
            incident_summary="s",
            rationale="r",
            tasks=[
                PlanTask(task_type="log_analysis", description="d1"),
                PlanTask(task_type="sql_query", description="d2"),
            ],
        )
        sends = route_to_evidence_tasks(state)
        assert {s.node for s in sends} == {"log_analysis", "sql_query"}
        assert all(isinstance(s, Send) for s in sends)

    def test_falls_back_to_log_analysis_when_plan_is_missing(self) -> None:
        state = create_initial_state("q")
        sends = route_to_evidence_tasks(state)
        assert len(sends) == 1
        assert sends[0].node == "log_analysis"

    def test_falls_back_when_plan_has_no_tasks(self) -> None:
        state = create_initial_state("q")
        state["plan"] = ExecutionPlan(incident_summary="s", rationale="r", tasks=[PlanTask(task_type="log_analysis", description="d")])
        state["plan"].tasks.clear()
        sends = route_to_evidence_tasks(state)
        assert len(sends) == 1
        assert sends[0].node == "log_analysis"


@pytest.mark.unit
class TestConfidenceCheckEdge:
    def _state(self, *, confidence: float, approve: bool, retry_count: int) -> dict:
        state = create_initial_state("q")
        state["confidence_score"] = confidence
        state["critic_feedback"] = CriticFeedback(overall_assessment="a", approve=approve)
        state["retry_count"] = retry_count
        return state

    def test_high_confidence_and_approval_proceeds_to_human_approval(self) -> None:
        state = self._state(confidence=0.95, approve=True, retry_count=0)
        assert route_after_confidence_check(state) == "human_approval"

    def test_low_confidence_with_retries_remaining_goes_to_reflection(self) -> None:
        state = self._state(confidence=0.2, approve=True, retry_count=0)
        assert route_after_confidence_check(state) == "reflection"

    def test_critic_rejection_alone_triggers_reflection(self) -> None:
        state = self._state(confidence=0.99, approve=False, retry_count=0)
        assert route_after_confidence_check(state) == "reflection"

    def test_exhausted_retries_proceeds_to_human_approval_regardless(self) -> None:
        state = self._state(confidence=0.1, approve=False, retry_count=3)
        assert route_after_confidence_check(state) == "human_approval"


@pytest.mark.unit
class TestReflectionRoutingEdge:
    def test_should_replan_and_retries_remaining_goes_to_planner(self) -> None:
        state = create_initial_state("q")
        state["retry_count"] = 1
        state["metadata"] = {"last_reflection_should_replan": True}
        assert route_after_reflection(state) == "planner"

    def test_should_not_replan_goes_to_human_approval(self) -> None:
        state = create_initial_state("q")
        state["retry_count"] = 1
        state["metadata"] = {"last_reflection_should_replan": False}
        assert route_after_reflection(state) == "human_approval"

    def test_retries_exhausted_goes_to_human_approval_even_if_should_replan(self) -> None:
        state = create_initial_state("q")
        state["retry_count"] = 3
        state["metadata"] = {"last_reflection_should_replan": True}
        assert route_after_reflection(state) == "human_approval"


@pytest.mark.graph
class TestEvidenceSubgraphInIsolation:
    def test_runs_only_the_planned_task_types(self) -> None:
        with install_fake_agents(plan_task_types=["log_analysis"]):
            subgraph = build_evidence_subgraph()
            state = create_initial_state("q")
            state["plan"] = ExecutionPlan(
                incident_summary="s", rationale="r", tasks=[PlanTask(task_type="log_analysis", description="d")]
            )
            result = subgraph.invoke(state)
            node_names = {r.node_name for r in result["reasoning"]}
            assert node_names == {"log_analysis"}
            assert result["logs"]

    def test_runs_multiple_planned_branches_in_one_pass(self) -> None:
        with install_fake_agents(plan_task_types=["log_analysis", "metrics_analysis"]):
            subgraph = build_evidence_subgraph()
            state = create_initial_state("q")
            state["plan"] = ExecutionPlan(
                incident_summary="s",
                rationale="r",
                tasks=[
                    PlanTask(task_type="log_analysis", description="d"),
                    PlanTask(task_type="metrics_analysis", description="d"),
                ],
            )
            result = subgraph.invoke(state)
            assert {r.node_name for r in result["reasoning"]} == {"log_analysis", "metrics_analysis"}
            assert result["logs"] and result["metrics"]


@pytest.mark.graph
class TestFullGraphHappyPath:
    def test_pauses_at_human_approval_interrupt(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph()
            state = create_initial_state("my checkout-api pods keep restarting")
            result = graph.invoke(state, _thread_config(state))

            assert "__interrupt__" in result
            interrupt_payload = result["__interrupt__"][0].value
            assert interrupt_payload["kind"] == "approval_request"
            assert interrupt_payload["incident_id"] == state["incident_id"]
            assert result["approval_status"] == ApprovalStatus.PENDING
            assert result["retry_count"] == 0
            # No duplication from the evidence-gathering node (see
            # graphs/evidence_subgraph.invoke_evidence_subgraph docstring).
            entry_ids = [e.entry_id for e in result["execution_history"]]
            assert len(entry_ids) == len(set(entry_ids))

    def test_approval_resumes_through_report_and_final_response(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph()
            state = create_initial_state("my checkout-api pods keep restarting")
            config = _thread_config(state)
            graph.invoke(state, config)

            feedback = HumanFeedback(decision=ApprovalStatus.APPROVED, comments="go ahead")
            result = graph.invoke(Command(resume=feedback.model_dump(mode="json")), config)

            assert result["approval_status"] == ApprovalStatus.APPROVED
            assert result["final_answer"] is not None
            assert "incident_report" in result["metadata"]
            assert "memory_record_pending_persist" in result["metadata"]
            node_sequence = [e.node_name for e in result["execution_history"]]
            assert node_sequence[-3:] == ["report_generator", "save_memory", "final_response"]

    def test_rejection_skips_report_generation(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph()
            state = create_initial_state("my checkout-api pods keep restarting")
            config = _thread_config(state)
            graph.invoke(state, config)

            feedback = HumanFeedback(decision=ApprovalStatus.REJECTED, comments="not safe enough")
            result = graph.invoke(Command(resume=feedback.model_dump(mode="json")), config)

            assert result["approval_status"] == ApprovalStatus.REJECTED
            assert "not safe enough" in result["final_answer"].answer
            assert "incident_report" not in result["metadata"]
            node_sequence = [e.node_name for e in result["execution_history"]]
            assert "report_generator" not in node_sequence
            assert node_sequence[-1] == "final_response"

    def test_modified_decision_overrides_draft_answer_and_still_generates_report(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph()
            state = create_initial_state("my checkout-api pods keep restarting")
            config = _thread_config(state)
            graph.invoke(state, config)

            from incident_agent.schemas.resolution import DraftAnswer, ResolutionStep

            modified = DraftAnswer(
                summary="human-edited resolution: scale up replicas instead",
                resolution_steps=[ResolutionStep(order=1, action="scale replicas to 5")],
                risk_level="low",
                estimated_impact="none",
            )
            feedback = HumanFeedback(
                decision=ApprovalStatus.MODIFIED, modified_draft_answer=modified, comments="prefer scaling"
            )
            result = graph.invoke(Command(resume=feedback.model_dump(mode="json")), config)

            assert result["approval_status"] == ApprovalStatus.MODIFIED
            assert result["draft_answer"].summary == "human-edited resolution: scale up replicas instead"
            assert "incident_report" in result["metadata"]


@pytest.mark.graph
class TestStreaming:
    """Node-level streaming -- `stream_mode="updates"` yields one chunk per
    completed node, which is what a FastAPI SSE endpoint (Phase 9) will
    forward to a client as progress updates."""

    def test_updates_stream_yields_one_chunk_per_node_in_order(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph()
            state = create_initial_state("my checkout-api pods keep restarting")
            config = _thread_config(state)

            node_names: list[str] = []
            for chunk in graph.stream(state, config, stream_mode="updates"):
                node_names.extend(chunk.keys())

            # Nodes preceding the interrupt must appear, in dependency order
            # (parallel evidence branches may interleave with each other but
            # never with their sequential neighbors).
            assert node_names[0] == "intent_detection"
            assert "planner" in node_names
            assert node_names.index("planner") < node_names.index("merge_results")
            assert node_names.index("merge_results") < node_names.index("root_cause_analysis")
            # human_approval never completes normally -- it interrupts mid-
            # execution -- so "updates" mode never emits a chunk for it
            # (there is no update to report); the stream's last chunk is
            # LangGraph's own "__interrupt__" marker, preceded by critic
            # (the last node that actually completed).
            assert node_names[-1] == "__interrupt__"
            assert node_names[-2] == "critic"
            assert "human_approval" not in node_names


@pytest.mark.graph
class TestFullGraphRetryCycle:
    def test_low_confidence_triggers_replan_then_succeeds(self) -> None:
        with install_fake_agents(validator_confidences=(0.5, 0.9), critic_approvals=(True, True)):
            graph = build_incident_graph()
            state = create_initial_state("my checkout-api pods keep restarting")
            config = _thread_config(state)
            result = graph.invoke(state, config)

            assert result["retry_count"] == 1
            assert result["confidence_score"] == pytest.approx(0.9)
            node_sequence = [e.node_name for e in result["execution_history"]]
            assert node_sequence.count("planner") == 2
            assert node_sequence.count("reflection") == 1
            assert "__interrupt__" in result

    def test_retry_stops_after_max_replan_attempts(self) -> None:
        # Always-low confidence: the cycle must still terminate (bounded by
        # settings.max_replan_attempts) and reach human_approval rather than
        # looping forever.
        with install_fake_agents(validator_confidences=(0.1,) * 10, critic_approvals=(True,) * 10):
            graph = build_incident_graph()
            state = create_initial_state("my checkout-api pods keep restarting")
            config = _thread_config(state)
            result = graph.invoke(state, config)

            from incident_agent.config.settings import get_settings

            assert result["retry_count"] == get_settings().max_replan_attempts
            assert "__interrupt__" in result
