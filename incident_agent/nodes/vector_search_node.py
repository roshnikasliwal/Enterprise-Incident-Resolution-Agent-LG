"""Vector Search node -- one branch of the parallel evidence-gathering
subgraph. The Retriever Agent formulates multi-query + metadata-filter
search plans; this node executes them against the knowledge base and
turns the top results into citations Root Cause Analysis / the final
report can point back to.
"""

from __future__ import annotations

from typing import Any

from incident_agent.agents.retriever import RetrieverAgent
from incident_agent.graphs.state import IncidentState
from incident_agent.models.documents import Citation, RetrievedDocument
from incident_agent.models.execution import ReasoningStep
from incident_agent.nodes.agent_cache import get_agent
from incident_agent.nodes.formatting import format_intent
from incident_agent.nodes.node_runner import run_node
from incident_agent.nodes.tool_invocation import invoke_tool, tool_succeeded
from incident_agent.tools.knowledge_base_search import knowledge_base_search

_MAX_QUERIES = 3
_TOP_K_PER_QUERY = 3
_MAX_CITATIONS = 5


def vector_search_node(state: IncidentState) -> dict[str, Any]:
    def work() -> tuple[dict[str, Any], str]:
        task = state.get("current_task")
        agent = get_agent(RetrieverAgent)
        query_plan = agent.invoke(
            user_query=state["user_query"],
            intent=format_intent(state.get("intent")),
            task_description=task.description if task else "Find relevant runbooks/postmortems.",
        )

        doc_type = query_plan.metadata_filters.get("doc_type")
        documents_by_id: dict[str, RetrievedDocument] = {}
        for query in query_plan.queries[:_MAX_QUERIES]:
            payload = invoke_tool(knowledge_base_search, query=query, top_k=_TOP_K_PER_QUERY, doc_type=doc_type)
            if not tool_succeeded(payload):
                continue
            for raw_doc in payload["data"]["results"]:
                doc = RetrievedDocument.model_validate(raw_doc)
                existing = documents_by_id.get(doc.document_id)
                if existing is None or doc.score > existing.score:
                    documents_by_id[doc.document_id] = doc

        documents = sorted(documents_by_id.values(), key=lambda d: d.score, reverse=True)
        citations = [
            Citation(
                citation_id=f"cite-{doc.document_id}",
                document_id=doc.document_id,
                source=doc.source,
                locator=doc.title,
                snippet=doc.content[:300],
            )
            for doc in documents[:_MAX_CITATIONS]
        ]

        updates: dict[str, Any] = {
            "retrieved_documents": documents,
            "citations": citations,
            "reasoning": [
                ReasoningStep(
                    node_name="vector_search",
                    content=(
                        f"Ran {len(query_plan.queries[:_MAX_QUERIES])} quer(y/ies), found "
                        f"{len(documents)} unique document(s); top match: "
                        f"{documents[0].title if documents else 'none'}"
                    ),
                )
            ],
        }
        summary = f"found {len(documents)} relevant document(s)" if documents else "found no relevant documents"
        return updates, summary

    return run_node("vector_search", work)
