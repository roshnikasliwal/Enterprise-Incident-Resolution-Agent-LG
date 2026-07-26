"""Phase 6 tests: the memory layer's repositories, service facade, and
the two nodes that wire it into the graph.

Every test uses an isolated in-memory SQLite connection
(`structured_store.reset_for_tests()`) and a throwaway Chroma directory
(`tmp_path`) -- never the real project `data/` directory.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from incident_agent.graphs.state import create_initial_state
from incident_agent.memory.conversation import SqliteConversationRepository
from incident_agent.memory.episodic import ChromaEpisodicMemoryRepository
from incident_agent.memory.fixes import SqliteFixRepository
from incident_agent.memory.memory_service import (
    MemoryService,
    clear_memory_service_override,
    get_memory_service,
    override_memory_service,
)
from incident_agent.memory.preferences import SqlitePreferenceRepository
from incident_agent.memory.structured_store import reset_for_tests
from incident_agent.memory.thread_registry import SqliteThreadRegistry
from incident_agent.models.enums import IncidentCategory
from incident_agent.models.memory import PastIncidentRecord
from incident_agent.nodes.recall_memory_node import recall_memory_node
from incident_agent.nodes.save_memory_node import save_memory_node
from incident_agent.schemas.report import IncidentReport
from incident_agent.services.vector_store import UnsupportedEmbeddingModelError, VectorStoreService


@pytest.fixture
def sqlite_conn():
    return reset_for_tests()


@pytest.fixture
def episodic_repo(tmp_path) -> ChromaEpisodicMemoryRepository:
    store = VectorStoreService(persist_directory=str(tmp_path / "chroma"), collection_name="test_episodic")
    return ChromaEpisodicMemoryRepository(store)


@pytest.mark.unit
class TestVectorStoreServiceEmbeddingModelValidation:
    def test_default_embedding_model_constructs_successfully(self, tmp_path) -> None:
        VectorStoreService(persist_directory=str(tmp_path / "chroma"), collection_name="test_default_model")

    def test_unsupported_embedding_model_raises_before_touching_chroma(self, tmp_path) -> None:
        with pytest.raises(UnsupportedEmbeddingModelError, match="text-embedding-3-small"):
            VectorStoreService(
                persist_directory=str(tmp_path / "chroma"),
                collection_name="test_unsupported_model",
                embedding_model="text-embedding-3-small",
            )


@pytest.mark.unit
class TestSqlitePreferenceRepository:
    def test_round_trips_a_preference(self, sqlite_conn) -> None:
        repo = SqlitePreferenceRepository(sqlite_conn)
        repo.set_preference("SES-1", "rollback_strategy", "conservative")
        prefs = repo.get_preferences("SES-1")
        assert len(prefs) == 1
        assert prefs[0].key == "rollback_strategy"
        assert prefs[0].value == "conservative"

    def test_setting_same_key_again_overwrites_not_duplicates(self, sqlite_conn) -> None:
        repo = SqlitePreferenceRepository(sqlite_conn)
        repo.set_preference("SES-1", "k", "v1")
        repo.set_preference("SES-1", "k", "v2")
        prefs = repo.get_preferences("SES-1")
        assert len(prefs) == 1
        assert prefs[0].value == "v2"

    def test_preferences_are_scoped_per_session(self, sqlite_conn) -> None:
        repo = SqlitePreferenceRepository(sqlite_conn)
        repo.set_preference("SES-1", "k", "v1")
        repo.set_preference("SES-2", "k", "v2")
        assert repo.get_preferences("SES-1")[0].value == "v1"
        assert repo.get_preferences("SES-2")[0].value == "v2"


@pytest.mark.unit
class TestSqliteFixRepository:
    def test_repeated_fix_increments_usage_count(self, sqlite_conn) -> None:
        repo = SqliteFixRepository(sqlite_conn)
        repo.record_fix_usage(IncidentCategory.KUBERNETES, "raise memory limit")
        repo.record_fix_usage(IncidentCategory.KUBERNETES, "raise memory limit")
        repo.record_fix_usage(IncidentCategory.KUBERNETES, "raise memory limit")
        fixes = repo.get_frequent_fixes(IncidentCategory.KUBERNETES)
        assert len(fixes) == 1
        assert fixes[0].usage_count == 3

    def test_different_descriptions_are_distinct_fixes(self, sqlite_conn) -> None:
        repo = SqliteFixRepository(sqlite_conn)
        repo.record_fix_usage(IncidentCategory.KUBERNETES, "raise memory limit")
        repo.record_fix_usage(IncidentCategory.KUBERNETES, "restart the deployment")
        fixes = repo.get_frequent_fixes(IncidentCategory.KUBERNETES, k=10)
        assert len(fixes) == 2

    def test_most_used_fix_ranks_first(self, sqlite_conn) -> None:
        repo = SqliteFixRepository(sqlite_conn)
        repo.record_fix_usage(IncidentCategory.DATABASE, "add index")
        for _ in range(5):
            repo.record_fix_usage(IncidentCategory.DATABASE, "increase pool size")
        fixes = repo.get_frequent_fixes(IncidentCategory.DATABASE, k=10)
        assert fixes[0].description == "increase pool size"

    def test_fixes_are_scoped_per_category(self, sqlite_conn) -> None:
        repo = SqliteFixRepository(sqlite_conn)
        repo.record_fix_usage(IncidentCategory.KUBERNETES, "raise memory limit")
        repo.record_fix_usage(IncidentCategory.DATABASE, "add index")
        assert len(repo.get_frequent_fixes(IncidentCategory.KUBERNETES, k=10)) == 1
        assert len(repo.get_frequent_fixes(IncidentCategory.CACHE, k=10)) == 0


@pytest.mark.unit
class TestSqliteConversationRepository:
    def test_no_summary_before_any_incident(self, sqlite_conn) -> None:
        repo = SqliteConversationRepository(sqlite_conn)
        assert repo.get_summary("SES-new") is None

    def test_appending_builds_a_rolling_summary(self, sqlite_conn) -> None:
        repo = SqliteConversationRepository(sqlite_conn)
        repo.append_incident("SES-1", "INC-1", "pods crash looping", "raised memory limit")
        repo.append_incident("SES-1", "INC-2", "db is slow", "added missing index")
        summary = repo.get_summary("SES-1")
        assert "INC-1" in summary and "INC-2" in summary
        assert "raised memory limit" in summary

    def test_summary_is_capped_and_keeps_most_recent_content(self, sqlite_conn) -> None:
        repo = SqliteConversationRepository(sqlite_conn)
        for i in range(50):
            repo.append_incident("SES-1", f"INC-{i}", "q" * 50, "r" * 50)
        summary = repo.get_summary("SES-1")
        assert len(summary) <= 2000
        assert "INC-49" in summary  # most recent entry must survive the cap


@pytest.mark.unit
class TestChromaEpisodicMemoryRepository:
    def test_find_similar_returns_a_previously_added_incident(self, episodic_repo) -> None:
        record = PastIncidentRecord(
            incident_id="INC-1",
            title="checkout-api OOM crash loop",
            category=IncidentCategory.KUBERNETES,
            root_cause="memory limit too low",
            resolution_summary="raised memory limit to 1Gi",
            resolved_at=datetime.now(timezone.utc),
        )
        episodic_repo.add_incident(record)

        results = episodic_repo.find_similar("kubernetes pods crash looping out of memory", k=3)

        assert len(results) == 1
        assert results[0].incident_id == "INC-1"
        assert results[0].root_cause == "memory limit too low"
        assert results[0].resolution_summary == "raised memory limit to 1Gi"
        assert results[0].similarity_score is not None

    def test_empty_store_returns_no_results(self, episodic_repo) -> None:
        assert episodic_repo.find_similar("anything", k=3) == []


@pytest.mark.unit
class TestMemoryService:
    def _service(self, sqlite_conn, episodic_repo) -> MemoryService:
        return MemoryService(
            episodic=episodic_repo,
            preferences=SqlitePreferenceRepository(sqlite_conn),
            fixes=SqliteFixRepository(sqlite_conn),
            conversations=SqliteConversationRepository(sqlite_conn),
            threads=SqliteThreadRegistry(sqlite_conn),
        )

    def test_recall_without_category_skips_frequent_fixes(self, sqlite_conn, episodic_repo) -> None:
        service = self._service(sqlite_conn, episodic_repo)
        context = service.recall(user_query="pods crash looping", category=None, session_id="SES-1")
        assert context.frequent_fixes == []
        assert context.similar_past_incidents == []
        assert context.conversation_summary is None

    def test_recall_with_category_includes_frequent_fixes(self, sqlite_conn, episodic_repo) -> None:
        service = self._service(sqlite_conn, episodic_repo)
        service.record_fix_usage(IncidentCategory.KUBERNETES, "raise memory limit")
        context = service.recall(user_query="q", category=IncidentCategory.KUBERNETES, session_id="SES-1")
        assert len(context.frequent_fixes) == 1

    def test_persist_incident_then_recall_finds_it(self, sqlite_conn, episodic_repo) -> None:
        service = self._service(sqlite_conn, episodic_repo)
        record = PastIncidentRecord(
            incident_id="INC-1",
            title="checkout-api OOM",
            category=IncidentCategory.KUBERNETES,
            root_cause="undersized memory limit",
            resolution_summary="raised limit",
            resolved_at=datetime.now(timezone.utc),
        )
        service.persist_incident(record)
        context = service.recall(user_query="checkout-api memory issue", category=None, session_id="SES-1")
        assert any(i.incident_id == "INC-1" for i in context.similar_past_incidents)

    def test_update_conversation_then_recall_includes_summary(self, sqlite_conn, episodic_repo) -> None:
        service = self._service(sqlite_conn, episodic_repo)
        service.update_conversation(
            session_id="SES-1", incident_id="INC-1", user_query="pods restart", resolution_summary="fixed"
        )
        context = service.recall(user_query="q", category=None, session_id="SES-1")
        assert context.conversation_summary is not None
        assert "INC-1" in context.conversation_summary


@pytest.mark.unit
class TestMemoryServiceOverrideSeam:
    def test_override_takes_precedence(self, sqlite_conn, episodic_repo) -> None:
        fake = MemoryService(
            episodic=episodic_repo,
            preferences=SqlitePreferenceRepository(sqlite_conn),
            fixes=SqliteFixRepository(sqlite_conn),
            conversations=SqliteConversationRepository(sqlite_conn),
            threads=SqliteThreadRegistry(sqlite_conn),
        )
        try:
            override_memory_service(fake)
            assert get_memory_service() is fake
        finally:
            clear_memory_service_override()

    def test_clearing_falls_through_to_the_default_builder(self, sqlite_conn, episodic_repo, monkeypatch) -> None:
        # Verifies the fall-through *behavior* (override cleared -> the
        # default-builder path is consulted) without exercising the real
        # settings-backed builder, which would touch the project's actual
        # data/ directory just to prove a code path runs.
        import incident_agent.memory.memory_service as memory_service_module

        sentinel = MemoryService(
            episodic=episodic_repo,
            preferences=SqlitePreferenceRepository(sqlite_conn),
            fixes=SqliteFixRepository(sqlite_conn),
            conversations=SqliteConversationRepository(sqlite_conn),
            threads=SqliteThreadRegistry(sqlite_conn),
        )
        monkeypatch.setattr(memory_service_module, "_build_default_memory_service", lambda: sentinel)

        fake = MemoryService(
            episodic=episodic_repo,
            preferences=SqlitePreferenceRepository(sqlite_conn),
            fixes=SqliteFixRepository(sqlite_conn),
            conversations=SqliteConversationRepository(sqlite_conn),
            threads=SqliteThreadRegistry(sqlite_conn),
        )
        override_memory_service(fake)
        assert get_memory_service() is fake
        clear_memory_service_override()
        assert get_memory_service() is sentinel


@pytest.mark.unit
class TestMemoryNodes:
    def _install(self, sqlite_conn, episodic_repo) -> MemoryService:
        service = MemoryService(
            episodic=episodic_repo,
            preferences=SqlitePreferenceRepository(sqlite_conn),
            fixes=SqliteFixRepository(sqlite_conn),
            conversations=SqliteConversationRepository(sqlite_conn),
            threads=SqliteThreadRegistry(sqlite_conn),
        )
        override_memory_service(service)
        return service

    def test_recall_memory_node_populates_state_memory_field(self, sqlite_conn, episodic_repo) -> None:
        self._install(sqlite_conn, episodic_repo)
        try:
            state = create_initial_state("my checkout-api pods keep restarting")
            result = recall_memory_node(state)
            assert result["memory"] is not None
            assert result["execution_history"][0].node_name == "recall_memory"
        finally:
            clear_memory_service_override()

    def test_save_memory_node_persists_and_records_fix_usage_when_approved(self, sqlite_conn, episodic_repo) -> None:
        service = self._install(sqlite_conn, episodic_repo)
        try:
            from incident_agent.models.enums import ApprovalStatus
            from incident_agent.schemas.intent import IntentClassification
            from incident_agent.schemas.resolution import DraftAnswer, ResolutionStep

            state = create_initial_state("my checkout-api pods keep restarting")
            state["approval_status"] = ApprovalStatus.APPROVED
            state["intent"] = IntentClassification(
                category=IncidentCategory.KUBERNETES, urgency="high", summary="s", confidence=0.9
            )
            state["draft_answer"] = DraftAnswer(
                summary="raise memory limit",
                resolution_steps=[ResolutionStep(order=1, action="raise limit")],
                risk_level="low",
                estimated_impact="none",
            )
            state["metadata"] = {
                "root_cause_analysis": {"root_cause": "OOM"},
                "incident_report": IncidentReport(
                    title="t", executive_summary="s", root_cause="OOM", resolution_summary="raised memory limit"
                ).model_dump(mode="json"),
            }

            result = save_memory_node(state)
            assert result["metadata"]["memory_persisted"] is True

            context = service.recall(user_query="q", category=IncidentCategory.KUBERNETES, session_id=state["session_id"])
            assert any(f.description == "raise memory limit" for f in context.frequent_fixes)
        finally:
            clear_memory_service_override()

    def test_save_memory_node_does_not_record_fix_usage_when_rejected(self, sqlite_conn, episodic_repo) -> None:
        service = self._install(sqlite_conn, episodic_repo)
        try:
            from incident_agent.models.enums import ApprovalStatus
            from incident_agent.schemas.resolution import DraftAnswer, ResolutionStep

            state = create_initial_state("my checkout-api pods keep restarting")
            state["approval_status"] = ApprovalStatus.REJECTED
            state["draft_answer"] = DraftAnswer(
                summary="raise memory limit",
                resolution_steps=[ResolutionStep(order=1, action="raise limit")],
                risk_level="low",
                estimated_impact="none",
            )

            save_memory_node(state)
            context = service.recall(user_query="q", category=IncidentCategory.KUBERNETES, session_id=state["session_id"])
            assert context.frequent_fixes == []
        finally:
            clear_memory_service_override()
