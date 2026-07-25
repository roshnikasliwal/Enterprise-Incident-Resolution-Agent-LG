"""Controller layer.

Thin orchestration classes that sit between the FastAPI routers (api/) and
the LangGraph graphs (graphs/). Controllers translate transport-level
requests into graph invocations/streams and translate graph state back into
API response schemas. No business logic lives here.
"""
