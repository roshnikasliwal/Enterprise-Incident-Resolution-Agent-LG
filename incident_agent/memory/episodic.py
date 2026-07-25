"""Episodic memory repository (Repository pattern) -- semantic recall of
past incidents.

Backed by its own Chroma collection (`episodic_incident_memory`), kept
entirely separate from the curated runbook/postmortem knowledge base
(`incident_knowledge_base`, see `services/vector_store.py`): the
knowledge base is hand-authored reference material, episodic memory is
an automatically-growing log of *this system's own* past investigations.
Conflating them would let old, possibly-wrong resolutions outrank
vetted runbooks in knowledge-base search results.
"""

from __future__ import annotations

from typing import Protocol

from incident_agent.models.documents import RetrievedDocument
from incident_agent.models.enums import IncidentCategory
from incident_agent.models.memory import PastIncidentRecord
from incident_agent.services.vector_store import VectorStoreService

EPISODIC_COLLECTION_NAME = "episodic_incident_memory"


class EpisodicMemoryRepository(Protocol):
    def add_incident(self, record: PastIncidentRecord) -> None: ...

    def find_similar(self, query: str, k: int = 3) -> list[PastIncidentRecord]: ...


class ChromaEpisodicMemoryRepository:
    def __init__(self, vector_store: VectorStoreService) -> None:
        self._store = vector_store

    def add_incident(self, record: PastIncidentRecord) -> None:
        document = RetrievedDocument(
            document_id=record.incident_id,
            source="episodic_memory",
            title=record.title,
            content=f"{record.title}\nRoot cause: {record.root_cause}\nResolution: {record.resolution_summary}",
            score=1.0,
            metadata={"category": record.category.value, "resolved_at": record.resolved_at.isoformat()},
        )
        self._store.add_documents([document])

    def find_similar(self, query: str, k: int = 3) -> list[PastIncidentRecord]:
        documents = self._store.similarity_search(query, k=k)
        records: list[PastIncidentRecord] = []
        for doc in documents:
            root_cause, resolution_summary = _split_content(doc.content)
            records.append(
                PastIncidentRecord(
                    incident_id=doc.document_id,
                    title=doc.title,
                    category=IncidentCategory(doc.metadata.get("category", IncidentCategory.UNKNOWN.value)),
                    root_cause=root_cause,
                    resolution_summary=resolution_summary,
                    resolved_at=doc.metadata.get("resolved_at") or doc.retrieved_at,
                    similarity_score=doc.score,
                )
            )
        return records


def _split_content(content: str) -> tuple[str, str]:
    root_cause = ""
    resolution_summary = ""
    for line in content.splitlines():
        if line.startswith("Root cause: "):
            root_cause = line.removeprefix("Root cause: ")
        elif line.startswith("Resolution: "):
            resolution_summary = line.removeprefix("Resolution: ")
    return root_cause, resolution_summary
