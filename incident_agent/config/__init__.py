"""Configuration layer.

Centralizes all environment-driven configuration (LLM providers, vector
store, checkpoint database, API, observability) behind typed Pydantic
Settings objects so the rest of the codebase never reads `os.environ`
directly. This keeps configuration testable and makes provider switching
(e.g. Anthropic -> OpenAI fallback) a config change, not a code change.
"""
