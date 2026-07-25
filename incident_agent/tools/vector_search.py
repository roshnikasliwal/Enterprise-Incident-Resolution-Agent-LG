"""Vector Search tool -- generic semantic similarity search.

Distinct from `knowledge_base_search`: this tool is the low-level
primitive (raw query + optional metadata filter, no assumptions about
document type), while `knowledge_base_search` is a friendlier, pinned
wrapper for the curated runbook/postmortem collection specifically. Both
share `VectorStoreService` so there is exactly one embedding pipeline.
"""

from __future__ import annotations

from langchain_core.tools import tool

from incident_agent.services.vector_store import get_vector_store_service
from incident_agent.tools.base import run_structured


@tool
def vector_search(query: str, top_k: int = 5, component_filter: str | None = None) -> str:
    """Semantic similarity search over the internal vector store.

    Use this to find documents whose *meaning* matches the query, even if
    they don't share exact keywords. `component_filter`, if given, narrows
    results to documents tagged with that component (e.g. 'kubernetes',
    'kafka', 'database', 'cache', 'application').

    Returns a JSON ToolResult whose `data.results` is a list of matched
    documents with a 0-1 relevance `score`.
    """
    service = get_vector_store_service()

    def implementation() -> dict:
        metadata_filter = {"component": component_filter} if component_filter else None
        documents = service.similarity_search(query, k=top_k, metadata_filter=metadata_filter)
        return {
            "query": query,
            "result_count": len(documents),
            "results": [doc.model_dump(mode="json") for doc in documents],
        }

    return run_structured("vector_search", implementation, metadata={"top_k": top_k})
