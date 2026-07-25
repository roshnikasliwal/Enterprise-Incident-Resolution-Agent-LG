"""Best-effort extraction of a concrete pod/service/topic name to
investigate, since the user's natural-language report ("my Kubernetes
deployment keeps restarting") rarely names one explicitly.

Falls back to `checkout-api` -- the service the seeded mock database
(`services.mock_database`) and knowledge-base runbooks already have
consistent data for -- so a demo run without an explicit name still
produces a coherent, cross-tool-corroborated investigation instead of
disconnected fake data pulled from unrelated random names. This is a
deliberate, honest simplification: a production system would resolve
this from the user's session context, an alerting payload, or a
follow-up clarifying question, none of which exist in this project's
scope.
"""

from __future__ import annotations

from incident_agent.graphs.state import IncidentState

DEFAULT_TARGET_COMPONENT = "checkout-api"


def infer_target_name(state: IncidentState) -> str:
    intent = state.get("intent")
    if intent and intent.keywords:
        for keyword in intent.keywords:
            if "-" in keyword or "_" in keyword:
                return keyword
    return DEFAULT_TARGET_COMPONENT
