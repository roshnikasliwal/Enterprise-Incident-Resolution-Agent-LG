"""Vector store service -- Chroma-backed similarity search.

Wrapped behind `VectorStoreService` (rather than tools reaching into
`chromadb` directly) so `tools/vector_search.py` and
`tools/knowledge_base_search.py` share one embedding pipeline instead of
duplicating client setup, and so the embedding backend can be swapped
later (e.g. to a hosted API embedding model) without touching either
tool.

We use Chroma's bundled `DefaultEmbeddingFunction` (a local ONNX
all-MiniLM-L6-v2 model, downloaded once and cached under
`~/.cache/chroma`) rather than an API-based embedding model. This keeps
the RAG pipeline fully functional with zero API key configured --
important for a project meant to run and be tested without live
credentials -- while remaining a real, semantically meaningful vector
search rather than a keyword-match stub.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from incident_agent.config.logging_config import get_logger
from incident_agent.config.settings import get_settings
from incident_agent.models.documents import RetrievedDocument
from incident_agent.services.kb_seed_data import SEED_DOCUMENTS

logger = get_logger(__name__)


class VectorStoreService:
    """Thin, typed wrapper around one Chroma collection."""

    def __init__(self, persist_directory: str, collection_name: str) -> None:
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(self, documents: list[RetrievedDocument]) -> int:
        """Upsert documents; returns the number written. Idempotent on `document_id`."""
        if not documents:
            return 0
        self._collection.upsert(
            ids=[doc.document_id for doc in documents],
            documents=[doc.content for doc in documents],
            metadatas=[
                {"title": doc.title, "source": doc.source, **doc.metadata} for doc in documents
            ],
        )
        return len(documents)

    def similarity_search(
        self,
        query: str,
        *,
        k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedDocument]:
        """Top-k semantic search, optionally narrowed by an exact-match metadata filter
        (Chroma's `where` clause -- this is what backs self-query / metadata filtering
        for the Retriever Agent).
        """
        if self._collection.count() == 0:
            return []
        raw = self._collection.query(
            query_texts=[query],
            n_results=min(k, self._collection.count()),
            where=metadata_filter or None,
        )
        documents: list[RetrievedDocument] = []
        ids = raw.get("ids") or [[]]
        contents = raw.get("documents") or [[]]
        metadatas = raw.get("metadatas") or [[]]
        distances = raw.get("distances") or [[]]
        for doc_id, content, meta, distance in zip(
            ids[0], contents[0], metadatas[0], distances[0], strict=True
        ):
            meta = dict(meta or {})
            title = str(meta.pop("title", doc_id))
            source = str(meta.pop("source", "knowledge_base"))
            # Cosine distance in [0, 2] -> similarity score in [0, 1].
            score = max(0.0, min(1.0, 1.0 - (distance / 2.0)))
            documents.append(
                RetrievedDocument(
                    document_id=doc_id,
                    source="knowledge_base" if source not in _VALID_SOURCES else source,
                    title=title,
                    content=content,
                    score=score,
                    metadata=meta,
                )
            )
        return documents

    def count(self) -> int:
        return self._collection.count()

    def seed_if_empty(self) -> int:
        """Load the bundled runbook/postmortem corpus on first run so the
        knowledge base is never empty in a fresh environment. No-ops once seeded.
        """
        if self._collection.count() > 0:
            return 0
        documents = [
            RetrievedDocument(
                document_id=doc.document_id,
                source="knowledge_base",
                title=doc.title,
                content=doc.content,
                score=1.0,
                metadata={"doc_type": doc.doc_type, "component": doc.component},
            )
            for doc in SEED_DOCUMENTS
        ]
        count = self.add_documents(documents)
        logger.info("knowledge_base_seeded", extra={"document_count": count})
        return count


_VALID_SOURCES = {"vector_store", "knowledge_base", "web_search", "sql_database", "knowledge_graph"}


@lru_cache(maxsize=1)
def get_vector_store_service() -> VectorStoreService:
    """Process-wide singleton, mirroring `get_settings()`'s caching approach.

    Takes no arguments deliberately: `VectorStoreService(...)` remains directly
    constructible (e.g. pointed at a `tmp_path` collection) for tests that need
    an isolated instance instead of this cached, settings-derived singleton.
    """
    settings = get_settings()
    settings.ensure_data_directories()
    service = VectorStoreService(
        persist_directory=settings.chroma.persist_directory,
        collection_name=settings.chroma.collection_name,
    )
    service.seed_if_empty()
    return service
