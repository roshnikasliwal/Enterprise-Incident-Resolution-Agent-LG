"""Integration Tests: the full story, end to end, through the real HTTP
API -- not a phase in isolation.

Every other test file in this suite is scoped to one layer (tools,
agents, the graph, memory, checkpointing, HITL, the API). This file's
job is different: prove those layers actually cohere into one working
system by driving a single incident through every stage a real user
session would hit -- creation, a low-confidence retry cycle, a human
edit-plan-and-retry, final approval, report generation, memory
persistence, and a durability check across a simulated process restart
-- all through `POST`/`GET` calls against the FastAPI app, the same
interface a real client uses.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from incident_agent.api.app import create_app
from incident_agent.api.dependencies import get_incident_controller, require_api_key
from incident_agent.controllers.incident_controller import IncidentController
from incident_agent.graphs.main_graph import build_incident_graph
from incident_agent.schemas.planning import ExecutionPlan, PlanTask
from incident_agent.services.checkpointer import build_checkpointer

from ._graph_fakes import install_fake_agents

logging.getLogger("langgraph.checkpoint.serde.jsonplus").setLevel(logging.ERROR)


@pytest.mark.integration
class TestFullIncidentLifecycleThroughTheAPI:
    def test_create_retry_edit_plan_approve_report_history_and_durability(self, tmp_path) -> None:
        db_path = str(tmp_path / "checkpoints.sqlite")

        # --- Stage 1: create the app against a real (tmp) SQLite checkpointer,
        # with a validator that's low-confidence on the first pass and high on
        # the second -- forcing the automated retry cycle to actually run.
        with install_fake_agents(
            validator_confidences=(0.4, 0.9),
            critic_approvals=(True, True),
            plan_task_types=["log_analysis", "metrics_analysis"],
        ):
            saver = build_checkpointer(db_path)
            graph = build_incident_graph(checkpointer=saver)
            app = create_app()
            app.dependency_overrides[get_incident_controller] = lambda: IncidentController(graph)
            app.dependency_overrides[require_api_key] = lambda: None
            client = TestClient(app)

            created = client.post(
                "/incident", json={"user_query": "checkout-api pods keep restarting", "session_id": "SES-integration"}
            ).json()
            thread_id = created["thread_id"]

            # The automated confidence-check/reflection cycle ran once
            # (0.4 -> retry -> 0.9) before ever reaching the human gate.
            assert created["retry_count"] == 1
            assert created["is_paused"] is True
            assert created["awaiting_node"] == "human_approval"
            assert created["interrupt_payload"]["kind"] == "approval_request"

            status = client.get(f"/status/{thread_id}").json()
            assert status["retry_count"] == 1

            # --- Stage 2: the human isn't satisfied either -- edits the plan
            # to drop metrics_analysis and re-run evidence gathering (Edit
            # Plan / Retry / Skip Tool, all in one action).
            current_plan = ExecutionPlan(
                incident_summary="checkout-api pods crash looping, suspected OOM",
                rationale="focus purely on logs after two inconclusive passes",
                tasks=[PlanTask(task_type="log_analysis", description="re-check logs only")],
            )
            edited = client.post(
                f"/approve/{thread_id}",
                json={"comments": "skip metrics, focus on logs", "modified_plan": current_plan.model_dump(mode="json")},
            ).json()
            assert edited["retry_count"] == 2
            assert edited["is_paused"] is True  # back at human_approval again

            # --- Stage 3: approve for real this time.
            approved = client.post(f"/approve/{thread_id}", json={"comments": "looks right now"}).json()
            assert approved["approval_status"] == "approved"
            assert approved["is_paused"] is False
            assert approved["final_answer"] is not None

            # --- Stage 4: GET /history proves memory persistence + the
            # thread registry (multi-user support) both actually wired up
            # end to end, not just at the unit level.
            history = client.get("/history", params={"session_id": "SES-integration"}).json()
            assert history["session_id"] == "SES-integration"
            assert any(item["thread_id"] == thread_id for item in history["incidents"])
            matching = next(item for item in history["incidents"] if item["thread_id"] == thread_id)
            assert matching["approval_status"] == "approved"

        # --- Stage 5: durability -- discard every in-process object entirely
        # and rebuild against the same SQLite file, proving the completed
        # run's state (and the ability to look it up) survives a restart.
        del graph, saver, app, client
        with install_fake_agents():
            saver_after_restart = build_checkpointer(db_path)
            graph_after_restart = build_incident_graph(checkpointer=saver_after_restart)
            controller_after_restart = IncidentController(graph_after_restart)

            final_status = controller_after_restart.get_status(thread_id)
            assert final_status["approval_status"].value == "approved"
            assert final_status["final_answer"] is not None
            node_names = [e.node_name for e in final_status["execution_history"]]
            assert "report_generator" in node_names
            assert "save_memory" in node_names
