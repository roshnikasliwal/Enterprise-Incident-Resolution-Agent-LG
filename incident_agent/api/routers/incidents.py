"""Incident endpoints: POST /incident, GET /status/{thread_id},
GET /history, POST /resume/{thread_id}, POST /approve/{thread_id},
POST /reject/{thread_id}.

Route handlers are `async def` (FastAPI's native, non-blocking request
handling) but `IncidentController`'s methods are synchronous (LangGraph's
`.invoke()`/`.get_state()` do blocking I/O against the checkpointer).
Rather than duplicating every controller method into sync/async pairs,
each handler offloads its one blocking call to Starlette's thread pool
via `run_in_threadpool` -- the standard, idiomatic way to keep a FastAPI
event loop responsive around a synchronous dependency, and the same
tradeoff any FastAPI app makes around a blocking ORM or SDK call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.concurrency import run_in_threadpool

from incident_agent.api.dependencies import get_incident_controller, require_api_key
from incident_agent.controllers.incident_controller import IncidentController, IncidentNotFoundError
from incident_agent.memory.memory_service import get_memory_service
from incident_agent.models.enums import ApprovalStatus
from incident_agent.schemas.api import (
    ApproveRequest,
    HistoryItem,
    HistoryResponse,
    IncidentRequest,
    IncidentStatusResponse,
    RejectRequest,
    ResumeRequest,
)

router = APIRouter(tags=["incidents"], dependencies=[Depends(require_api_key)])


def _status_response(controller: IncidentController, thread_id: str) -> IncidentStatusResponse:
    snapshot = controller.get_snapshot(thread_id)
    state = snapshot.values
    interrupt_payload = snapshot.interrupts[0].value if snapshot.interrupts else None
    return IncidentStatusResponse(
        thread_id=state["thread_id"],
        session_id=state["session_id"],
        incident_id=state["incident_id"],
        user_query=state["user_query"],
        approval_status=state["approval_status"],
        is_paused=len(snapshot.next) > 0,
        awaiting_node=snapshot.next[0] if snapshot.next else None,
        confidence_score=state["confidence_score"],
        retry_count=state["retry_count"],
        error_count=len(state.get("errors", [])),
        final_answer=state.get("final_answer"),
        interrupt_payload=interrupt_payload,
    )


def _not_found(thread_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No incident found for thread_id '{thread_id}'.")


@router.post("/incident", response_model=IncidentStatusResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentRequest, controller: IncidentController = Depends(get_incident_controller)
) -> IncidentStatusResponse:
    """Start a new incident investigation. Runs synchronously up to the
    first pause (typically the human-approval interrupt) or completion."""
    state = await run_in_threadpool(controller.start_investigation, payload.user_query, session_id=payload.session_id)
    return await run_in_threadpool(_status_response, controller, state["thread_id"])


@router.get("/status/{thread_id}", response_model=IncidentStatusResponse)
async def get_incident_status(
    thread_id: str, controller: IncidentController = Depends(get_incident_controller)
) -> IncidentStatusResponse:
    try:
        return await run_in_threadpool(_status_response, controller, thread_id)
    except IncidentNotFoundError:
        raise _not_found(thread_id) from None


@router.get("/history", response_model=HistoryResponse)
async def get_incident_history(
    session_id: str = Query(..., description="The session whose past incidents/threads to list."),
    controller: IncidentController = Depends(get_incident_controller),
) -> HistoryResponse:
    def _load() -> list[HistoryItem]:
        service = get_memory_service()
        items: list[HistoryItem] = []
        for record in service.list_threads_for_session(session_id):
            item = HistoryItem(
                thread_id=record.thread_id, incident_id=record.incident_id, created_at=record.created_at
            )
            try:
                state = controller.get_status(record.thread_id)
                item = item.model_copy(
                    update={"approval_status": state["approval_status"], "user_query": state["user_query"]}
                )
            except IncidentNotFoundError:
                pass  # registered but no checkpoint (e.g. a very old/pruned run) -- list it anyway, minimally
            items.append(item)
        return items

    incidents = await run_in_threadpool(_load)
    return HistoryResponse(session_id=session_id, incidents=incidents)


@router.post("/resume/{thread_id}", response_model=IncidentStatusResponse)
async def resume_incident(
    thread_id: str,
    _payload: ResumeRequest,
    controller: IncidentController = Depends(get_incident_controller),
) -> IncidentStatusResponse:
    """Continue a run paused at a *static* interrupt_before/after point."""
    try:
        await run_in_threadpool(controller.resume, thread_id)
        return await run_in_threadpool(_status_response, controller, thread_id)
    except IncidentNotFoundError:
        raise _not_found(thread_id) from None


@router.post("/approve/{thread_id}", response_model=IncidentStatusResponse)
async def approve_incident(
    thread_id: str,
    payload: ApproveRequest,
    controller: IncidentController = Depends(get_incident_controller),
) -> IncidentStatusResponse:
    """Approve, or approve-with-modification (Modify State / Edit Plan /
    Retry / Skip Tool), the pending human-approval decision."""
    try:
        if payload.modified_plan is not None:
            await run_in_threadpool(
                controller.edit_plan_and_retry, thread_id, payload.modified_plan, comments=payload.comments
            )
        elif payload.modified_draft_answer is not None:
            await run_in_threadpool(
                controller.modify_draft_answer, thread_id, payload.modified_draft_answer, comments=payload.comments
            )
        else:
            await run_in_threadpool(controller.approve, thread_id, comments=payload.comments)
        return await run_in_threadpool(_status_response, controller, thread_id)
    except IncidentNotFoundError:
        raise _not_found(thread_id) from None


@router.post("/reject/{thread_id}", response_model=IncidentStatusResponse)
async def reject_incident(
    thread_id: str,
    payload: RejectRequest,
    controller: IncidentController = Depends(get_incident_controller),
) -> IncidentStatusResponse:
    try:
        await run_in_threadpool(controller.reject, thread_id, comments=payload.comments)
        return await run_in_threadpool(_status_response, controller, thread_id)
    except IncidentNotFoundError:
        raise _not_found(thread_id) from None
