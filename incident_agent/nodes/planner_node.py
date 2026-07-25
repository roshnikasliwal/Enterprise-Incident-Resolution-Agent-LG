"""Planner node -- produces the execution plan the evidence-gathering
subgraph fans out over. Also the re-entry point of the retry cycle: when
`reflection_node` routes back here, `_latest_reflection_guidance()` picks
up its guidance from the reasoning trace so the same node serves both the
first-attempt and replan paths without a separate code path.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.planner import PlannerAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_intent, format_memory_context
from incident_agent.nodes.node_runner import run_node


def _latest_reflection_guidance(reasoning: list[ReasoningStep]) -> str:
    reflections = [r for r in reasoning if r.node_name == "reflection"]
    return reflections[-1].content if reflections else ""


def planner_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        agent = get_agent(PlannerAgent)
        result = agent.invoke(
            user_query=state["user_query"],
            intent=format_intent(state.get("intent")),
            memory_context=format_memory_context(state.get("memory")),
            replanning_guidance=_latest_reflection_guidance(state.get("reasoning", [])),
        )
        task_types = [t.task_type.value for t in result.tasks]
        updates: dict[str, Any] = {
            "plan": result,
            "current_task": None,
            "reasoning": [
                ReasoningStep(node_name="planner", content=f"Planned tasks {task_types}: {result.rationale}")
            ],
        }
        return updates, f"planned {len(result.tasks)} task(s): {task_types}"

    return run_node("planner", work)
