"""Agent instance cache -- and the test seam for injecting fake agents.

Nodes call `get_agent(SomeAgentClass)` rather than constructing agents
directly for two reasons:

1. **Cost**: building an agent means building an `LLMClientFactory`
   fallback/retry chain; doing that once per node call (rather than once
   per process) would be wasteful across a long-running graph with many
   invocations.
2. **Testability without credentials**: `override_agent()` lets tests
   (and the Phase 5 graph test suite) register an agent instance backed
   by a fake `Runnable` for every one of the 17 agents, so the full graph
   can be built and run end-to-end with zero API keys configured. This is
   the same dependency-injection seam `BaseAgent` was designed around in
   Phase 4, applied at the node-wiring level.
"""

from __future__ import annotations

from incident_agent.agents.base import BaseAgent

_overrides: dict[type[BaseAgent], BaseAgent] = {}
_cache: dict[type[BaseAgent], BaseAgent] = {}


def get_agent(agent_cls: type[BaseAgent]) -> BaseAgent:
    if agent_cls in _overrides:
        return _overrides[agent_cls]
    if agent_cls not in _cache:
        _cache[agent_cls] = agent_cls()
    return _cache[agent_cls]


def override_agent(agent_cls: type[BaseAgent], instance: BaseAgent) -> None:
    """Test-only hook: force `get_agent(agent_cls)` to return `instance`."""
    _overrides[agent_cls] = instance


def clear_overrides() -> None:
    _overrides.clear()


def clear_cache() -> None:
    _cache.clear()
