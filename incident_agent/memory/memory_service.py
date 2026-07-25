"""`MemoryService` -- a Facade over the four repositories, giving nodes
exactly two operations: `recall()` (start of a run) and the persist
methods `save_memory_node` calls (end of a run). Nodes never touch a
repository directly, which keeps `graphs/state`-awareness entirely out
of `memory/` (repositories only ever see domain models, never
`IncidentState`).
"""

from __future__ import annotations

from functools import lru_cache

from incident_agent.config.settings import get_settings
from incident_agent.memory.conversation import ConversationRepository, SqliteConversationRepository
from incident_agent.memory.episodic import EPISODIC_COLLECTION_NAME, ChromaEpisodicMemoryRepository, EpisodicMemoryRepository
from incident_agent.memory.fixes import FixRepository, SqliteFixRepository
from incident_agent.memory.preferences import PreferenceRepository, SqlitePreferenceRepository
from incident_agent.memory.structured_store import get_connection
from incident_agent.models.enums import IncidentCategory
from incident_agent.models.memory import MemoryContext, PastIncidentRecord
from incident_agent.services.vector_store import VectorStoreService


class MemoryService:
    def __init__(
        self,
        *,
        episodic: EpisodicMemoryRepository,
        preferences: PreferenceRepository,
        fixes: FixRepository,
        conversations: ConversationRepository,
    ) -> None:
        self._episodic = episodic
        self._preferences = preferences
        self._fixes = fixes
        self._conversations = conversations

    def recall(self, *, user_query: str, category: IncidentCategory | None, session_id: str) -> MemoryContext:
        """Everything worth injecting into a fresh run's context, gathered
        once up front. `category` is optional since recall can happen before
        intent classification narrows it (frequent-fix lookup is simply
        skipped in that case, not an error)."""
        return MemoryContext(
            similar_past_incidents=self._episodic.find_similar(user_query, k=3),
            frequent_fixes=self._fixes.get_frequent_fixes(category, k=3) if category else [],
            user_preferences=self._preferences.get_preferences(session_id),
            conversation_summary=self._conversations.get_summary(session_id),
        )

    def persist_incident(self, record: PastIncidentRecord) -> None:
        self._episodic.add_incident(record)

    def record_fix_usage(self, category: IncidentCategory, description: str) -> None:
        self._fixes.record_fix_usage(category, description)

    def update_conversation(self, *, session_id: str, incident_id: str, user_query: str, resolution_summary: str) -> None:
        self._conversations.append_incident(session_id, incident_id, user_query, resolution_summary)

    def set_preference(self, session_id: str, key: str, value: str) -> None:
        self._preferences.set_preference(session_id, key, value)


_override: MemoryService | None = None


def override_memory_service(service: MemoryService) -> None:
    """Test-only hook: force `get_memory_service()` to return `service` --
    e.g. one built from a `tmp_path` SQLite connection and Chroma directory,
    so graph tests (Phase 5/6) never read/write the real project data
    directory. Mirrors `nodes.agent_cache.override_agent()`.
    """
    global _override
    _override = service


def clear_memory_service_override() -> None:
    global _override
    _override = None


@lru_cache(maxsize=1)
def _build_default_memory_service() -> MemoryService:
    settings = get_settings()
    settings.ensure_data_directories()
    connection = get_connection()
    vector_store = VectorStoreService(
        persist_directory=settings.chroma.persist_directory,
        collection_name=EPISODIC_COLLECTION_NAME,
    )
    return MemoryService(
        episodic=ChromaEpisodicMemoryRepository(vector_store),
        preferences=SqlitePreferenceRepository(connection),
        fixes=SqliteFixRepository(connection),
        conversations=SqliteConversationRepository(connection),
    )


def get_memory_service() -> MemoryService:
    """Process-wide singleton wired to the real SQLite/Chroma backends,
    unless a test has installed an override."""
    return _override or _build_default_memory_service()
