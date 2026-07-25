"""`BaseAgent` -- the Template Method every one of the 17 agents follows.

Design rationale
-----------------
Every agent in this system does the same three things: run a prompt
through an LLM, force the response into a specific Pydantic schema, and
surface failures in one consistent shape. `BaseAgent` implements all of
that exactly once; each concrete agent (`agents/intent_detection.py`, etc.)
supplies only three class attributes -- `name`, `prompt`, `output_schema`
-- making each agent file close to declarative and trivially reviewable
("what does this agent do?" is answered by reading its prompt + schema,
not by reading control flow).

Deliberately **not** aware of `IncidentState` or LangGraph at all: agents
are pure `(inputs: dict) -> output_schema instance` units, independent of
how they're orchestrated. `nodes/` (Phase 5) is the layer that knows about
graph state and decides what to pass in / where the result goes. This
keeps agents unit-testable in isolation and reusable outside this graph.

Dependency injection for testability
--------------------------------------
The constructor accepts an already-built `structured_llm: Runnable`
instead of always reaching for the real `LLMClientFactory`. Tests inject
a trivial `RunnableLambda` that returns a canned schema instance --
exercising this class's actual logic (prompt composition, error wrapping)
without making a real network call or depending on API credentials being
configured.
"""

from __future__ import annotations

from abc import ABC
from typing import ClassVar, Generic, TypeVar

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from incident_agent.config.logging_config import get_logger
from incident_agent.services.llm_factory import LLMClientFactory

logger = get_logger(__name__)

TOutput = TypeVar("TOutput", bound=BaseModel)


class AgentExecutionError(RuntimeError):
    """Raised when an agent's LLM call fails after all retries and provider
    fallbacks configured in `LLMClientFactory` are exhausted.

    Nodes (Phase 5) catch this single exception type -- not raw provider
    SDK exceptions -- to convert a failed agent call into an `AgentError`
    appended to state, which is what lets one failed evidence-gathering
    branch degrade gracefully instead of aborting the whole graph run.
    """

    def __init__(self, agent_name: str, original_error: Exception) -> None:
        super().__init__(f"{agent_name} failed after exhausting retries/fallbacks: {original_error}")
        self.agent_name = agent_name
        self.original_error = original_error


class BaseAgent(ABC, Generic[TOutput]):
    name: ClassVar[str]
    prompt: ClassVar[ChatPromptTemplate]
    output_schema: ClassVar[type[BaseModel]]

    def __init__(self, structured_llm: Runnable | None = None) -> None:
        llm = structured_llm or LLMClientFactory().build_structured_llm(self.output_schema)
        self._chain: Runnable = (self.prompt | llm).with_config(
            {"run_name": self.name, "tags": ["agent", self.name]}
        )

    def invoke(self, **inputs: object) -> TOutput:
        try:
            result = self._chain.invoke(inputs)
        except Exception as exc:  # noqa: BLE001 -- converted to a typed error for callers
            logger.warning("agent_execution_failed", extra={"agent_name": self.name, "error": str(exc)})
            raise AgentExecutionError(self.name, exc) from exc
        return result  # type: ignore[return-value]

    async def ainvoke(self, **inputs: object) -> TOutput:
        try:
            result = await self._chain.ainvoke(inputs)
        except Exception as exc:  # noqa: BLE001 -- converted to a typed error for callers
            logger.warning("agent_execution_failed", extra={"agent_name": self.name, "error": str(exc)})
            raise AgentExecutionError(self.name, exc) from exc
        return result  # type: ignore[return-value]
