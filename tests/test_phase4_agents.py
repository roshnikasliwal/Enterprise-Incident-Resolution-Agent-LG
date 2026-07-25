"""Phase 4 tests: the LLM provider factory and every agent's wiring.

No real network/API calls are made anywhere in this suite -- provider
construction (Anthropic/OpenAI/Azure SDK client objects) does not itself
call out to the network, only *using* the client does, and every agent
test injects a fake `Runnable` in place of a real LLM. This is the
"Mock LLM Tests" pattern applied from Phase 4 onward, not deferred
entirely to Phase 11.
"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from incident_agent.agents.base import AgentExecutionError, BaseAgent
from incident_agent.agents.registry import AGENT_REGISTRY, get_agent_class
from incident_agent.config.settings import Settings
from incident_agent.prompts.common import build_agent_prompt
from incident_agent.schemas.analysis import (
    KnowledgeGraphResult,
    LogAnalysisResult,
    MetricsAnalysisResult,
    SQLAgentOutput,
    WebSearchResult,
)
from incident_agent.schemas.critique import CriticFeedback, ValidationResult
from incident_agent.schemas.final import FinalAnswer
from incident_agent.schemas.human import ApprovalRequestSummary
from incident_agent.schemas.intent import IntentClassification
from incident_agent.schemas.planning import ExecutionPlan, PlanTask
from incident_agent.schemas.reflection import ReflectionOutput
from incident_agent.schemas.report import IncidentReport
from incident_agent.schemas.resolution import DraftAnswer, ResolutionStep
from incident_agent.schemas.retrieval import RetrievalQueryPlan
from incident_agent.schemas.root_cause import RootCauseAnalysis
from incident_agent.schemas.tool_selection import ToolSelectionDecision
from incident_agent.services.llm_factory import LLMClientFactory, LLMProviderNotConfiguredError


@pytest.mark.unit
class TestLLMClientFactory:
    def test_raises_when_no_provider_has_credentials(self) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        factory = LLMClientFactory(settings)
        with pytest.raises(LLMProviderNotConfiguredError):
            factory.build_structured_llm(IntentClassification)

    def test_builds_when_only_primary_is_configured(self) -> None:
        settings = Settings(_env_file=None, anthropic={"api_key": "sk-ant-test-dummy"})  # type: ignore[call-arg]
        factory = LLMClientFactory(settings)
        chain = factory.build_structured_llm(IntentClassification)
        assert chain is not None

    def test_builds_fallback_chain_when_multiple_providers_configured(self) -> None:
        settings = Settings(  # type: ignore[call-arg]
            _env_file=None,
            anthropic={"api_key": "sk-ant-test-dummy"},
            openai={"api_key": "sk-test-dummy"},
        )
        factory = LLMClientFactory(settings)
        chain = factory.build_structured_llm(IntentClassification)
        assert chain is not None

    def test_configured_provider_order_excludes_providers_without_credentials(self) -> None:
        settings = Settings(  # type: ignore[call-arg]
            _env_file=None,
            anthropic={"api_key": "sk-ant-test-dummy"},
            llm={"primary_provider": "anthropic", "fallback_providers": ["openai", "azure_openai"]},
        )
        factory = LLMClientFactory(settings)
        assert factory._configured_provider_order() == ["anthropic"]

    def test_build_chat_model_raises_for_unconfigured_provider(self) -> None:
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        factory = LLMClientFactory(settings)
        with pytest.raises(LLMProviderNotConfiguredError):
            factory.build_chat_model("openai")


class _EchoOutput(BaseModel):
    seen_topic: str


class _EchoAgent(BaseAgent[_EchoOutput]):
    """A minimal concrete agent used only to test BaseAgent's own behavior,
    independent of any of the 17 real agents."""

    name = "echo_test_agent"
    prompt = build_agent_prompt(
        agent_name="Echo Test Agent",
        responsibility="Echo back the topic it was given.",
        human_template="Topic: {topic}",
    )
    output_schema = _EchoOutput


@pytest.mark.unit
class TestBaseAgent:
    def test_invoke_returns_the_fake_llms_output(self) -> None:
        agent = _EchoAgent(structured_llm=RunnableLambda(lambda _: _EchoOutput(seen_topic="kafka")))
        result = agent.invoke(topic="kafka")
        assert isinstance(result, _EchoOutput)
        assert result.seen_topic == "kafka"

    def test_ainvoke_returns_the_fake_llms_output(self) -> None:
        agent = _EchoAgent(structured_llm=RunnableLambda(lambda _: _EchoOutput(seen_topic="redis")))
        result = asyncio.run(agent.ainvoke(topic="redis"))
        assert result.seen_topic == "redis"

    def test_invoke_wraps_failures_in_agent_execution_error(self) -> None:
        def _boom(_: object) -> _EchoOutput:
            raise ValueError("provider exploded")

        agent = _EchoAgent(structured_llm=RunnableLambda(_boom))
        with pytest.raises(AgentExecutionError) as excinfo:
            agent.invoke(topic="kafka")
        assert excinfo.value.agent_name == "echo_test_agent"
        assert isinstance(excinfo.value.original_error, ValueError)

    def test_missing_prompt_variable_raises_before_reaching_the_llm(self) -> None:
        agent = _EchoAgent(structured_llm=RunnableLambda(lambda _: _EchoOutput(seen_topic="x")))
        with pytest.raises(AgentExecutionError):
            agent.invoke()  # missing required `topic`


# One minimal, schema-valid instance per agent's output_schema, used as the
# fake LLM's canned return value in TestAllSeventeenAgents below.
_DUMMY_OUTPUTS: dict[str, BaseModel] = {
    "intent_detection": IntentClassification(
        category="kubernetes", urgency="high", summary="pods crash looping", confidence=0.9
    ),
    "planner": ExecutionPlan(
        incident_summary="s",
        tasks=[PlanTask(task_type="log_analysis", description="check logs")],
        rationale="r",
    ),
    "retriever": RetrievalQueryPlan(queries=["kubernetes pod crash looping"]),
    "log_analysis": LogAnalysisResult(summary="s", anomaly_count=1, confidence=0.8),
    "metrics_analysis": MetricsAnalysisResult(summary="s", trend="degrading", confidence=0.8),
    "sql_agent": SQLAgentOutput(summary="s", generated_query="SELECT 1", confidence=0.7),
    "knowledge_graph": KnowledgeGraphResult(summary="s", confidence=0.6),
    "web_search": WebSearchResult(summary="s", confidence=0.5),
    "tool_selection": ToolSelectionDecision(selected_tools=["k8s_get_pod_status"], rationale="r"),
    "root_cause_analysis": RootCauseAnalysis(root_cause="oom", evidence_summary="s", confidence=0.85),
    "incident_resolution": DraftAnswer(
        summary="s",
        resolution_steps=[ResolutionStep(order=1, action="restart")],
        risk_level="low",
        estimated_impact="none",
    ),
    "critic": CriticFeedback(overall_assessment="looks fine", approve=True),
    "validator": ValidationResult(is_valid=True, confidence_score=0.9),
    "report_generator": IncidentReport(
        title="t", executive_summary="s", root_cause="oom", resolution_summary="restarted"
    ),
    "human_approval": ApprovalRequestSummary(headline="h", recommended_action="approve"),
    "reflection": ReflectionOutput(what_went_wrong="thin evidence", should_replan=True, guidance_for_replanner="g"),
    "final_response": FinalAnswer(answer="all good now", confidence=0.9),
}


@pytest.mark.unit
class TestAllSeventeenAgents:
    def test_registry_has_exactly_seventeen_agents(self) -> None:
        assert len(AGENT_REGISTRY) == 17

    def test_dummy_outputs_cover_every_registered_agent(self) -> None:
        assert set(_DUMMY_OUTPUTS) == set(AGENT_REGISTRY)

    @pytest.mark.parametrize("agent_name", list(AGENT_REGISTRY))
    def test_agent_invokes_end_to_end_with_a_fake_llm(self, agent_name: str) -> None:
        agent_cls = get_agent_class(agent_name)
        canned_output = _DUMMY_OUTPUTS[agent_name]
        agent = agent_cls(structured_llm=RunnableLambda(lambda _: canned_output))

        dummy_inputs = {var: f"<{var}>" for var in agent.prompt.input_variables}
        result = agent.invoke(**dummy_inputs)

        assert isinstance(result, agent_cls.output_schema)
        assert result == canned_output

    def test_unknown_agent_name_raises_helpful_key_error(self) -> None:
        with pytest.raises(KeyError, match="Unknown agent 'not_a_real_agent'"):
            get_agent_class("not_a_real_agent")
