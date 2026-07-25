"""Phase 7 tests: real SQLite-backed checkpointing -- persistence across a
simulated process restart, thread isolation, and the application-level
"multiple users" index (`ThreadRegistry`).

Every test builds its own `SqliteSaver` against a `tmp_path` file, never
`get_checkpointer()`'s real project-data-backed singleton.
"""

from __future__ import annotations

import logging

import pytest
from langgraph.types import Command

from incident_agent.graphs.main_graph import build_incident_graph
from incident_agent.graphs.state import create_initial_state
from incident_agent.memory.memory_service import get_memory_service
from incident_agent.models.enums import ApprovalStatus
from incident_agent.schemas.human import HumanFeedback
from incident_agent.services.checkpointer import build_checkpointer, list_thread_ids

from ._graph_fakes import install_fake_agents

logging.getLogger("langgraph.checkpoint.serde.jsonplus").setLevel(logging.ERROR)


@pytest.mark.unit
class TestCheckpointerFactory:
    def test_build_checkpointer_creates_tables(self, tmp_path) -> None:
        db_path = str(tmp_path / "checkpoints.sqlite")
        saver = build_checkpointer(db_path)
        tables = {
            row[0]
            for row in saver.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"checkpoints", "writes"} <= tables

    def test_list_thread_ids_reflects_written_checkpoints(self, tmp_path) -> None:
        db_path = str(tmp_path / "checkpoints.sqlite")
        saver = build_checkpointer(db_path)
        assert list_thread_ids(saver) == []

        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            graph = build_incident_graph(checkpointer=saver)
            state = create_initial_state("q")
            graph.invoke(state, {"configurable": {"thread_id": state["thread_id"]}})

        assert list_thread_ids(saver) == [state["thread_id"]]


@pytest.mark.graph
class TestPersistenceAcrossSimulatedRestart:
    def test_resume_works_from_a_freshly_reconnected_checkpointer(self, tmp_path) -> None:
        db_path = str(tmp_path / "checkpoints.sqlite")

        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            # "Process 1": run up to the human-approval interrupt.
            saver_a = build_checkpointer(db_path)
            graph_a = build_incident_graph(checkpointer=saver_a)
            state = create_initial_state("checkout-api pods keep restarting")
            config = {"configurable": {"thread_id": state["thread_id"]}}
            result_a = graph_a.invoke(state, config)
            assert "__interrupt__" in result_a
            del graph_a, saver_a  # simulate the process exiting

            # "Process 2": reconnect to the same SQLite file with brand-new
            # objects and resume -- proves durability, not just in-memory
            # object reuse.
            saver_b = build_checkpointer(db_path)
            graph_b = build_incident_graph(checkpointer=saver_b)
            feedback = HumanFeedback(decision=ApprovalStatus.APPROVED)
            result_b = graph_b.invoke(Command(resume=feedback.model_dump(mode="json")), config)

            assert result_b["approval_status"] == ApprovalStatus.APPROVED
            assert result_b["final_answer"] is not None
            # State accumulated before the "restart" (evidence, reasoning,
            # execution history) must have survived the round trip.
            assert result_b["user_query"] == "checkout-api pods keep restarting"
            assert any(e.node_name == "root_cause_analysis" for e in result_b["execution_history"])

    def test_get_state_reflects_the_persisted_checkpoint_after_restart(self, tmp_path) -> None:
        db_path = str(tmp_path / "checkpoints.sqlite")

        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            saver_a = build_checkpointer(db_path)
            graph_a = build_incident_graph(checkpointer=saver_a)
            state = create_initial_state("q")
            config = {"configurable": {"thread_id": state["thread_id"]}}
            graph_a.invoke(state, config)
            del graph_a, saver_a

            saver_b = build_checkpointer(db_path)
            graph_b = build_incident_graph(checkpointer=saver_b)
            snapshot = graph_b.get_state(config)
            assert snapshot.values["thread_id"] == state["thread_id"]
            assert snapshot.next == ("human_approval",)


@pytest.mark.graph
class TestMultipleThreadsIsolation:
    def test_two_threads_on_one_checkpointer_do_not_leak_state(self, tmp_path) -> None:
        db_path = str(tmp_path / "checkpoints.sqlite")

        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            saver = build_checkpointer(db_path)
            graph = build_incident_graph(checkpointer=saver)

            state_1 = create_initial_state("checkout-api pods restarting")
            state_2 = create_initial_state("payments-worker consumer lag climbing")
            config_1 = {"configurable": {"thread_id": state_1["thread_id"]}}
            config_2 = {"configurable": {"thread_id": state_2["thread_id"]}}

            result_1 = graph.invoke(state_1, config_1)
            result_2 = graph.invoke(state_2, config_2)

            assert result_1["user_query"] == "checkout-api pods restarting"
            assert result_2["user_query"] == "payments-worker consumer lag climbing"
            assert result_1["incident_id"] != result_2["incident_id"]

            # Resuming thread 1 must not affect thread 2's checkpoint.
            feedback = HumanFeedback(decision=ApprovalStatus.APPROVED)
            resumed_1 = graph.invoke(Command(resume=feedback.model_dump(mode="json")), config_1)
            assert resumed_1["approval_status"] == ApprovalStatus.APPROVED

            state_2_snapshot = graph.get_state(config_2)
            assert state_2_snapshot.values["approval_status"] == ApprovalStatus.PENDING
            assert set(list_thread_ids(saver)) == {state_1["thread_id"], state_2["thread_id"]}


@pytest.mark.graph
class TestMultipleUsersViaThreadRegistry:
    def test_thread_registry_scopes_threads_per_session(self, tmp_path) -> None:
        db_path = str(tmp_path / "checkpoints.sqlite")

        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            saver = build_checkpointer(db_path)
            graph = build_incident_graph(checkpointer=saver)

            state_user_a = create_initial_state("checkout-api pods restarting", session_id="SES-user-a")
            state_user_b = create_initial_state("payments-worker consumer lag", session_id="SES-user-b")
            graph.invoke(state_user_a, {"configurable": {"thread_id": state_user_a["thread_id"]}})
            graph.invoke(state_user_b, {"configurable": {"thread_id": state_user_b["thread_id"]}})

            service = get_memory_service()
            threads_a = service.list_threads_for_session("SES-user-a")
            threads_b = service.list_threads_for_session("SES-user-b")

            assert [t.thread_id for t in threads_a] == [state_user_a["thread_id"]]
            assert [t.thread_id for t in threads_b] == [state_user_b["thread_id"]]

    def test_same_session_multiple_incidents_all_listed(self, tmp_path) -> None:
        db_path = str(tmp_path / "checkpoints.sqlite")

        with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
            saver = build_checkpointer(db_path)
            graph = build_incident_graph(checkpointer=saver)

            state_1 = create_initial_state("first incident", session_id="SES-repeat-user")
            state_2 = create_initial_state("second incident", session_id="SES-repeat-user")
            graph.invoke(state_1, {"configurable": {"thread_id": state_1["thread_id"]}})
            graph.invoke(state_2, {"configurable": {"thread_id": state_2["thread_id"]}})

            threads = get_memory_service().list_threads_for_session("SES-repeat-user")
            assert {t.thread_id for t in threads} == {state_1["thread_id"], state_2["thread_id"]}
