"""Knowledge Graph node -- one branch of the parallel evidence-gathering
subgraph. Reasons over the static service-dependency map
(`services/dependency_graph.py`) to characterize blast radius.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.knowledge_graph import KnowledgeGraphAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.node_runner import run_node
from incident_agent.nodes.target_inference import infer_target_name
from incident_agent.services.dependency_graph import get_dependency_context


def knowledge_graph_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        task = state.get("current_task")
        target = infer_target_name(state)
        graph_context = get_dependency_context(target)

        agent = get_agent(KnowledgeGraphAgent)
        result = agent.invoke(
            task_description=task.description if task else "Assess blast radius of the affected component.",
            graph_context=graph_context,
        )

        updates: dict[str, Any] = {
            "reasoning": [
                ReasoningStep(
                    node_name="knowledge_graph",
                    content=(
                        f"{result.summary} | related_entities={result.related_entities} | "
                        f"relationships={result.relationships} | confidence={result.confidence}"
                    ),
                )
            ],
        }
        return updates, result.summary

    return run_node("knowledge_graph", work)
