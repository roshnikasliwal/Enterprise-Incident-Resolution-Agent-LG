"""Static service-dependency map backing the Knowledge Graph Agent.

A real deployment would query an actual service catalog / dependency
graph store; this project stands in with a small, explicit static map
covering the same demo services used elsewhere (the mock Postgres
database, the seeded knowledge base). It exists specifically to give the
Knowledge Graph Agent something concrete to reason over about blast
radius -- "what else breaks if this component goes down" -- which none
of the other tools/services provide.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceNode:
    name: str
    component_type: str
    depends_on: tuple[str, ...]


SERVICE_GRAPH: tuple[ServiceNode, ...] = (
    ServiceNode("checkout-api", "application", depends_on=("postgres-primary", "redis-cache", "orders-topic")),
    ServiceNode("payments-worker", "application", depends_on=("orders-topic", "postgres-primary", "payment-gateway")),
    ServiceNode("postgres-primary", "database", depends_on=()),
    ServiceNode("postgres-replica-1", "database", depends_on=("postgres-primary",)),
    ServiceNode("redis-cache", "cache", depends_on=()),
    ServiceNode("orders-topic", "kafka", depends_on=("kafka-cluster",)),
    ServiceNode("kafka-cluster", "kafka", depends_on=()),
    ServiceNode("payment-gateway", "external", depends_on=()),
    ServiceNode("checkout-frontend", "application", depends_on=("checkout-api",)),
)

_BY_NAME = {node.name: node for node in SERVICE_GRAPH}


def get_dependents(name: str) -> list[str]:
    """Services that would be impacted (directly) if `name` were unhealthy --
    the inverse of `depends_on`, i.e. blast radius."""
    return [node.name for node in SERVICE_GRAPH if name in node.depends_on]


def get_dependency_context(component_hint: str) -> str:
    """Render a human/LLM-readable summary of the dependency graph, filtered
    around whatever component the investigation concerns (falls back to the
    full graph if the hint doesn't match any known service).
    """
    hint = component_hint.strip().lower()
    matches = [node for node in SERVICE_GRAPH if hint and hint in node.name.lower()] or list(SERVICE_GRAPH)

    lines: list[str] = []
    for node in matches:
        depends_on = ", ".join(node.depends_on) if node.depends_on else "(none)"
        dependents = get_dependents(node.name)
        dependents_str = ", ".join(dependents) if dependents else "(none)"
        lines.append(
            f"- {node.name} ({node.component_type}): depends_on=[{depends_on}]; "
            f"depended_on_by=[{dependents_str}]"
        )
    return "\n".join(lines)
