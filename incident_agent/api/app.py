"""FastAPI application factory.

Builds exactly one compiled graph at startup (via a `lifespan` context
manager, FastAPI's recommended replacement for the deprecated
`@app.on_event("startup")`) backed by the real SQLite checkpointer, and
stores it on `app.state` for `api/dependencies.get_incident_controller`
to wrap in a fresh `IncidentController` per request. Exception handlers
here are what turns internal exception types (`IncidentNotFoundError`,
`LLMProviderNotConfiguredError`, `AgentExecutionError`) into the
"Graceful Errors" the error-handling requirements call for -- a client
never sees a raw Python traceback.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from incident_agent.agents.base import AgentExecutionError
from incident_agent.api.routers.incidents import router as incidents_router
from incident_agent.config.logging_config import configure_logging, get_logger
from incident_agent.config.settings import get_settings
from incident_agent.controllers.incident_controller import IncidentNotFoundError
from incident_agent.graphs.main_graph import build_incident_graph
from incident_agent.services.checkpointer import get_checkpointer
from incident_agent.services.llm_factory import LLMProviderNotConfiguredError

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_data_directories()
    app.state.graph = build_incident_graph(checkpointer=get_checkpointer())
    logger.info("incident_graph_ready", extra={"environment": settings.environment})
    yield


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Enterprise Incident Resolution Agent -- multi-agent LangGraph incident investigation API.",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(IncidentNotFoundError)
    async def _handle_not_found(_: Request, exc: IncidentNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(LLMProviderNotConfiguredError)
    async def _handle_no_provider(_: Request, exc: LLMProviderNotConfiguredError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)})

    @app.exception_handler(AgentExecutionError)
    async def _handle_agent_failure(_: Request, exc: AgentExecutionError) -> JSONResponse:
        logger.error("unhandled_agent_execution_error", extra={"agent_name": exc.agent_name, "error": str(exc)})
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": f"The '{exc.agent_name}' agent failed after exhausting retries/fallbacks."},
        )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(incidents_router)

    return app
