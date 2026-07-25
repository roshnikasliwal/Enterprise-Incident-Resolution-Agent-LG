"""Phase 9 tests: the FastAPI layer, exercised through a real HTTP test
client (`fastapi.testclient.TestClient`) against the real compiled graph
(fake agents only) -- not by calling router functions directly, so
request/response validation, dependency injection, and exception
handlers are all genuinely exercised.

`TestClient(app)` is used *without* the `with` context-manager form,
which means FastAPI's lifespan (startup: `build_incident_graph(checkpointer
=get_checkpointer())`, the real settings-backed SQLite checkpointer)
never runs -- `get_incident_controller` is overridden via FastAPI's
`dependency_overrides` instead, so no test ever touches the real project
data/ directory or requires API credentials.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from incident_agent.api.app import create_app
from incident_agent.api.dependencies import get_incident_controller
from incident_agent.controllers.incident_controller import IncidentController
from incident_agent.graphs.main_graph import build_incident_graph

from ._graph_fakes import install_fake_agents

logging.getLogger("langgraph.checkpoint.serde.jsonplus").setLevel(logging.ERROR)


@pytest.fixture
def client():
    with install_fake_agents(validator_confidences=(0.9,), critic_approvals=(True,)):
        app = create_app()
        graph = build_incident_graph()
        app.dependency_overrides[get_incident_controller] = lambda: IncidentController(graph)
        yield TestClient(app)
        app.dependency_overrides.clear()


@pytest.mark.unit
def test_health_check_does_not_require_the_graph(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.graph
class TestCreateIncident:
    def test_returns_201_and_paused_status(self, client: TestClient) -> None:
        response = client.post("/incident", json={"user_query": "checkout-api pods keep restarting"})
        assert response.status_code == 201
        body = response.json()
        assert body["is_paused"] is True
        assert body["awaiting_node"] == "human_approval"
        assert body["approval_status"] == "pending"
        assert body["interrupt_payload"]["kind"] == "approval_request"

    def test_rejects_empty_user_query(self, client: TestClient) -> None:
        response = client.post("/incident", json={"user_query": ""})
        assert response.status_code == 422

    def test_honors_supplied_session_id(self, client: TestClient) -> None:
        response = client.post("/incident", json={"user_query": "q", "session_id": "SES-fixed"})
        assert response.json()["session_id"] == "SES-fixed"


@pytest.mark.graph
class TestGetStatus:
    def test_returns_current_state(self, client: TestClient) -> None:
        created = client.post("/incident", json={"user_query": "q"}).json()
        response = client.get(f"/status/{created['thread_id']}")
        assert response.status_code == 200
        assert response.json()["thread_id"] == created["thread_id"]

    def test_unknown_thread_returns_404(self, client: TestClient) -> None:
        response = client.get("/status/THR-does-not-exist")
        assert response.status_code == 404


@pytest.mark.graph
class TestApprove:
    def test_plain_approve_completes_the_run(self, client: TestClient) -> None:
        created = client.post("/incident", json={"user_query": "q"}).json()
        response = client.post(f"/approve/{created['thread_id']}", json={"comments": "go ahead"})
        assert response.status_code == 200
        body = response.json()
        assert body["approval_status"] == "approved"
        assert body["is_paused"] is False
        assert body["final_answer"] is not None

    def test_approve_with_modified_draft_answer(self, client: TestClient) -> None:
        created = client.post("/incident", json={"user_query": "q"}).json()
        modified_draft = {
            "summary": "scale replicas instead",
            "resolution_steps": [{"order": 1, "action": "scale to 5 replicas", "risk": "low"}],
            "risk_level": "low",
            "estimated_impact": "none",
        }
        response = client.post(
            f"/approve/{created['thread_id']}", json={"comments": "prefer scaling", "modified_draft_answer": modified_draft}
        )
        assert response.status_code == 200
        assert response.json()["approval_status"] == "modified"

    def test_approve_unknown_thread_returns_404(self, client: TestClient) -> None:
        response = client.post("/approve/THR-does-not-exist", json={})
        assert response.status_code == 404


@pytest.mark.graph
class TestReject:
    def test_reject_completes_without_report(self, client: TestClient) -> None:
        created = client.post("/incident", json={"user_query": "q"}).json()
        response = client.post(f"/reject/{created['thread_id']}", json={"comments": "too risky"})
        assert response.status_code == 200
        body = response.json()
        assert body["approval_status"] == "rejected"
        assert body["final_answer"]["answer"]
        assert "too risky" in body["final_answer"]["answer"]


@pytest.mark.graph
class TestHistory:
    def test_lists_incidents_for_the_session(self, client: TestClient) -> None:
        client.post("/incident", json={"user_query": "first incident", "session_id": "SES-history-test"})
        client.post("/incident", json={"user_query": "second incident", "session_id": "SES-history-test"})

        response = client.get("/history", params={"session_id": "SES-history-test"})
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "SES-history-test"
        assert len(body["incidents"]) == 2
        queries = {item["user_query"] for item in body["incidents"]}
        assert queries == {"first incident", "second incident"}

    def test_empty_for_unknown_session(self, client: TestClient) -> None:
        response = client.get("/history", params={"session_id": "SES-never-used"})
        assert response.json()["incidents"] == []

    def test_requires_session_id_query_param(self, client: TestClient) -> None:
        response = client.get("/history")
        assert response.status_code == 422


@pytest.mark.unit
class TestApiKeyAuth:
    """`require_api_key` is a plain function reading `get_settings()`
    directly (not itself a `Depends`-injected value), so it's tested as a
    unit rather than through a full app + TestClient -- simpler, and it
    still exercises the exact code path FastAPI calls as a dependency.
    """

    def test_open_by_default(self, client: TestClient) -> None:
        # No API__API_KEY configured in the default test settings -> no auth required.
        response = client.get("/health")
        assert response.status_code == 200

    def test_passes_when_no_key_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from incident_agent.api.dependencies import require_api_key
        from incident_agent.config.settings import Settings

        monkeypatch.setattr(
            "incident_agent.api.dependencies.get_settings", lambda: Settings(_env_file=None)  # type: ignore[call-arg]
        )
        require_api_key(x_api_key=None)  # must not raise

    def test_rejects_missing_or_wrong_key_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fastapi import HTTPException

        from incident_agent.api.dependencies import require_api_key
        from incident_agent.config.settings import Settings

        monkeypatch.setattr(
            "incident_agent.api.dependencies.get_settings",
            lambda: Settings(_env_file=None, api={"api_key": "test-secret-key"}),  # type: ignore[call-arg]
        )
        with pytest.raises(HTTPException) as missing:
            require_api_key(x_api_key=None)
        assert missing.value.status_code == 401

        with pytest.raises(HTTPException) as wrong:
            require_api_key(x_api_key="wrong-key")
        assert wrong.value.status_code == 401

        require_api_key(x_api_key="test-secret-key")  # must not raise
