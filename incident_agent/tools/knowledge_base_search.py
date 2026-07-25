"""Knowledge Base Search tool -- pinned to the curated runbook/postmortem
collection, with a `doc_type` filter (`runbook` vs. `postmortem`) that
`vector_search` doesn't expose. This is what the Retriever Agent uses by
default; `vector_search` remains available for ad-hoc/other collections.
"""

from __future__ import annotations

from langchain_core.tools import tool

from incident_agent.services.vector_store import get_vector_store_service
from incident_agent.tools.base import run_structured


@tool
def knowledge_base_search(
    query: str,
    top_k: int = 3,
    doc_type: str | None = None,
) -> str:
    """Search the internal knowledge base of runbooks and incident postmortems.

    `doc_type`, if given, restricts results to `'runbook'` (step-by-step
    diagnostic guides) or `'postmortem'` (writeups of specific past
    incidents). Leave it unset to search both.

    Returns a JSON ToolResult whose `data.results` is a list of matched
    documents with a 0-1 relevance `score`.
    """
    service = get_vector_store_service()

    def implementation() -> dict:
        metadata_filter = {"doc_type": doc_type} if doc_type else None
        documents = service.similarity_search(query, k=top_k, metadata_filter=metadata_filter)
        return {
            "query": query,
            "result_count": len(documents),
            "results": [doc.model_dump(mode="json") for doc in documents],
        }

    return run_structured("knowledge_base_search", implementation, metadata={"doc_type": doc_type})
