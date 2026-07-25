"""Request-scoped FastAPI dependencies.

`get_incident_controller` reads the single graph instance built once at
app startup (see `api/app.py`'s lifespan) off `app.state` -- the graph
itself is expensive to build and perfectly safe to share across
requests (LangGraph's compiled graph is stateless; all per-run state
lives in the checkpointer, keyed by thread_id), so there is no reason to
rebuild it per request.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from incident_agent.config.settings import get_settings
from incident_agent.controllers.incident_controller import IncidentController


def get_incident_controller(request: Request) -> IncidentController:
    return IncidentController(request.app.state.graph)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """No-op when `API__API_KEY` is unset (open by default, matching this
    project's zero-config-to-run posture); enforced only once an operator
    opts in by setting one."""
    settings = get_settings()
    expected = settings.api.api_key
    if expected is None:
        return
    if x_api_key is None or x_api_key != expected.get_secret_value():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key header.")
