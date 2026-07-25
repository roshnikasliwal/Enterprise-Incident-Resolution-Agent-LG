"""Schema layer.

Pydantic models for (a) structured LLM outputs consumed via
`with_structured_output`, and (b) FastAPI request/response contracts.
Keeping these in one place lets every agent and endpoint share a single
source of truth for shape validation.
"""
