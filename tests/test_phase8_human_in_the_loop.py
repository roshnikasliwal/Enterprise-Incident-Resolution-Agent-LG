"""Phase 8 tests: human-in-the-loop capabilities beyond plain approve/
reject (already covered in Phase 5) -- Modify State, Edit Plan, Retry,
Skip Tool (via edited plan), static `interrupt_before`/`interrupt_after`,
and the `IncidentController` seam Phase 9's API will sit on top of.
"""

from __future__ import annotations

import logging

import pytest

from incident_agent.controllers.incident_controller import IncidentController, IncidentNotFoundError
from incident_agent.graphs.main_graph import build_incident_graph
from incident_agent.models.enums import ApprovalStatus, TaskType
from incident_agent.schemas.resolution import DraftAnswer, ResolutionStep

from ._graph_fakes import install_fake_agents

logging.getLogger("langgraph.checkpoint.serde.jsonplus").setLevel(logging.ERROR)


@pytest.mark.graph
class TestIncidentController:
    def test_start_investigation_pauses_at_human_approval(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            controller = IncidentController(build_incident_graph())
            result = controller.start_investigation("checkout-api pods keep restarting")
            assert controller.is_paused(result["thread_id"])
            assert result["approval_status"] == ApprovalStatus.PENDING

    def test_approve_completes_the_run(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            controller = IncidentController(build_incident_graph())
            result = controller.start_investigation("q")
            final = controller.approve(result["thread_id"], comments="go ahead")
            assert final["approval_status"] == ApprovalStatus.APPROVED
            assert final["final_answer"] is not None
            assert not controller.is_paused(result["thread_id"])

    def test_reject_completes_without_report(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            controller = IncidentController(build_incident_graph())
            result = controller.start_investigation("q")
            final = controller.reject(result["thread_id"], comments="too risky")
            assert final["approval_status"] == ApprovalStatus.REJECTED
            assert "incident_report" not in final["metadata"]

    def test_modify_draft_answer_substitutes_and_still_generates_report(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            controller = IncidentController(build_incident_graph())
            result = controller.start_investigation("q")
            modified = DraftAnswer(
                summary="scale replicas instead of raising memory",
                resolution_steps=[ResolutionStep(order=1, action="scale to 5 replicas")],
                risk_level="low",
                estimated_impact="none",
            )
            final = controller.modify_draft_answer(result["thread_id"], modified, comments="prefer scaling")
            assert final["approval_status"] == ApprovalStatus.MODIFIED
            assert final["draft_answer"].summary == "scale replicas instead of raising memory"
            assert "incident_report" in final["metadata"]

    def test_get_status_raises_for_unknown_thread(self) -> None:
        with install_fake_agents():
            controller = IncidentController(build_incident_graph())
            with pytest.raises(IncidentNotFoundError):
                controller.get_status("THR-does-not-exist")


@pytest.mark.graph
class TestEditPlanRetryAndSkipTool:
    def test_edit_plan_and_retry_reruns_evidence_gathering_with_new_plan(self) -> None:
        with install_fake_agents(
            validator_confidences=(0.9, 0.9), critic_approvals=(True, True), plan_task_types=["log_analysis", "metrics_analysis"]
        ):
            controller = IncidentController(build_incident_graph())
            result = controller.start_investigation("checkout-api pods keep restarting")
            assert result["retry_count"] == 0

            # Skip Tool: keep only log_analysis on the retry pass.
            edited_plan = result["plan"].model_copy(
                update={"tasks": [t for t in result["plan"].tasks if t.task_type == TaskType.LOG_ANALYSIS]}
            )
            resumed = controller.edit_plan_and_retry(
                result["thread_id"], edited_plan, comments="metrics were inconclusive, focus on logs"
            )

            assert resumed["retry_count"] == 1
            assert controller.is_paused(result["thread_id"])  # back at human_approval again
            node_names = [e.node_name for e in resumed["execution_history"]]
            # metrics_analysis ran on the first pass but must NOT run again
            # after being removed from the retried plan.
            assert node_names.count("metrics_analysis") == 1
            assert node_names.count("log_analysis") == 2

            final = controller.approve(result["thread_id"])
            assert final["approval_status"] == ApprovalStatus.APPROVED


@pytest.mark.graph
class TestStaticInterrupts:
    def test_interrupt_before_pauses_ahead_of_the_named_node(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph(interrupt_before=["evidence_gathering"])
            controller = IncidentController(graph)
            result = controller.start_investigation("q")

            snapshot_next = graph.get_state({"configurable": {"thread_id": result["thread_id"]}}).next
            assert snapshot_next == ("evidence_gathering",)
            # A static interrupt carries no payload -- unlike human_approval's
            # dynamic interrupt() call, it never populates "__interrupt__" at
            # all; `.next` on the state snapshot is the only way to detect it.
            assert "__interrupt__" not in result
            assert result["plan"] is not None

    def test_update_state_before_resuming_a_static_interrupt_edits_the_plan(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph(interrupt_before=["evidence_gathering"])
            controller = IncidentController(graph)
            result = controller.start_investigation("checkout-api pods keep restarting")

            edited_plan = result["plan"].model_copy(
                update={"tasks": [t for t in result["plan"].tasks if t.task_type == TaskType.LOG_ANALYSIS]}
            )
            controller.update_state(result["thread_id"], {"plan": edited_plan})
            resumed = controller.resume(result["thread_id"])

            node_names = [e.node_name for e in resumed["execution_history"]]
            assert "log_analysis" in node_names
            assert "metrics_analysis" not in node_names
            # The run continues normally past evidence gathering to the
            # dynamic human_approval interrupt.
            assert controller.is_paused(result["thread_id"])

    def test_interrupt_after_pauses_following_the_named_node(self) -> None:
        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph(interrupt_after=["root_cause_analysis"])
            controller = IncidentController(graph)
            result = controller.start_investigation("q")

            snapshot = graph.get_state({"configurable": {"thread_id": result["thread_id"]}})
            assert snapshot.next == ("incident_resolution",)
            assert "root_cause_analysis" in result["metadata"]
            # incident_resolution/validator/critic must not have run yet.
            assert result["draft_answer"] is None

            resumed = controller.resume(result["thread_id"])
            assert resumed["draft_answer"] is not None
            assert controller.is_paused(result["thread_id"])  # reaches human_approval next
