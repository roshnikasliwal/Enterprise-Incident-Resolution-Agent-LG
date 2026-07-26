"""Streamlit UI -- a thin client over the FastAPI backend.

Deliberately talks to the API over HTTP (not by importing `incident_agent`
directly and calling the graph in-process): this is the same boundary a
real deployment would have (UI and API as separate processes/containers,
see `docker-compose.yml`), and it keeps the UI honest about only using
the endpoints a third-party client could also use.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st
from dotenv import load_dotenv

from incident_agent.config.settings import PROJECT_ROOT

# Unlike the API process, Streamlit never loads `.env` on its own -- it's a
# separate process from `python run_api.py`/uvicorn, which pick .env up via
# pydantic-settings. Without this, API__API_KEY set in .env would be
# invisible here even though the API enforces it (401 with no way to send
# the header from the UI, since os.environ wouldn't have it).
load_dotenv(PROJECT_ROOT / ".env")

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
# A real investigation makes many sequential/parallel LLM calls across up to
# 17 agents before pausing for approval or finishing -- comfortably over 30s
# once real provider credentials are wired in (fine for the fake-agent test
# suite, not for an actual run). /incident and /approve (which can re-enter
# evidence_gathering) are the slow ones; generous enough to cover a
# replan/retry cycle too.
_TIMEOUT_SECONDS = 360.0

# Same `.env` var the API reads as `settings.api.api_key` (API__API_KEY, via
# pydantic-settings' env_nested_delimiter="__"); the UI reads it raw since it
# has no settings layer of its own. Unset -> no header sent, matching the
# API's open-by-default posture in `api/dependencies.require_api_key`.
API_KEY = os.environ.get("API__API_KEY") or None

st.set_page_config(page_title="Enterprise Incident Resolution Agent", page_icon="🛠️", layout="centered")


def _client() -> httpx.Client:
    headers = {"X-API-Key": API_KEY} if API_KEY else {}
    return httpx.Client(base_url=API_BASE_URL, timeout=_TIMEOUT_SECONDS, headers=headers)


def _post(path: str, json: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        with _client() as client:
            response = client.post(path, json=json or {})
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        st.error(f"Request failed ({exc.response.status_code}): {exc.response.json().get('detail', exc.response.text)}")
    except httpx.RequestError as exc:
        st.error(f"Could not reach the API at {API_BASE_URL}: {exc}")
    return None


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        with _client() as client:
            response = client.get(path, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        st.error(f"Request failed ({exc.response.status_code}): {exc.response.json().get('detail', exc.response.text)}")
    except httpx.RequestError as exc:
        st.error(f"Could not reach the API at {API_BASE_URL}: {exc}")
    return None


def _render_status(status: dict[str, Any]) -> None:
    st.subheader(f"Incident `{status['incident_id']}`")
    st.caption(f"thread_id: `{status['thread_id']}` | session_id: `{status['session_id']}`")

    cols = st.columns(3)
    cols[0].metric("Approval status", status["approval_status"])
    cols[1].metric("Confidence", f"{status['confidence_score']:.0%}")
    cols[2].metric("Retry count", status["retry_count"])

    if status["is_paused"] and status.get("interrupt_payload"):
        brief = status["interrupt_payload"].get("brief", {})
        st.warning(f"**Awaiting human approval** -- paused before `{status['awaiting_node']}`.")
        st.markdown(f"**{brief.get('headline', 'Review required.')}**")
        for point in brief.get("key_points", []):
            st.markdown(f"- {point}")
        if brief.get("risk_callouts"):
            st.markdown("**Risk callouts:**")
            for risk in brief["risk_callouts"]:
                st.markdown(f"- :warning: {risk}")
        st.caption(f"Agent recommendation: **{brief.get('recommended_action', 'n/a')}**")

        comments = st.text_input("Comments (optional)", key=f"comments_{status['thread_id']}")
        approve_col, reject_col = st.columns(2)
        if approve_col.button("Approve", type="primary", key=f"approve_{status['thread_id']}"):
            updated = _post(f"/approve/{status['thread_id']}", {"comments": comments or None})
            if updated:
                st.session_state["last_status"] = updated
                st.rerun()
        if reject_col.button("Reject", key=f"reject_{status['thread_id']}"):
            updated = _post(f"/reject/{status['thread_id']}", {"comments": comments or None})
            if updated:
                st.session_state["last_status"] = updated
                st.rerun()
    elif status.get("final_answer"):
        st.success("Investigation complete.")
        st.markdown(status["final_answer"]["answer"])
        if status["final_answer"].get("follow_up_recommendations"):
            st.markdown("**Follow-up recommendations:**")
            for rec in status["final_answer"]["follow_up_recommendations"]:
                st.markdown(f"- {rec}")
    elif status["is_paused"]:
        st.info(f"Paused before `{status['awaiting_node']}` (no human decision required here -- resume to continue).")
        if st.button("Resume", key=f"resume_{status['thread_id']}"):
            updated = _post(f"/resume/{status['thread_id']}", {})
            if updated:
                st.session_state["last_status"] = updated
                st.rerun()


def main() -> None:
    st.title("🛠️ Enterprise Incident Resolution Agent")
    st.caption("Multi-agent LangGraph incident investigation, with human approval before any resolution is finalized.")

    if "session_id" not in st.session_state:
        st.session_state["session_id"] = None

    with st.sidebar:
        st.header("Session")
        session_id_input = st.text_input(
            "Session ID (optional -- leave blank for a new one)", value=st.session_state.get("session_id") or ""
        )
        if st.button("Load history"):
            if session_id_input:
                history = _get("/history", {"session_id": session_id_input})
                if history:
                    st.session_state["history"] = history["incidents"]
        for item in st.session_state.get("history", []):
            if st.button(f"{item['incident_id']} -- {item.get('approval_status', '?')}", key=item["thread_id"]):
                status = _get(f"/status/{item['thread_id']}")
                if status:
                    st.session_state["last_status"] = status

    user_query = st.text_area(
        "Describe the incident",
        placeholder="e.g. My Kubernetes deployment keeps restarting.",
        height=100,
    )
    if st.button("Start investigation", type="primary", disabled=not user_query.strip()):
        payload = {"user_query": user_query, "session_id": session_id_input or None}
        status = _post("/incident", payload)
        if status:
            st.session_state["session_id"] = status["session_id"]
            st.session_state["last_status"] = status

    if st.session_state.get("last_status"):
        st.divider()
        _render_status(st.session_state["last_status"])


main()
