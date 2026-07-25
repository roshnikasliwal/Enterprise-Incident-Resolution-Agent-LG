"""Phase 2 tests: state, domain models/schemas, and prompts.

The most important test here is `TestStateReducers` -- it compiles a real,
tiny `StateGraph` with two parallel branches to prove the `Annotated`
reducers on `IncidentState` actually merge concurrent writes the way we
designed them to, rather than just asserting on Python type hints in the
abstract.
"""

from __future__ import annotations

import importlib
import pkgutil
from datetime import datetime, timezone

import pytest
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

import incident_agent.prompts as prompts_package
from incident_agent.graphs.state import IncidentState, create_initial_state
from incident_agent.models.enums import ApprovalStatus, IncidentCategory, IncidentUrgency
from incident_agent.models.execution import ExecutionHistoryEntry
from incident_agent.models.tool_results import LogEntry
from incident_agent.schemas.critique import ValidationResult
from incident_agent.schemas.human import HumanFeedback
from incident_agent.schemas.intent import IntentClassification
from incident_agent.schemas.planning import ExecutionPlan, PlanTask
from incident_agent.schemas.resolution import DraftAnswer, ResolutionStep
from incident_agent.utils.reducers import merge_dicts


@pytest.mark.unit
class TestCreateInitialState:
    def test_generates_ids_when_not_supplied(self) -> None:
        state = create_initial_state("my pods keep restarting")
        assert state["thread_id"].startswith("THR-")
        assert state["session_id"].startswith("SES-")
        assert state["incident_id"].startswith("INC-")
        assert state["user_query"] == "my pods keep restarting"

    def test_honors_supplied_ids(self) -> None:
        state = create_initial_state("q", thread_id="THR-fixed", session_id="SES-fixed", incident_id="INC-fixed")
        assert state["thread_id"] == "THR-fixed"
        assert state["session_id"] == "SES-fixed"
        assert state["incident_id"] == "INC-fixed"

    def test_accumulating_fields_start_empty_and_scalars_have_safe_defaults(self) -> None:
        state = create_initial_state("q")
        for key in (
            "retrieved_documents",
            "tool_results",
            "logs",
            "metrics",
            "sql_results",
            "reasoning",
            "execution_history",
            "citations",
            "errors",
        ):
            assert state[key] == []  # type: ignore[literal-required]
        assert state["retry_count"] == 0
        assert state["confidence_score"] == 0.0
        assert state["approval_status"] == ApprovalStatus.PENDING
        assert state["metadata"] == {}


@pytest.mark.unit
class TestMergeDictsReducer:
    def test_merges_disjoint_keys(self) -> None:
        assert merge_dicts({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_right_hand_wins_on_conflict(self) -> None:
        assert merge_dicts({"a": 1}, {"a": 2}) == {"a": 2}

    def test_handles_empty_dicts(self) -> None:
        assert merge_dicts({}, {"a": 1}) == {"a": 1}
        assert merge_dicts({"a": 1}, {}) == {"a": 1}


@pytest.mark.graph
class TestStateReducersUnderRealLangGraph:
    """Compiles an actual StateGraph to prove Annotated reducers merge
    correctly, including when two branches write in the same super-step."""

    def test_parallel_branches_accumulate_lists_and_merge_metadata(self) -> None:
        def branch_a(state: IncidentState) -> dict:
            return {
                "logs": [
                    LogEntry(
                        timestamp=datetime.now(timezone.utc),
                        source="pod-a",
                        severity="error",
                        message="boom",
                    )
                ],
                "metadata": {"branch_a_ran": True},
            }

        def branch_b(state: IncidentState) -> dict:
            return {
                "metrics": [],
                "metadata": {"branch_b_ran": True},
            }

        builder = StateGraph(IncidentState)
        builder.add_node("branch_a", branch_a)
        builder.add_node("branch_b", branch_b)
        builder.add_edge(START, "branch_a")
        builder.add_edge(START, "branch_b")
        builder.add_edge("branch_a", END)
        builder.add_edge("branch_b", END)
        graph = builder.compile()

        result = graph.invoke(create_initial_state("pods restarting"))

        assert len(result["logs"]) == 1
        assert result["logs"][0].source == "pod-a"
        assert result["metadata"] == {"branch_a_ran": True, "branch_b_ran": True}

    def test_sequential_writes_to_execution_history_accumulate_not_overwrite(self) -> None:
        def make_node(node_name: str):
            def node(state: IncidentState) -> dict:
                return {
                    "execution_history": [
                        ExecutionHistoryEntry(
                            node_name=node_name,
                            status="completed",
                            started_at=datetime.now(timezone.utc),
                            summary=f"{node_name} finished",
                        )
                    ]
                }

            return node

        builder = StateGraph(IncidentState)
        builder.add_node("first", make_node("first"))
        builder.add_node("second", make_node("second"))
        builder.add_edge(START, "first")
        builder.add_edge("first", "second")
        builder.add_edge("second", END)
        graph = builder.compile()

        result = graph.invoke(create_initial_state("q"))

        assert [e.node_name for e in result["execution_history"]] == ["first", "second"]


@pytest.mark.unit
class TestSchemaValidation:
    def test_intent_classification_rejects_out_of_range_confidence(self) -> None:
        with pytest.raises(ValidationError):
            IntentClassification(
                category=IncidentCategory.KUBERNETES,
                urgency=IncidentUrgency.HIGH,
                summary="pods crash looping",
                confidence=1.5,
            )

    def test_execution_plan_requires_at_least_one_task(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionPlan(incident_summary="s", tasks=[], rationale="r")

    def test_plan_task_auto_generates_id(self) -> None:
        task = PlanTask(task_type="log_analysis", description="check logs")
        assert task.task_id.startswith("TSK-")

    def test_draft_answer_requires_at_least_one_resolution_step(self) -> None:
        with pytest.raises(ValidationError):
            DraftAnswer(summary="s", resolution_steps=[], risk_level="low", estimated_impact="none")

        # Sanity check the happy path also validates cleanly.
        DraftAnswer(
            summary="restart the deployment",
            resolution_steps=[ResolutionStep(order=1, action="kubectl rollout restart deployment/api")],
            risk_level="low",
            estimated_impact="brief rolling restart, no downtime",
        )

    def test_human_feedback_round_trips_modified_plan(self) -> None:
        plan = ExecutionPlan(
            incident_summary="s",
            tasks=[PlanTask(task_type="log_analysis", description="d")],
            rationale="r",
        )
        feedback = HumanFeedback(decision=ApprovalStatus.MODIFIED, modified_plan=plan)
        assert feedback.modified_plan is not None
        assert feedback.modified_plan.tasks[0].task_type == "log_analysis"

    def test_validation_result_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ValidationResult(is_valid=True, confidence_score=-0.1)


@pytest.mark.unit
class TestPrompts:
    """Every prompt module must expose exactly one `ChatPromptTemplate` whose
    `human` template can be rendered with the variables the corresponding
    Phase 4 agent is expected to supply."""

    EXPECTED_PROMPT_MODULES = {
        "intent_detection": "INTENT_DETECTION_PROMPT",
        "planner": "PLANNER_PROMPT",
        "retriever": "RETRIEVER_PROMPT",
        "log_analysis": "LOG_ANALYSIS_PROMPT",
        "metrics_analysis": "METRICS_ANALYSIS_PROMPT",
        "sql_agent": "SQL_AGENT_PROMPT",
        "knowledge_graph": "KNOWLEDGE_GRAPH_PROMPT",
        "web_search": "WEB_SEARCH_PROMPT",
        "tool_selection": "TOOL_SELECTION_PROMPT",
        "root_cause": "ROOT_CAUSE_PROMPT",
        "incident_resolution": "INCIDENT_RESOLUTION_PROMPT",
        "critic": "CRITIC_PROMPT",
        "validator": "VALIDATOR_PROMPT",
        "report_generator": "REPORT_GENERATOR_PROMPT",
        "human_approval": "HUMAN_APPROVAL_PROMPT",
        "reflection": "REFLECTION_PROMPT",
        "final_response": "FINAL_RESPONSE_PROMPT",
    }

    def test_all_seventeen_agent_prompts_exist_and_render(self) -> None:
        for module_name, constant_name in self.EXPECTED_PROMPT_MODULES.items():
            module = importlib.import_module(f"incident_agent.prompts.{module_name}")
            prompt = getattr(module, constant_name)
            dummy_values = {var: f"<{var}>" for var in prompt.input_variables}
            messages = prompt.format_messages(**dummy_values)
            assert len(messages) == 2  # system + human
            assert messages[0].type == "system"
            assert messages[1].type == "human"
            assert "Enterprise Incident Resolution Agent" in messages[0].content

    def test_no_stray_prompt_modules_are_missing_from_the_expected_set(self) -> None:
        discovered = {
            module_info.name
            for module_info in pkgutil.iter_modules(prompts_package.__path__)
            if module_info.name not in {"common"}
        }
        assert discovered == set(self.EXPECTED_PROMPT_MODULES)
